import sys, os
import gzip
from collections import defaultdict
import csv
from sklearn.feature_extraction import DictVectorizer
from sklearn.preprocessing import MultiLabelBinarizer
from sklearn.grid_search import GridSearchCV, ParameterGrid
from sklearn.ensemble.forest import ExtraTreesClassifier, RandomForestClassifier
from sklearn.metrics import classification_report, f1_score

import operator
import time
from sklearn.cross_validation import train_test_split

def loadUniprotSimilarity(inPath, proteins):
    for key in proteins:
        proteins[key]["similar"] = {"sub":set(), "fam":set()}
    print "Loading uniprot similar.txt"
    with open(inPath, "rt") as f:
        section = None
        group = None
        subgroup = ""
        #lineCount = 0
        for line in f:
            if line.startswith("I. Domains, repeats and zinc fingers"):
                section = "sub"
            elif line.startswith("II. Families"):
                section = "fam"
            elif section == None: # Not yet in the actual data
                continue
            elif line.startswith("----------"): # end of file
                break
            elif line.strip() == "":
                continue
            #elif line.strip() == "": # empty line ends block
            #    group = None
            elif line[0].strip() != "": # a new group (family or domain)
                group = line.strip().replace(" ", "-").replace(",",";")
                subgroup = ""
            elif line.startswith("  ") and line[2] != " ":
                subgroup = "<" + line.strip().replace(" ", "-").replace(",",";") + ">"
            elif line.startswith("     "):
                assert group != None, line
                items = [x.strip() for x in line.strip().split(",")]
                items = [x for x in items if x != ""]
                protIds = [x.split()[0] for x in items]
                for protId in protIds:
                    if protId in proteins:
                        proteins[protId]["similar"][section].add(group + subgroup)

def loadTerms(inPath, proteins):
    print "Loading terms from", inPath
    counts = defaultdict(int)
    with gzip.open(inPath, "rt") as f:
        tsv = csv.reader(f, delimiter='\t')
        for row in tsv:
            protId, goTerm, evCode = row
            protein = proteins[protId]
            if "terms" not in protein:
                protein["terms"] = {}
            protein["terms"][goTerm] = evCode
            counts[goTerm] += 1
    return counts

def loadSequences(inPath, proteins):
    print "Loading sequences from", inPath
    with gzip.open(inPath, "rt") as f:
        header = None
        for line in f:
            if header == None:
                assert line.startswith(">")
                header = line[1:].strip()
            else:
                proteins[header]["seq"] = line.strip()
                proteins[header]["id"] = header
                header = None
            #print seq.id, seq.seq

def loadSplit(inPath, proteins):
    for dataset in ("train", "devel", "test"):
        filePath = os.path.join(inPath, dataset + ".txt.gz")
        assert os.path.exists(filePath), filePath
        with gzip.open(filePath, "rt") as f:
            for line in f:
                protId = line.strip()
                assert protId in proteins
                proteins[protId]["set"] = dataset

def splitProteins(proteins):
    datasets = {"devel":[], "train":[], "test":[]}
    for protId in sorted(proteins.keys()):
        datasets[proteins[protId]["set"]].append(proteins[protId])
    print "Divided sets", [(x, len(datasets[x])) for x in sorted(datasets.keys())]
    return datasets

def buildExamples(proteins, limit=None, limitTerms=None, featureGroups=None):
    print "Building examples"
    examples = {"labels":[], "features":[], "ids":[], "sets":[], "label_names":[], "label_size":{}}
    mlb = MultiLabelBinarizer()
    dv = DictVectorizer(sparse=True)
    protIds = sorted(proteins.keys())
    if limit:
        protIds = protIds[0:limit]
    counts = {"instances":0, "unique":0}
    for protId in protIds:
        protein = proteins[protId]
        # Build features
        features = {"dummy":1}
        if featureGroups == None or "seq" in featureGroups:
            seq = protein["seq"]
            for i in range(len(seq)-3):
                feature = seq[i:i+3]
                features[feature] = 1
        if featureGroups == None or "similar" in featureGroups:
            for group in protein["similar"]["sub"]:
                features["sub_" + group] = 1
            for group in protein["similar"]["fam"]:
                features["fam_" + group] = 1
        # Build labels
        labels = protein["terms"].keys()
        if limitTerms:
            labels = [x for x in labels if x in limitTerms]
        labels = sorted(labels)
        if len(labels) == 0:
            labels = ["no_annotations"]
        for label in labels:
            if label not in examples["label_size"]:
                examples["label_size"][label] = 0
            examples["label_size"][label] += 1
        examples["labels"].append(labels)
        examples["features"].append(features)
        examples["ids"].append(protId)
        examples["sets"].append(protein["set"])
        #print features
    examples["features"] = dv.fit_transform(examples["features"])
    examples["labels"] = mlb.fit_transform(examples["labels"])
    examples["label_names"] = mlb.classes_
    return examples
    #return mlb.fit_transform(examples["labels"]), dv.fit_transform(examples["features"])

def getTopTerms(counts, num=1000):
    return sorted(counts.items(), key=operator.itemgetter(1), reverse=True)[0:num]

def getResults(examples, scores):
    assert len(scores) == len(examples["label_names"])
    results = []
    for i in range(len(examples["label_names"])):
        label = examples["label_names"][i]
        results.append({"score":scores[i], "id":label, "label_size":examples["label_size"][label]})
    return results

