from collections import OrderedDict
from sklearn.metrics import classification_report
#from sklearn.cross_validation import LabelKFold
from sklearn.grid_search import GridSearchCV
from sklearn.feature_extraction import DictVectorizer
from sklearn.svm import SVC
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.neighbors import KNeighborsClassifier
import copy
from collections import defaultdict
from sklearn.naive_bayes import GaussianNB, MultinomialNB, BernoulliNB
from sklearn.linear_model.perceptron import Perceptron
from sklearn.ensemble.gradient_boosting import GradientBoostingClassifier
from sklearn.linear_model.stochastic_gradient import SGDClassifier
from sklearn.neighbors.nearest_centroid import NearestCentroid
from sklearn.metrics import f1_score
import evaluateFile
import loading
import evaluation
import sys, os

def showStats(interactions, entities, useGold):
    stats = defaultdict(int)
    statsIds = defaultdict(str)
    confScores = {"a":set(), "b":set()}
    for key in interactions:
        interaction = interactions[key]
        if useGold:
            goldClass = interaction["gold"].get("type")
            combination = goldClass
        else:
            goldClass = "neg"
            combination = "unknown" 
        combination += "(" + entities[interaction["a"].get("e1")].get("type") + "/" + entities[interaction["a"].get("e2")].get("type") + ")" 
        for setName in ("a", "b"):
            combination += "_" + setName + ":"
            predClass = interaction[setName].get("type")
            if useGold:
                combination += "t" if goldClass == predClass else "f"
            combination += "n" if predClass == "neg" else "p"
            confScores[setName].add(getConfScore(interaction[setName]))
        stats[combination] += 1
        statsIds[combination] += key + "_"
    for key in sorted(stats.keys()):
        print key, stats[key] #, statsIds[key][0:100]
    print "Confidence score ranges"
    for setName in ("a", "b"):
        print setName, [min(confScores[setName]), max(confScores[setName])]

def getConfScore(interaction):
    conf = interaction.get("conf")
    if conf == "":
        return 0
    elif "," in conf:
        splits = conf.split(",")[-1].split(":")
        assert splits[0] == "Lives_In"
        confScore = 0.005 * float(splits[1])
    else:
        confScore = float(conf) - 0.5 # - 1.0
    return confScore

def buildFeatures(interactions, entities, show=10):
    features = []
    for key in interactions:
        f = {}
        confidences = {}
        combined = {"types":"comb_pred"}
        aPos = interactions[key]["a"].get("type") != "neg"
        bPos = interactions[key]["b"].get("type") != "neg"
        #f["AND"] = combinePredictions(aPos, bPos, "AND")
        f["OR"] = combinePredictions(aPos, bPos, "OR")
        if True:
            for setName in ("a", "b"):
                # interaction
                interaction = interactions[key][setName]
                predType = interaction.get("type")
                f["pred-" + setName] = 1 if predType != "neg" else -1
#                 combined["types"] += "-" + predType
#                for intType in ("neg", "Lives_In"):
#                     if predType == intType:
#                         f[setName + "_type_" + intType] = 1
#                     else:
#                         f[setName + "_type_not_" + intType] = 1
                #f[setName + "_pred"] = 1 if interaction.get("type") != "neg" else -1
                # entities
                e1 = entities[interaction.get("e1")]
                e2 = entities[interaction.get("e2")]
                #distance = abs(int(e1.get("charOffset").split("-")[0]) - int(e2.get("charOffset").split("-")[0]))
                #f["distance"] = distance
                for entity, entKey in [(e1, "e1"), (e2, "e2")]:
                    f[entKey + "_type_" + entity.get("type")] = 1
                    #for token in entity.get("text").split():
                    #    f[entKey + "_token_" + token] = 1
                    #f[entKey + "_text_" + entity.get("text").split()[-1].lower()] = 1
                f["e_types_" + e1.get("type") + "-" + e2.get("type")] = 1
                # confidence scores
                confScore = getConfScore(interaction)
                confidences[setName] = confScore
                f[setName + "_conf"] = confScore
            f["combined_conf"] = (confidences["a"] + confidences["b"]) / 2.0
            #f["combined_pred"] = 1 if f["combined_conf"] > 0 else -1
            f["combined_pred_type_" + ("pos" if f["combined_conf"] > 0 else "neg")] = 1
            for combinedFeature in sorted(combined.values()):
                f[combinedFeature] = 1
        if show > 0:
            print f
            show -= 1
        features.append(f)
    return DictVectorizer(sparse=False).fit_transform(features)

