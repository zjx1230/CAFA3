import csv
import numpy as np
import gzip
from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score
from collections import defaultdict

def evaluate(labels, predicted, examples, terms=None, averageOnly=False, average="micro", noAUC=False):
    print "Evaluating the predictions"
    results = {}
    print "Calculating average scores"
    results["average"] = {"id":"average", "ns":None, "name":None, "auc":0, "tp":None, "fp":None, "fn":None, "tn":None}
    if not noAUC:
        try:
            results["average"]["auc"] = roc_auc_score(labels, predicted, average="micro")
        except ValueError as e:
            print e
    results["average"]["fscore"] = f1_score(labels, predicted, average=average)
    results["average"]["precision"] = precision_score(labels, predicted, average=average)
    results["average"]["recall"] = recall_score(labels, predicted, average=average)
    if averageOnly:
        return results
    
    print "Calculating label scores"
    label_names = examples["label_names"]
    label_size = examples.get("label_size")
    label_args = examples.get("label_args")
    try:
        aucs = roc_auc_score(labels, predicted, average=None)
    except (TypeError, ValueError) as e:
        print e
        aucs = [0] * len(label_names)
    fscores = f1_score(labels, predicted, average=None)
    precisions = precision_score(labels, predicted, average=None)
    recalls = recall_score(labels, predicted, average=None)
    lengths = [len(x) for x in (aucs, fscores, precisions, recalls, label_names)]
    assert len(set(lengths)) == 1, lengths
    for auc, fscore, precision, recall, label_name in zip(aucs, fscores, precisions, recalls, label_names):
        assert label_name not in results
        result = {"id":label_name, "ns":None, "name":None, "auc":auc, "precision":precision, "recall":recall, "fscore":fscore, "tp":0, "fp":0, "fn":0, "tn":0}
        results[label_name] = result
        if label_size != None and label_name in label_size:
            result["label_size"] = label_size[label_name]
        if label_args != None and label_name in label_args:
            result["label_args"] = label_args[label_name]
        if terms != None and label_name in terms:
            term = terms[label_name]
            result["ns"] = term["ns"]
            result["name"] = term["name"]
    print "Counting label instances"
    stats = {x:{"tp":0, "fp":0, "fn":0, "tn":0} for x in label_names}
    label_indices = range(len(label_names))
    for gold, pred in zip(labels, predicted):
        for i in label_indices:
            stats[label_names[i]][getMatch(gold[i], pred[i])] += 1
    for key in stats:
        results[key].update(stats[key])
    return results

def resultIsBetter(original, new, key="average"):
    if new[key]["fscore"] != original[key]["fscore"]:
        return new[key]["fscore"] > original[key]["fscore"]
    else:
        return new[key]["auc"] > original[key]["auc"]
        
# def countInstances(labels, predicted):
#     tp = labels.multiply(predicted)
#     tp = labels.multiply(predicted)

def metricsToString(result, style="%.3f"):
    hasCounts = any([result.get(x) != None for x in ("tp", "fp", "tn", "fn")])
    s = "a/f|p/r"
    if hasCounts:
        s += "|tp/fp/tn/fn"
    s += " = " + style % result["auc"] + "/" + style % result["fscore"] + "|" + style % result["precision"] + "/" + style % result["recall"]
    if hasCounts:
        s += "|" + "/".join([str(result.get(x, "-")) for x in ("tp", "fp", "tn", "fn")])
    return s

def getResultsString(results, maxNumber=None, skipIds=None, sortBy="fscore"):
    count = 0
    s = ""
    for result in sorted(results.values(), key=lambda x: (x[sortBy], x["fp"]), reverse=True):
        if skipIds != None and result["id"] in skipIds:
            continue
        s += metricsToString(result) + " " + str([result.get("id"), result.get("ns"), result.get("label_size"), result.get("name")]) + "\n"
        count += 1
        if count > maxNumber:
            break
    return s

