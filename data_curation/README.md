# DIBBS Text to Code (TTC) - Data Curation

## Table of Contents
[[_TOC_]]

## Overview

The `data_curation` folder contains scripts for TTC model development, tuning, and evaluation.  Most of the scripts leverage data that is being pulled from the LOINC, UMLS, and HL7 APIs.  However, some require the LOINC RelmaDB (MS-Access database).

## Scripts

### terminology_valueset_sync.py

Contains various functions to pull data from SNOMED, LOINC, and HL7 APIs to provide data for the TTC model. For detailed instructions on how to use the various scripts [see instruction section below](#terminology-valueset-sync-script)

### augmentation.py

A gathering of various functions to modify data from the different terminology data sets to help with model training and tuning.  Functions that randomly scramble words, randomly delete characters, and randomly replacing words with related terms are included.  The `configs.py` is leveraged to allow the user to configure the various parameters/properties for these random data modification functions.

### configs.py

A collection of various configurations used to augment data and/or create synthetic data, using the terminology data sets.

### generation.py

A script to house functions that can be used to generate data sets used to help train and tune the data models.  ie. `Generate Positive Pairs` - Given the location of one or more files of LOINC codes and some corresponding augmented examples for those codes, this function compiles a list of positive pairs that can be read for model training. A positive pair is a tuple of the form (original_loinc_code, augmented_example_of_code).

### synthetic_lab_results.py

Generate a CSV of synthetic lab results with labeled values. Each row contains a randomized result word (e.g., "positive", "not detected")
and a label: 1 for positive terms, 2 for negative terms. Optionally, the cript can introduce randomized case changes and typos.


## Data Files

### LOINC:

- [How to generate](#loinc-1)
- Data Structure: `code|short_name|long_name|display_name|definition_desc|related_names`
   - Code: A unique identifier for a specific test or observation, typically in a 5-digit-then-a-dash format (e.g., 806-0). 
   - Short Name: A concise name used for quick displays, such as in a report's column header. 
   - Long Name (Long Common Name): A more readable, expanded version of the LOINC concept, created to be user-friendly for clinicians. 
   - Display Name: A flexible field that can be the Long Common Name, Short Name, or another name for the term, depending on how the user or system wants to present it. 
   - Definition Description (Fully-Specified Name): The formal, six-part description that provides the complete and standardized meaning of the observation. 
   - Related Names: This category can include various other terms or synonyms used to describe the same test or observation, helping to map local codes to the LOINC standard. List of terms is `;` delimited.

- [Lab Orders](../data/snoinc_extracts/loinc_lab_orders_20250926.csv) - LOINC provides codes that represent the specific clinical concept of the test being ordered, or in other words a request made to a laboratory to perform a specific test or panel of tests.   In HL7v2 this would be the equivalent of an OBR.   

- [Lab Results](../data/snoinc_extracts/loinc_lab_result_20250926.csv) - The LOINC code identifies the performed test, the actual information or observation that comes back from the laboratory after the order has been fulfilled, and is combined with a result value and unit of measure (See other valuesets for more information) to form the complete lab result.   In HL7v2 this would be the equivalent of an OBX.
   
- [Lab Names](../data/snoinc_extracts/loinc_lab_names_20250926.csv) - The LOINC codes and terms for both Lab Orders and Lab Results in a single set.  This is primarily used to satisfy the models used for determining the correct code for Lab Orders and Resulting Labs in TTC.


## Instructions

### LOINC

### LOINC Part Synonyms & Abbreviations

### LOINC Part Descriptions

### SNOMED

### HL7