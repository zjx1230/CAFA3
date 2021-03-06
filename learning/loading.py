import gzip
import csv
import os
import operator
from collections import defaultdict
from sklearn.feature_extraction import DictVectorizer
from sklearn.preprocessing import MultiLabelBinarizer
from sklearn.feature_selection.variance_threshold import VarianceThreshold

def openAny(inPath, mode):
    return gzip.open(inPath, mode) if inPath.endswith(".gz") else open(inPath, mode)

def loadBaseline(inPath, proteins, key="baseline", cutoff=1, limitTerms=None, useCafa=False):
    baselinePath = inPath #os.path.join(inPath, "fallback", "trial")
    print "Loading BLAST baseline from", baselinePath
    counts = defaultdict(int)
    baselineTerms = set()
    #filenames = ["Jari_develtest.tsv.gz"] #["Jari_devel.tsv.gz", "Jari_test.tsv.gz"] #["Swissprot_sequence.go_count.tsv.gz"]
    #if useCafa:
    #    filenames.append("Blast_CAFA3.tsv.gz") # "target_all.go_count.tsv.gz")
    filenames = [x for x in os.listdir(baselinePath) if x.endswith(".tsv.gz")]
    for filename in filenames:
        filePath = os.path.join(baselinePath, filename)
        print "Reading", filePath
        with gzip.open(filePath, "rt") as f:
            tsv = csv.reader(f, delimiter='\t')
            for row in tsv:
                protId, goTerm, blastCount = row
                blastCount = int(blastCount)
                if blastCount < cutoff:
                    counts["skipped-total"] += 1
                    counts["skipped-" + str(blastCount)] += 1
                    continue
                protein = proteins[protId]
                if key not in protein:
                    protein[key] = {}
                #assert goTerm not in protein[key]
                if goTerm in protein[key]:
                    counts["duplicates"] += 1
                protein[key][goTerm] = blastCount
                baselineTerms.add(goTerm)
                counts[blastCount] += 1
    counts["unique-terms"] = len(baselineTerms)
    if limitTerms != None:
        counts["top-terms"] = len(limitTerms)
        #print list(baselineTerms)[0:10]
        #print terms.keys()[0:10]
        for goTerm in baselineTerms:
            if goTerm not in limitTerms:
                counts["out-of-top-terms"] += 1
            else:
                counts["included-in-top-terms"] += 1
    print "Loaded baseline,", dict(counts)

def loadAnnotations(inPath, proteins):
    print "Loading annotations from", inPath
    counts = defaultdict(int)
    with gzip.open(inPath, "rt") as f:
        tsv = csv.reader(f, delimiter='\t')
        rowCount = 0
        for row in tsv:
            assert len(row) == 3, (row, rowCount)
            protId, goTerm, evCode = row
            protein = proteins[protId]
            if "terms" not in protein:
                protein["terms"] = {}
            protein["terms"][goTerm] = evCode
            counts[goTerm] += 1
            rowCount += 1
    return counts

def removeNonHuman(proteins):
    counts = {"kept":0, "removed":0}
    for protId in proteins.keys():
        if not protId.endswith("_HUMAN"):
            del proteins[protId]
            counts["removed"] += 1
        else:
            counts["kept"] += 1
    print "Removed non-human proteins:", counts

def loadHPOAnnotations(inPath, proteins):
    print "Loading HPO annotations from", inPath
    counts = defaultdict(int)
    stats = {"missing":set(), "match":set()}
    with gzip.open(inPath, "rt") as f:
        tsv = csv.reader(f, delimiter='\t')
        for row in tsv:
            termId, protId = row
            if protId not in proteins:
                stats["missing"].add(protId)
                continue
            stats["match"].add(protId)
            protein = proteins[protId]
            if "terms" not in protein:
                protein["terms"] = {}
            protein["terms"][termId] = "N/A"
            counts[termId] += 1
    print "Loaded HPO annotations:", {key:len(stats[key]) for key in stats}
    return counts

def getTopTerms(counts, num=1000):
    return sorted(counts.items(), key=operator.itemgetter(1), reverse=True)[0:num]

def loadGOTerms(inPath):
    print "Loading GO terms from", inPath
    terms = {}
    with open(inPath, "rt") as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            #print row
            assert row["id"] not in terms
            terms[row["id"]] = row
    return terms