def getResultsTable(results, maxNumber=None, skipIds=None, sortBy="fscore"):
    count = 0
    s = ""
    for result in sorted(results.values(), key=lambda x: (x[sortBy], x["fp"]), reverse=True):
        if skipIds != None and result["id"] in skipIds:
            continue
        values = ["%.3f" % result[x] for x in ("fscore", "precision", "recall")]
        values += [str(result.get(x, "-")) for x in ("tp", "fp", "tn", "fn")]
        values += [result.get("id"), result.get("ns"), str(result.get("label_size")), result.get("name")]
        s += " & ".join([str(x) for x in values]) + "\\\\\n"
        count += 1
        if count > maxNumber:
            break
    s = s.replace("_", "\_")
    return s

def saveProteins(proteins, outPath, limitTerms=None, limitToSets=None, predKey="predictions"):
    print "Writing results to", outPath
    counts = defaultdict(int)
    with gzip.open(outPath, "wt") as f:
        dw = csv.DictWriter(f, ["id", "label_index", "label", "predicted", "confidence", "gold", "match", "cafa_ids", "ensemble"], delimiter='\t')
        dw.writeheader()
        filtered = {"labels":set(), "predictions":set()}
        for protId in sorted(proteins.keys()):
            protein = proteins[protId]
            rows = []
            if limitToSets != None and not any(x in limitToSets for x in protein["sets"]):
                counts["skipped-proteins"] += 1
                continue
            counts["proteins"] += 1
            goldLabels = protein["terms"].keys()
            if predKey not in protein:
                counts["proteins-with-no-predictions"] += 1
            predLabels = protein.get(predKey, {}).keys()
            if limitTerms:
                filtered["labels"].update([x for x in goldLabels if x not in limitTerms])
                goldLabels = [x for x in goldLabels if x in limitTerms]
                filtered["predictions"].update([x for x in predLabels if x not in limitTerms])
                predLabels = [x for x in predLabels if x in limitTerms]
            allLabels = sorted(set(goldLabels + predLabels))
            predLabels = set(predLabels)
            goldLabels = set(goldLabels)
            cafa_ids = ",".join(protein["cafa_ids"])
            predConf = protein.get(predKey + "_conf", {})
            predSources = protein.get(predKey + "_sources", {})
            hasPred = False
            hasGold = False
            seenSources = set()
            for label in allLabels:
                pred = 1 if label in predLabels else 0
                if pred == 1:
                    hasPred = True
                gold = 1 if label in goldLabels else 0
                if gold == 1:
                    hasGold = True
                conf = predConf.get(label, 0.01) if (pred == 1) else 0 # Use a low confidence for BLAST baseline transfer
                match = getMatch(gold, pred)
                sources = predSources.get(label, [])
                for source in sources:
                    counts["source-" + source] += 1
                    seenSources.add(source)
                ensemble = ",".join(sources)
                rows.append({"id":protId, "label_index":None, "label":label, "predicted":pred, "gold":gold,
                             "confidence":conf, "match":getMatch(gold, pred), "cafa_ids":cafa_ids, "ensemble":ensemble})
                counts["rows"] += 1
                counts[match] += 1
                counts["pred_" + str(pred)] += 1
                counts["gold_" + str(gold)] += 1
            if hasPred:
                counts["proteins-with-predictions"] += 1
            if hasGold:
                counts["proteins-with-gold"] += 1
            counts["proteins-with-sources:" + str(sorted(seenSources))] += 1
            dw.writerows(rows)
    counts.update({"filtered-" + x:len(filtered[x]) for x in filtered})
    print "Results written,", dict(counts)

