from data_curation.schemas.loinc_struct import LoincStruct, LabType

FENTANYL_STRUCT = LoincStruct(
    long_common_name = "fentaNYL [Presence] in Urine by Screen method",
    short_name = "fentaNYL Ur Ql Scn", 
    display_name = "fentaNYL Screen Ql (U)", 
    consumer_name = "fentaNYL, Urine", 
    fully_specified_name = "fentaNYL:PrThr:Pt:Urine:Ord:Screen", 
    lab_type = LabType.BOTH, 
    class_type = "DRUG/TOX", 
    property = "PrThr", 
    time = "Pt", 
    system = "Urine", 
    scale = "Ord", 
    method = "Screen"
)

ERYTHROCYTES_STRUCT = LoincStruct(
    long_common_name = "Erythrocytes [#/volume] in Blood by Automated count",
    short_name = "RBC # Bld Auto", 
    display_name = "RBC Auto (Bld) [#/Vol]", 
    consumer_name = "Red Blood Cell (RBC) Count, Blood", 
    fully_specified_name = "Erythrocytes:NCnc:Pt:Bld:Qn:Automated count", 
    lab_type = LabType.BOTH, 
    class_type = "HEM/BC", 
    property = "NCnc", 
    time = "Pt", 
    system = "Bld", 
    scale = "Qn", 
    method = "Automated count"
)

CBC_STRUCT = LoincStruct (
    long_common_name = "CBC W Auto Differential panel - Blood",
    short_name = "CBC W Auto Diff Bld", 
    display_name = "CBC W Auto Differential panel (Bld)", 
    consumer_name = "CBC W Auto Differential Panel, Blood", 
    fully_specified_name = "Complete blood count W Auto Differential panel:-:Pt:Bld:Qn:", 
    lab_type = LabType.ORDER, 
    class_type = "PANEL.HEM/BC", 
    property = None, 
    time = "Pt",
    system = "Bld", 
    scale = "Qn", 
    method = None
)