def loadOBOTerms(inPath, onlyNames=False, forceNameSpace=None):
    print "Reading OBO ontology from", inPath
    terms = {}
    with open(inPath, "rt") as f:
        term = None
        for line in f:
            if line.startswith("["):
                term = None
                if line.startswith("[Term]"):
                    term = {}
            elif term != None and ":" in line:
                line = line.strip()
                tag, content = [x.strip() for x in line.split(":", 1)]
                term[tag] = content
                if tag in ("id", "alt_id"):
                    #assert content not in terms, (tag, content)
                    terms[content] = term
                if tag == "namespace":
                    term["ns"] = "".join([x[0] for x in content.split("_")])
    if forceNameSpace != None:
        for term in terms.values():
            term["ns"] = forceNameSpace
    #if onlyNames:
    #    terms = {key:terms[key]["name"] for key in terms}
    return terms

def addProtein(proteins, protId, cafaId, sequence, filename, replaceSeq=False, verbose=False, counts=None):
    assert len(sequence) > 0
    if protId not in proteins:
        proteins[protId] = {}
        proteins[protId]["seq"] = sequence
        proteins[protId]["id"] = protId
        proteins[protId]["cafa_ids"] = [cafaId] if cafaId else []
        proteins[protId]["file"] = [filename]
        proteins[protId]["terms"] = {}
        counts["unique"] += 1
    else:
        counts["multiple"] += 1
        if proteins[protId]["seq"] != sequence:
            if verbose:
                print "WARNING, sequence mismatch for", protId, cafaId, ":", (proteins[protId], (protId, cafaId, sequence, filename))
            counts["mismatch"] += 1
            counts["mismatches"].append(protId)
            if replaceSeq:
                proteins[protId]["seq"] = sequence
        assert proteins[protId]["id"] == protId, (proteins[protId], (protId, cafaId, sequence, filename))
        proteins[protId]["file"] += [filename]
        if cafaId != None:
            if len(proteins[protId]["cafa_ids"]) > 0:
                if verbose:
                    print "WARNING, duplicate CAFA target", protId, cafaId, ":", (proteins[protId], (protId, cafaId, sequence, filename))
                counts["duplicate_id"] += 1
                counts["duplicate_ids"].append(protId)
                proteins[protId]["cafa_ids"].append(cafaId)
            else:
                proteins[protId]["cafa_ids"] += [cafaId]
    assert "id" in proteins[protId], (protId, cafaId, proteins[protId])
         
def loadFASTA(inPath, proteins, cafaHeader=False):
    print "Loading sequences from", inPath
    filename = os.path.basename(inPath)
    counts = defaultdict(int)
    counts["mismatches"] = []
    counts["duplicate_ids"] = []
    with openAny(inPath, "rt") as f:
        protId = None
        cafaId = None
        sequence = ""
        for line in f:
            if line.startswith(">"):
                # Add already read protein
                if protId != None:
                    addProtein(proteins, protId, cafaId, sequence, filename, counts=counts)
                protId = None
                cafaId = None
                sequence = ""
                # Begin new protein
                protId = line[1:].strip()
                if cafaHeader:
                    cafaId, protId = protId.split()
            else:
                sequence += line.strip()
        if protId != None:
            addProtein(proteins, protId, cafaId, sequence, filename, counts=counts)               
            #print seq.id, seq.seq
    print dict(counts)

def loadSplit(inPath, proteins, allowMissing=False):
    print "Loading split from", inPath
    counts = defaultdict(int)
    for dataset in ("train", "devel", "test"):
        filePath = os.path.join(inPath, dataset + ".txt.gz")
        assert os.path.exists(filePath), filePath
        with gzip.open(filePath, "rt") as f:
            for line in f:
                protId = line.strip()
                if not allowMissing:
                    assert protId in proteins
                if protId in proteins:
                    proteins[protId]["split"] = dataset
                    counts[dataset + "-match"] += 1
                else:
                    counts[dataset + "-missing"] += 1
    print "Loaded split:", dict(counts)

def defineFoldSets(fold, numFolds=10, numDevel=2):
    print "Defining train/devel/test split for", str(numFolds) + "-fold cross-validation fold number", fold
    folds = range(numFolds)
    assert fold in folds
    foldSets = {x:"train" for x in folds}
    foldSets[fold] = "test"
    for develFold in range(fold + 1, fold + 1 + numDevel):
        if develFold >= numFolds:
            develFold -= numFolds
        foldSets[develFold] = "devel"
    print "Cross-validation sets:", ",".join([str(x) + ":" + foldSets[x] for x in sorted(foldSets.keys())])
    return foldSets

