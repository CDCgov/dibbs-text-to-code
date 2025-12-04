# DIBBS Text to Code Data

## Table of Contents

- [Overview](#overview)

## Overview

The `data` folder contains publicly available, synthetic, and augmented data used in
TTC model development, tuning, and evaluation.

Data extracted from queries, API calls, or other pulls from LOINC, SNOMED, and HL7 Valueset resources are categorized under
`/snoinc_extracts`.

- For more details read [here](../data_curation/README.md)
- To generate these SNOINC Extract Files refer to this [README](../data_curation/README.md#instructions)

Data created as part of curation, augmentation, or synthetic generation for model training and evaluation is categorized under
`/training_files/`.

Data used to evaluate the accuracy of codes assigned by the TTC model to the expected codes and is categoried under `/accuracy_evaluation`.

- `build_eval_files.py` creates the files required to complete the evaluation using the eRSD.
- `oid_to_conditions.txt` is a json file that logs the OID-SNOMED condition ID key-pairs.
- `loinc_to_oids.txt` is a josn file that logs the LOINC code to the array of 1+ OIDs that leverage that LOINC code.