def getInteractions(a, b, gold):
    interactions = OrderedDict()
    for interaction in a.getroot().iter('interaction'):
        interactions[interaction.get("id")] = {"a":interaction, "b":None, "gold":None}
    for interaction in b.getroot().iter('interaction'):
        assert interaction.get("id") in interactions, (interaction.get("id"), interactions.keys())
        interactions[interaction.get("id")]["b"] = interaction
    if gold:
        numIntersentence = 0
        for interaction in gold.getroot().iter('interaction'):
            #print interaction.get("e1").split(".i")[0], interaction.get("e2").split(".i")[0]
            if interaction.get("e1").split(".e")[0] != interaction.get("e2").split(".e")[0]:
                numIntersentence += 1
                continue
            assert interaction.get("id") in interactions, (interaction.get("id"), interactions.keys())
            interactions[interaction.get("id")]["gold"] = interaction
        print "Skipped", numIntersentence, "intersentence interactions"
    return interactions

#def mapHeads(entities, xml):
#    for template.getroot().iter('sentence'):

def getERole(entity):
    eType = entity.get("type")
    assert eType in ("Bacteria", "Habitat", "Geographical")
    if eType == "Bacteria":
        return "Bacteria"
    else:
        return "Location"

def writeOutput(template, predictions, outPath):
    print "Generating output"
    template = copy.deepcopy(template)
    entities = {x.get("id"):x for x in template.getroot().iter('entity')}
    outInteractions = [x for x in template.getroot().iter('interaction')]
    assert len(outInteractions) == len(predictions)
    for i in range(len(predictions)):
        interaction = outInteractions[i]
        interaction.set("type", "Lives_In" if predictions[i] > 0 else "neg")
        interaction.set("e1Role", getERole(entities[interaction.get("e1")]))
        interaction.set("e2Role", getERole(entities[interaction.get("e2")]))
    print "Writing output to", outPath
    ETUtils.write(template.getroot(), outPath)
    ConvertXML.toSTFormat(template, outPath + "-events.zip", outputTag="a2", useOrigIds=False, debug=False, allAsRelations=False, writeExtra=False)

def combinePredictions(aPos, bPos, mode="AND"):
    if mode == "AND":
        return 1 if (aPos and (aPos == bPos)) else -1
    elif mode == "OR":
        return 1 if (aPos or bPos) else -1

def getSimpleCombinedPredictions(interactions, mode = "AND"):
    predictions = []
    for key in interactions:
        interaction = interactions[key]
        aPos = interaction["a"].get("type") != "neg"
        bPos = interaction["b"].get("type") != "neg"
        predictions.append(combinePredictions(aPos, bPos, mode))
    return predictions

def evaluatePerformance(labels, predictions, results, title, tag=None, verbose=True):
    if verbose:
        print title
        print classification_report(labels, predictions)
    f1score = f1_score(labels, predictions)
    #print f1score
    results.append((f1score, tag, title, predictions))

def clearKey(proteins, key):
    for protId in proteins:
        protein = proteins[protId]
        if key in protein:
            del protein[key]

def combinePred(proteins, key1, key2, combKey, mode="AND", limitToSets=None):
    assert mode in ("AND", "OR", "ONLY1", "ONLY2")
    counts = defaultdict(int)
    for protId in proteins:
        protein = proteins[protId]
        if limitToSets != None and not any(x in limitToSets for x in protein["sets"]):
            counts["out-of-sets"] += 1
            continue
        counts["proteins"] += 1
        protein[combKey] = {}
        if mode == "AND":
            for key in (key1, key2):
                if key in protein:
                    counts["predictions-mode-" + mode] += 1
                    protein[combKey].update(protein[key])
                else:
                    counts["no-prediction-for-" + key] += 1
        elif mode == "OR":
            if key1 not in protein:
                counts["no-prediction-for-" + key1] += 1
            elif key2 not in protein:
                counts["no-prediction-for-" + key2] += 1
            else:
                counts["predictions-mode-" + mode] += 1
                pred1 = set(protein[key1].keys())
                pred2 = set(protein[key2].keys())
                protein[combKey] = {x:1 for x in pred1.intersection(pred2)}
        else:
            key = key1 if mode == "ONLY1" else key2
            if key not in protein:
                counts["no-prediction-for-" + key] += 1
            else:
                counts["predictions-mode-" + mode] += 1
                protein[combKey] = protein[key]
                
    print "Combined predictions, mode =", mode, "counts =", dict(counts)
    