def defineSets(proteins, cafaTargets, fold=None, limitTrainingToAnnotated=True):
    counts = defaultdict(int)
    filtered = defaultdict(int)
    if fold != None:
        foldSets = defineFoldSets(fold)
    for protId in proteins.keys():
        protein = proteins[protId]
        assert "id" in protein, protein
        cafaSet = ["cafa"] if (len(protein["cafa_ids"]) or "cafa" in protein["split"]) > 0 else []
        if fold != None:
            splitSet = [foldSets[protein["fold"]]] if protein.get("fold") != None else []
        else:
            splitSet = [protein["split"]] if protein.get("split") != None else []
        if limitTrainingToAnnotated and len(protein["terms"]) == 0:
            for s in splitSet:
                filtered[s] += 1
            splitSet = []
            if cafaSet == []: # If a protein has no terms and is not a CAFA target it is removed 
                del proteins[protId]
                filtered["deleted"] += 1
                continue
        if len(cafaSet) > 0:
            if cafaTargets == "overlap":
                protein["sets"] = cafaSet + splitSet
            elif cafaTargets == "separate":
                if "train" in splitSet:
                    protein["sets"] = cafaSet
                else:
                    protein["sets"] = cafaSet + splitSet
            elif cafaTargets == "external":
                protein["sets"] = splitSet if len(splitSet) > 0 else cafaSet
            else:
                raise Exception("CAFA targets were loaded with mode '" + cafaTargets + "'")
        else:
            protein["sets"] = splitSet
        assert len(protein["sets"]) > 0
        category = ",".join(cafaSet + splitSet) + "=>" + ",".join(protein["sets"])
        counts[category] += 1
    print "Defined sets:", dict(counts), "Filtered:", dict(filtered)

def saveIdNames(names, outPath):
    print "Saving id names to", outPath
    with (gzip.open(outPath, "wt") if outPath.endswith(".gz") else open(outPath, "wt")) as f:
        f.write("index\tname\n")
        for i in range(len(names)):
            f.write(str(i) + "\t" + names[i] + "\n")

def loadIdNames(inPath):
    print "Loading id names from", inPath
    idNames = {} 
    with (gzip.open(inPath, "rt") if inPath.endswith(".gz") else open(inPath, "rt")) as f:
        reader = csv.DictReader(f, delimiter='\t')
        for line in reader:
            index = int(line["index"])
            assert index not in idNames
            idNames[index] = line["name"]
    print "Loaded", len(idNames), "id names"
    return idNames
    
def vectorizeExamples(examples, featureGroups=None, sparseLabels=False, idPath=None):
    print "Vectorizing examples"
    mlb = MultiLabelBinarizer(sparse_output=sparseLabels)
    if "predictions" in examples and examples["predictions"] != None:
        print "Vectorizing predictions"
        assert idPath == None
        #examples["labels"] = mlb.fit_transform(examples["labels"])
        #examples["predictions"] = examples["labels"]
        numLabels = len(examples["labels"])
        vector = mlb.fit_transform(examples["labels"] + examples["predictions"])
        examples["labels"] = vector[:numLabels,:]
        examples["predictions"] = vector[numLabels:,:]
        print "Vectorized predictions", (examples[x].shape[1] for x in ("labels", "predictions"))
    else:
        if idPath != None:
            labelIdPath = os.path.join(idPath, "labels.tsv")
            print "Vectorizing labels with existing ids from", labelIdPath
            labelNames = loadIdNames(labelIdPath)
            mlb = MultiLabelBinarizer([labelNames[x] for x in sorted(labelNames.keys())], sparse_output=sparseLabels)
            mlb.fit(set(labelNames.values()))
            examples["labels"] = mlb.transform(examples["labels"])
        else:
            print "Vectorizing labels with new ids"
            examples["labels"] = mlb.fit_transform(examples["labels"])
    examples["label_names"] = mlb.classes_
    if "features" in examples:
        print "Vectorizing features"
        dv = DictVectorizer(sparse=True)
        if idPath != None:
            featureIdPath = os.path.join(idPath, "features.tsv.gz")
            print "Vectorizing features with existing ids from", featureIdPath
            featureNames = loadIdNames(featureIdPath)
            #dv.fit([featureNames])
            dv.feature_names_ = [featureNames[x] for x in sorted(featureNames.keys())]
            dv.vocabulary_ = dict((f, i) for i, f in enumerate(dv.feature_names_))
            examples["features"] = dv.transform(examples["features"])
        else:
            print "Vectorizing features with new ids"
            examples["features"] = dv.fit_transform(examples["features"])
        examples["feature_names"] = dv.feature_names_
    else:
        examples["feature_names"] = []
    if featureGroups != None and "select" in featureGroups:
        threshold = .1
        print "Selecting features", examples["features"].shape[1]
        examples["features"] = VarianceThreshold(threshold * (1 - threshold)).fit_transform(examples["features"])
        print "Selected features", examples["features"].shape[1]
        #examples["features"] = SelectKBest(chi2, k=1000).fit_transform(examples["features"], examples["labels"])
    print "Vectorized", examples["labels"].shape[0], "examples with", len(examples["feature_names"]), "unique features and", len(examples["label_names"]), "unique labels", ("(sparse)" if sparseLabels else "")