def saveResults(data, outStem, label_names, negatives=False, feature_names=None):
    print "Writing results to", outStem + "-results.tsv"
    with open(outStem + "-results.tsv", "wt") as f:
        dw = csv.DictWriter(f, ["auc", "fscore", "precision", "recall", "tp", "fp", "tn", "fn", "id", "label_size", "ns", "name", "label_args"], delimiter='\t')
        dw.writeheader()
        dw.writerow(data["results"]["average"])
        results = [x for x in data["results"].values() if x["id"] != "average"]
        dw.writerows(sorted(results, key=lambda x: x["auc"], reverse=True))
    savePredictions(data, label_names, outStem + "-predictions.tsv.gz", negatives=negatives)
    print "Writing ids to", outStem + "-ids.tsv"
    with open(outStem + "-ids.tsv", "wt") as f:
        dw = csv.DictWriter(f, ["id", "cafa_ids", "gold", "predicted"], delimiter='\t')
        dw.writeheader()
        dw.writerows([{"id":protId, "cafa_ids":",".join(cafa_ids), "gold":np.count_nonzero(gold), "predicted":np.count_nonzero(pred)} for protId, cafa_ids, gold, pred in zip(data["ids"], data["cafa_ids"], data["gold"], data["predicted"])])
    if feature_names != None:
        print "Writing importances to", outStem + "-importances.tsv.gz"
        with gzip.open(outStem + "-importances.tsv.gz", "wt") as f:
            dw = csv.DictWriter(f, ["index", "name", "importance"], delimiter='\t')
            dw.writeheader()
            importances = [{"index":i, "name":feature_names[i], "importance":data["feature_importances"][i]} for i in range(len(data["feature_importances"]))]
            importances.sort(key=lambda k: k['importance'], reverse=True) 
            dw.writerows(importances)

def getMatch(gold, predicted):
    if gold == predicted:
        return "tp" if (gold == 1) else "tn"
    else:
        return "fn" if (gold == 1) else "fp"

def savePredictions(data, label_names, outPath, negatives=False):
    print "Writing predictions to", outPath
    keys = ["ids", "gold", "predicted", "cafa_ids"]
    hasProbabilities = data.get("probabilities") != None
    if hasProbabilities:
        lengths = [len(data["probabilities"]), len(label_names)]
        assert len(set(lengths)) == 1, lengths #keys += ["probabilities"]
    lengths = [len(data[x]) for x in keys]
    assert len(set(lengths)) == 1, lengths
    label_indices = range(len(label_names))
    
#     n_samples = data["probabilities"][0].shape[0]
#     label_names_array = np.array(label_names)
#     n_outputs = len(label_names_array)
#     predictions = np.zeros((n_samples, n_outputs))
#     for k in range(n_outputs):
#         predictions[:, k] = label_names_array[k].take(np.argmax(data["probabilities"][k], axis=1), axis=0)
    
    with gzip.open(outPath, "wt") as f:
        dw = csv.DictWriter(f, ["id", "label_index", "label", "predicted", "confidence", "gold", "match", "cafa_ids"], delimiter='\t')
        dw.writeheader()
        rows = []
        for i in range(len(data["ids"])):
            gold = data["gold"][i]
            pred = data["predicted"][i]
            cafa_ids = ",".join(data["cafa_ids"][i])
            for labelIndex in label_indices:
                goldValue = gold[labelIndex]
                predValue = int(pred[labelIndex])
                if negatives or (goldValue == 1 or predValue == 1):
                    row = {"id":data["ids"][i], "label_index":labelIndex, "label":label_names[labelIndex], "gold":goldValue, "predicted":predValue, "cafa_ids":cafa_ids}
                    row["match"] = getMatch(goldValue, predValue)
                    row["confidence"] = max(data["probabilities"][labelIndex][i]) if hasProbabilities else None #data["probabilities"][labelIndex][i] if hasProbabilities else None
                    #row["pred2"] = predictions[i][labelIndex]
                    rows.append(row)
            if len(rows) >= 100000:
                dw.writerows(rows)
                rows = []
        if len(rows) >= 0:
            dw.writerows(rows)