def combine(dataPath, nnInput, clsInput, useCafa=False):
    print "==========", "Ensemble", "=========="
    proteins = {}
    print "Loading Swissprot proteins"
    loading.loadFASTA(os.path.join(options.dataPath, "Swiss_Prot", "Swissprot_sequence.tsv.gz"), proteins)
    if useCafa == "cafa":
        print "Loading CAFA3 targets"
        loading.loadFASTA(os.path.join(options.dataPath, "CAFA3_targets", "Target_files", "target.all.fasta"), proteins, True)
    print "Proteins:", len(proteins)
    termCounts = loading.loadAnnotations(os.path.join(options.dataPath, "data", "Swissprot_propagated.tsv.gz"), proteins)
    print "Unique terms:", len(termCounts)
    topTerms = loading.getTopTerms(termCounts, 5000)
    print "Using", len(topTerms), "most common GO terms"
    loading.loadSplit(os.path.join(options.dataPath, "data"), proteins)
    loading.defineSets(proteins, "overlap" if useCafa else "skip")
    
    print "Loading neural network predictions from", nnInput
    for setName in (("devel", "test", "cafa") if useCafa else ("devel", "test")):
        evaluateFile.loadPredictions(proteins, os.path.join(nnInput, setName + ("_targets" if setName == "cafa" else "_pred")) + ".tsv.gz", limitToSets=None, readGold=False, predKey="nn_pred_" + setName)
    print "Loading classifier predictions"
    evaluateFile.loadPredictions(proteins, clsInput, limitToSets=["devel","test","cafa"] if useCafa else ["devel","test"], readGold=True, predKey="cls_pred")
    
    print "Combining predictions"
    combKey = "combined"
    for setName in ("devel", "test"):
        for mode in ("ONLY1", "ONLY2", "AND", "OR"):
            print "***", "Evaluating predictions for set '" + setName + "' using mode '" + mode + "'", "***"
            combinePred(proteins, "nn_pred_" + setName, "cls_pred", combKey, mode, limitToSets=[setName])
            examples = evaluateFile.makeExamples(proteins, limitTerms=set([x[0] for x in topTerms]), limitToSets=[setName], predKey=combKey)
            loading.vectorizeExamples(examples, None)
            results = evaluation.evaluate(examples["labels"], examples["predictions"], examples, terms=None, averageOnly=True)
            print "Average:", evaluation.metricsToString(results["average"])
            clearKey(proteins, combKey)
    
    sys.exit()
    
    learnedPredictions = None
    if learning:
        print "===============", "Learning", "===============" 
        X_all = buildFeatures(interactions, entities)
        learnedPredictions = [None for key in interactions] 
        lkfOuter = LabelKFold(documentLabels, n_folds=10)
        outerIndex = 0
        for train, test in lkfOuter:
            outerIndex += 1
            print "Outer loop", outerIndex, (len(train), len(test))
            trainDocumentLabels = [documentLabels[i] for i in train]
            train_y = [y_all[i] for i in train]
            train_X = [X_all[i] for i in train]
            print "GridSearchCV inner loop, size =", len(trainDocumentLabels)
            lkfInner = LabelKFold(trainDocumentLabels, n_folds=5)
            verbose = 0
            n_jobs = 3
            metric = "roc_auc"
            #clf = GridSearchCV(SVC(C=1), {"C":[0.001,0.01,0.1,0.5,1,5,10,100,1000,10000]}, cv=lkfInner, verbose=verbose, n_jobs=n_jobs)
            clf = GridSearchCV(SVC(C=1), {"C":[0.001,0.01,0.1,1,10,100,1000,10000], "kernel":["rbf"]}, cv=lkfInner, verbose=verbose, n_jobs=n_jobs, scoring=metric)
            #clf = GridSearchCV(SVC(C=1), {"C":[0.001,0.01,0.1,1,10,100,1000,10000], "kernel":["linear", "sigmoid", "rbf", "poly"]}, cv=lkfInner, verbose=verbose, n_jobs=n_jobs)
            #clf = GridSearchCV(ExtraTreesClassifier(), {"n_estimators":[1,2,10,50,100]}, cv=lkfInner)
            #clf = GridSearchCV(DecisionTreeClassifier(), {"criterion":["gini"]}, cv=lkfInner, verbose=verbose, n_jobs=n_jobs)
            #clf = GridSearchCV(KNeighborsClassifier(), {"n_neighbors":[1, 5, 10, 20, 50, 100, 150, 200]}, cv=lkfInner, verbose=verbose, n_jobs=n_jobs)
            #clf = GridSearchCV(GaussianNB(), {}, cv=lkfInner, verbose=verbose, n_jobs=n_jobs)
            #clf = GridSearchCV(Perceptron(), {}, cv=lkfInner, verbose=verbose, n_jobs=n_jobs)
            #clf = GridSearchCV(GradientBoostingClassifier(), {"n_estimators":[1,2,10,50,100]}, cv=lkfInner)
            #clf = GridSearchCV(SGDClassifier(), {}, cv=lkfInner)
            #clf = GridSearchCV(BernoulliNB(), {}, cv=lkfInner)
            #clf = GridSearchCV(NearestCentroid(), {}, cv=lkfInner, verbose=verbose, n_jobs=n_jobs)
            clf.fit(train_X, train_y)
            print "Best params", (clf.best_params_, clf.best_score_)
            print "Predicting the outer loop test fold"
            test_X = [X_all[i] for i in test]
            testPredictions = clf.predict(test_X)
            for prediction, index in zip(testPredictions, test):
                assert learnedPredictions[index] == None
                learnedPredictions[index] = prediction
    
    # Evaluate the performance for the different combination modes
    if not concise: print "===============", "Performance", "==============="
    results = []
    evaluatePerformance(y_all, [-1 if (interactions[key]["a"].get("type") == "neg") else 1 for key in interactions], results, "Performance for dataset a, " + inputA, "A", verbose=not concise)
    evaluatePerformance(y_all, [-1 if (interactions[key]["b"].get("type") == "neg") else 1 for key in interactions], results, "Performance for dataset b, " + inputB, "B", verbose=not concise)
    for mode in ("AND", "OR"):
        evaluatePerformance(y_all, getSimpleCombinedPredictions(interactions, mode), results, "Performance for simple combination " + mode, mode, verbose=not concise)
    if learning:
        assert None not in learnedPredictions
        evaluatePerformance(y_all, learnedPredictions, results, "Outer loop results", "LEARN", verbose=not concise)
    
    # Sort the different results by performance
    print "===============", "Sorted Results", "==============="
    results = sorted(results, reverse=True)
    for result in results:
        print result[0:3]
    
    # Save the combined output file
    if outPath != None:
        outResult = None
        print "===============", "Writing Output", "==============="
        if outMode != None:
            print "Result '" + str(outMode) + "' will be used for output"
            for result in results:
                if result[1] == outMode:
                    outResult = result
                    break
            if outResult == None:
                raise Exception("No result for output mode '" + str(outMode) + "'")
        else:
            print "The result with the best performance will be used for output"
            outResult = results[0]
        print "Saving result:", outResult[0:3], "to", outPath
        writeOutput(a, outResult[3], outPath)

if __name__=="__main__":       
    from optparse import OptionParser
    optparser = OptionParser(description="Combine relation predictions (All input files must include both positive and negative interaction elements)")
    optparser.add_option("-p", "--dataPath", default=os.path.expanduser("~/data/CAFA3/data"), help="")
    optparser.add_option("-a", "--nnInput", default=None)
    optparser.add_option("-b", "--clsInput", default=None)
    optparser.add_option("-g", "--gold", default=None)
    optparser.add_option("-o", "--output", default=None)
    optparser.add_option("-l", "--learning", default=False, action="store_true")
    optparser.add_option("-w", "--write", default="OR")
    optparser.add_option("--concise", default=False, action="store_true", dest="concise", help="")
    optparser.add_option("--subsetFrom", default="a")
    (options, args) = optparser.parse_args()
    
    assert options.write in ("AUTO", "LEARN", "AND", "OR")
    if options.write == "AUTO":
        options.write = None
    if options.output and options.gold == None and options.write == None:
        raise Exception("Write mode must be defined if no gold data is available")  
    
    combine(dataPath=options.dataPath, nnInput=options.nnInput, clsInput=options.clsInput)