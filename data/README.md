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

- `build_evaluation_files.py` creates the files required to complete the evaluation using the eRSD.
- `oid_to_conditions.txt` is a json file that logs the OID-SNOMED condition ID key-pairs.
- `loinc_to_oids.txt` is a json file that logs the LOINC code to the array of 1+ OIDs that leverage that LOINC code.
- `add_loinc_codes.py` adds LOINC codes to a JSONL that only has the display name for the expected and returned text fields. This will probably be deprecated once we add LOINC codes to the embedding files to avoid 1000s of calls to the LOINC API.
- `evaluation.py` is a script that takes a JSON containing the expected and returned LOINC codes and runs a comparison to determine the accuracy of a match. More information on the criteria to determine the degree of correctness of a match can be found here: https://docs.google.com/document/d/1yA5NJ06mf1EfLZRmNrrNKopWL6ExMj-dPYKy8wlVDGs/edit?tab=t.0#heading=h.rn5y5vzcin6p.
- `/accuracy_evaluation/sample_data/` is a folder that contains small portions of data to confirm the efficacy of the `evaluation.py` script.
  - `eval_results_snippet.jsonl` is a portion of the output of the `performance.ipynb` notebook that currently lacks the LOINC codes. `eval_results_snippet_with_loinc_codes.json` is the created output of the `add_loinc_codes.py` script that can be used with the `evaluation.py` script; `evaluation_results_eval_results_snippet_with_loinc_codes.json` is the result.
  - `sample_evaluation_file.txt` is a dummy file that can be run against the evaluation script to confirm the logic for a first-, second-, and third-degree match; `evaluation_results_sample_evaluation_file.json` is the output file.
