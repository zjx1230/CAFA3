from Task import Task
from learning.featureBuilders import *

class CAFA3Task(Task):
    def __init__(self):
        Task.__init__(self)
        
        self.allowMissing = False
        self.limitTrainingToAnnotated = True
        
        self.sequencesPath = "Swiss_Prot/Swissprot_sequence.tsv.gz"
        self.targetsPath = "CAFA3_targets/Target_files/target.all.fasta"
        self.annotationsPath = "Swissprot_propagated.tsv.gz"
        self.splitPath = "data"
        self.foldsPath = "folds/training_folds_170125.tsv.gz"
        self.termsPath = "GO/go_terms.tsv"
        
        self.features = {
            "taxonomy":TaxonomyFeatureBuilder(["Taxonomy"]),
            "similar":UniprotFeatureBuilder("Uniprot/similar.txt"),
            "blast":BlastFeatureBuilder(["temp_blastp_result_features", "blastp_result_features"]),
            "blast62":BlastFeatureBuilder(["CAFA2/training_features", "CAFA2/CAFA3_features"], tag="BLAST62"),
            "delta":BlastFeatureBuilder(["temp_deltablast_result_features", "deltablast_result_features"], tag="DELTA"),
            "interpro":InterProScanFeatureBuilder(["temp_interproscan_result_features", "interproscan_result_features"]),
            "predgpi":PredGPIFeatureBuilder(["predGPI"]),
            "nucpred":NucPredFeatureBuilder(["nucPred"]),
            "netacet":NetAcetFeatureBuilder(["NetAcet"]),
            "funtaxis":FunTaxISFeatureBuilder(["FunTaxIS"]),
            "ngrams":NGramFeatureBuilder(["ngrams/4jari/min_len3-min_freq2-min1fun-top_fun5k"])
        }
        self.defaultFeatures = ["all", "-funtaxis", "-ngrams", "-similar"]

class CAFA3HPOTask(CAFA3Task):
    def __init__(self):
        CAFA3Task.__init__(self)
        
        self.allowMissing = True        
        self.annotationsPath = "HPO/annotation/all_cafa_annotation_propagated.tsv.gz"
        self.termsPath = "HPO/ontology/hp.obo"

class CAFAPITask(Task):
    def __init__(self):
        Task.__init__(self)
        
        self.remapSets = {"test":"devel"}
        self.allowMissing = True
        self.limitTrainingToAnnotated = False
        
        self.sequencesPath = "CAFA_PI/Swissprot/CAFA_PI_Swissprot_sequence.tsv.gz"
        self.targetsPath = "CAFA_PI/Swissprot/target.all.fasta.gz"
        self.annotationsPath = "CAFA_PI/Swissprot/CAFA_PI_Swissprot_propagated.tsv.gz"
        self.splitPath = "CAFA_PI/Swissprot"
        self.foldsPath = "folds/CAFA_PI_training_folds_180417.tsv.gz"
        self.termsPath = "GO/go_terms.tsv"
        
        self.features = {
            "taxonomy":TaxonomyFeatureBuilder(["CAFA_PI/features/Taxonomy"]),
            "blast":BlastFeatureBuilder(["CAFA_PI/features/temp_blastp_result_features", "CAFA_PI/features/blastp_result_features"]),
            "blast62":BlastFeatureBuilder(["CAFA_PI/features/CAFA2/training_features", "CAFA_PI/features/CAFA2/CAFA3_features"], tag="BLAST62"),
            "delta":BlastFeatureBuilder(["CAFA_PI/features/temp_deltablast_result_features", "CAFA_PI/features/deltablast_result_features"], tag="DELTA"),
            "interpro":InterProScanFeatureBuilder(["CAFA_PI/features/temp_interproscan_result_features", "CAFA_PI/features/interproscan_result_features"]),
            "predgpi":PredGPIFeatureBuilder(["CAFA_PI/features/predGPI"]),
            "nucpred":NucPredFeatureBuilder(["CAFA_PI/features/nucPred"]),
            "netacet":NetAcetFeatureBuilder(["CAFA_PI/features/NetAcet"])
        }
        self.defaultFeatures = ["all"]

# Register the tasks
Task.registerTask(CAFA3Task, "cafa3")
Task.registerTask(CAFA3HPOTask, "cafa3hpo")
Task.registerTask(CAFAPITask, "cafapi")