def printResults(results, maxNumber=None):
    count = 0
    results = [(x["score"], x["id"], x["label_size"]) for x in results]
    for result in sorted(results, reverse=True):
        print result
        count += 1
        if count > maxNumber:
            break

def saveResults(results, outPath):
    print "Writing results to", outPath
    with open(outPath, "wt") as f:
        dw = csv.DictWriter(f, ["score", "id", "label_size"], delimiter='\t')
        dw.writeheader()
        dw.writerows(sorted(results, key=lambda x: x["score"], reverse=True))

def optimize(examples, verbose=3, n_jobs = -1, scoring = "f1_micro", cvJobs=1):
    grid = ParameterGrid({"n_estimators":[10], "n_jobs":[n_jobs], "verbose":[verbose]}) #{"n_estimators":[1,2,10,50,100]}
    #XTrainAndDevel, XTest, yTrainAndDevel, yTest = train_test_split(X, y, test_size=0.2, random_state=0)
    #XTrain, XDevel, yTrain, yDevel = train_test_split(XTrainAndDevel, yTrainAndDevel, test_size=0.2, random_state=0)
    sets = examples["sets"]
    trainIndices = [i for i in range(len(sets)) if sets[i] == "train"]
    develIndices = [i for i in range(len(sets)) if sets[i] == "devel"]
    trainFeatures = examples["features"][trainIndices]
    develFeatures = examples["features"][develIndices]
    trainLabels = examples["labels"][trainIndices]
    develLabels = examples["labels"][develIndices]
    print "Train / devel = ", trainFeatures.shape[0], "/", develFeatures.shape[0]
    best = None
    print "Parameter grid search", time.strftime('%X %x %Z')
    for args in grid:
        print "Learning with args", args
        cls = RandomForestClassifier(**args)
        cls.fit(trainFeatures, trainLabels)
        predicted = cls.predict(develFeatures)
        score = f1_score(develLabels, predicted, average="micro")
        scores = f1_score(develLabels, predicted, average=None)
        print "Average =", score
        results = getResults(examples, scores)
        printResults(results, 20)
        if best == None or score > best["score"]:
            best = {"score":score, "results":results, "args":args}
        print time.strftime('%X %x %Z')
    return best
    #clf = GridSearchCV(RandomForestClassifier(), args, verbose=verbose, n_jobs=cvJobs, scoring=scoring)
    #clf.fit(X, y)
    #print "Best params", (clf.best_params_, clf.best_score_)

# def learn(train, devel, test, limit=None, limitTerms=None, featureGroups=None):
#     print time.strftime('%X %x %Z')
#     print "Building devel examples"
#     develLabels, develFeatures = buildExamples(devel, limit, limitTerms, featureGroups)
#     print "Building train examples"
#     trainLabels, trainFeatures = buildExamples(train, limit, limitTerms, featureGroups)
#     if test != None:
#         print "Building train examples"
#         testLabels, testFeatures = buildExamples(test, limit, limitTerms, featureGroups)
#     optimize(trainFeatures, develFeatures, trainLabels, develLabels, verbose=3, n_jobs = -1, scoring = "f1_micro", cvJobs=1)

def run(dataPath, output=None, featureGroups=None, limit=None, useTestSet=False):
    proteins = defaultdict(lambda: dict())
    loadSequences(os.path.join(options.dataPath, "Swiss_Prot", "Swissprot_sequence.tsv.gz"), proteins)
    counts = loadTerms(os.path.join(options.dataPath, "Swiss_Prot", "Swissprot_propagated.tsv.gz"), proteins)
    loadUniprotSimilarity(os.path.join(options.dataPath, "Uniprot", "similar.txt"), proteins)
    print "Proteins:", len(proteins)
    topTerms = getTopTerms(counts, 100)
    print "Most common terms:", topTerms
    print proteins["14310_ARATH"]
    loadSplit(os.path.join(options.dataPath, "Swiss_Prot"), proteins)
    #divided = splitProteins(proteins)
    examples = buildExamples(proteins, limit, limitTerms=set([x[0] for x in topTerms]), featureGroups=featureGroups)
    best = optimize(examples)
    if output != None:
        saveResults(best["results"], output)
    #y, X = buildExamples(proteins, None, set([x[0] for x in topTerms]))
    #print y
    #print X
    #print time.strftime('%X %x %Z')
    #classify(y, X)
    #print time.strftime('%X %x %Z')

if __name__=="__main__":       
    from optparse import OptionParser
    optparser = OptionParser(description="")
    optparser.add_option("-p", "--dataPath", default=os.path.expanduser("~/data/CAFA3"), help="")
    optparser.add_option("-f", "--features", default="similar", help="")
    optparser.add_option("-l", "--limit", default=None, type=int, help="")
    optparser.add_option("-o", "--output", default=None, help="")
    optparser.add_option("--testSet", default=False, action="store_true", help="")
    (options, args) = optparser.parse_args()
    
    #proteins = de
    #importProteins(os.path.join(options.dataPath, "Swiss_Prot", "Swissprot_sequence.tsv.gz"))
    run(options.dataPath, featureGroups=options.features.split(","), limit=options.limit, useTestSet=options.testSet, output=options.output)