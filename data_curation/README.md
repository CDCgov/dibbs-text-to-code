# DIBBS Text to Code (TTC) - Data Curation

## Table of Contents
[[_TOC_]]

## Overview

The `data_curation` folder contains scripts for TTC model development, tuning, and evaluation.  Most of the scripts leverage data that is being pulled from the LOINC, UMLS, and HL7 APIs.  However, some require the LOINC RelmaDB (MS-Access database).

## Scripts

### terminology_valueset_sync.py

Contains various functions to pull data from SNOMED, LOINC, and HL7 APIs to provide data for the TTC model. For detailed instructions on how to use the various scripts [see instruction section below](#instructions)

### augmentation.py

A gathering of various functions to modify data from the different terminology data sets to help with model training and tuning.  Functions that randomly scramble words, randomly delete characters, and randomly replacing words with related terms are included.  The `configs.py` is leveraged to allow the user to configure the various parameters/properties for these random data modification functions.

### configs.py

A collection of various configurations used to augment data and/or create synthetic data, using the terminology data sets.

### generation.py

A script to house functions that can be used to generate data sets used to help train and tune the data models.  ie. `Generate Positive Pairs` - Given the location of one or more files of LOINC codes and some corresponding augmented examples for those codes, this function compiles a list of positive pairs that can be read for model training. A positive pair is a tuple of the form (original_loinc_code, augmented_example_of_code).

### synthetic_lab_results.py

Generate a CSV of synthetic lab results with labeled values. Each row contains a randomized result word (e.g., "positive", "not detected")
and a label: 1 for positive terms, 2 for negative terms. Optionally, the cript can introduce randomized case changes and typos.

### loinc (folder)

Contains .sql queries/files that are used to gather data from LOINC's RELMA database (MS-Access), as well as the resulting data files that are used to generate some of the data files.


## Data Files

### LOINC:

These data files are for the Lab codes/concepts in LOINC for the base TTC model.

- **Data Structure:** `code|short_name|long_name|display_name|definition_desc|related_names`
   - Code: A unique identifier for a specific test or observation, typically in a 5-digit-then-a-dash format (e.g., 806-0). 
   - Short Name: A concise name used for quick displays, such as in a report's column header. 
   - Long Name (Long Common Name): A more readable, expanded version of the LOINC concept, created to be user-friendly for clinicians. 
   - Display Name: A flexible field that can be the Long Common Name, Short Name, or another name for the term, depending on how the user or system wants to present it. 
   - Definition Description (Fully-Specified Name): The formal, six-part description that provides the complete and standardized meaning of the observation. 
   - Related Names: This category can include various other terms or synonyms used to describe the same test or observation, helping to map local codes to the LOINC standard. List of terms is `;` delimited.

- [Lab Orders](../data/snoinc_extracts/loinc_lab_orders_20250926.csv) - LOINC provides codes that represent the specific clinical concept of the test being ordered, or in other words a request made to a laboratory to perform a specific test or panel of tests.   In HL7v2 this would be the equivalent of an OBR.   

- [Lab Results](../data/snoinc_extracts/loinc_lab_result_20250926.csv) - The LOINC code identifies the performed test, the actual information or observation that comes back from the laboratory after the order has been fulfilled, and is combined with a result value and unit of measure (See other valuesets for more information) to form the complete lab result.   In HL7v2 this would be the equivalent of an OBX.
   
- [Lab Names](../data/snoinc_extracts/loinc_lab_names_20250926.csv) - The LOINC codes and terms for both Lab Orders and Lab Results in a single set.  This is primarily used to satisfy the models used for determining the correct code for Lab Orders and Resulting Labs in TTC.

### LOINC Part Synonyms & Abbreviations

These data files are organizing all the possible abbreviations and synonyms for all the particular LOINC Part codes/concepts into a single JSON/Dictionary file.

LOINC terms are comprised of six parts, defining a specific clinical observation or measurement: Component (the analyte), Property (the characteristic being measured), Time Aspect (when it was measured), System (the specimen or source), Scale (how the result is expressed), and Method (how it was measured). These parts, joined by colons, create a fully specified name that provides clarity and standardization for clinical data exchange.  

Each part provides unique information about the test or observation: 
- [Component](../data/snoinc_extracts/loinc_component_abbrv_syn_20250926.json): What is being measured (e.g., glucose, a specific organ part). 
- [Property](../data/snoinc_extracts/loinc_property_abbrv_syn_20250926.json): The specific attribute of the component being measured (e.g., length, mass, number). 
- [Time Aspect](../data/snoinc_extracts/loinc_time_abbrv_syn_20250926.json): The time frame or duration over which the measurement was made. 
- [System](../data/snoinc_extracts/loinc_system_abbrv_syn_20250926.json): The specimen source or origin of the measurement (e.g., serum, plasma, blood). 
- [Scale](../data/snoinc_extracts/loinc_scale_abbrv_syn_20250926.json): How the result is reported (e.g., quantitative for numbers, ordinal for ranked categories, narrative for text). 
- [Method](../data/snoinc_extracts/loinc_method_abbrv_syn_20250926.json): The technique or procedure used to perform the measurement. This part is the only one that is not mandatory for every LOINC term. 

- **Data Structure:**
```{
   ...
   {
   "Clinical biochemical genetics": {
        "code": "LP134112-4",
        "abbrv": [
            "Clinic biochem gen"
        ],
        "synonyms": [
            "Medical biochemical genomics",
            "Clinical biochem genetics",
            "Medical biochemical genetics",
            "Clinical biochemical genomics"
        ]
    },
```
   - Key: LOINC Part Short Name
   - Code: The LOINC Part unique identifier, starting with LP then typically in a 6-digit-then-a-dash format (e.g., LP806123-0).
   - Abbrv: A list of abbreviations for the specific LOINC Part.
   - Synonym: A list of synonyms for the specific LOINC Part.

### LOINC Part Descriptions

This is a data file that contains LOINC codes/concepts that also have a LOINC Part descriptions that give a more in-depth description of the LOINC Lab code/concept.  Not all LOINC codes/concepts will have a result in this data file.  A custom [sql query](./loinc/loinc_codes_with_part_descriptions.sql) was created to extract this data from the LOINC RELMA database, as the results weren't possible to be extracted using the LOINC API.

- **Data Structure**: (CSV) `LOINC_NUM,DESCRIPTION`
   - Loinc num: A unique identifier for a specific test or observation, typically in a 5-digit-then-a-dash format (e.g., 806-0).
   - Description: The description pulled for the 'Component Core' Part for correlating LOINC codes/concept.

- [LOINC Codes with Part Descriptions](../data/snoinc_extracts/loinc_codes_with_part_descriptions.csv)

_**NOTE: we can easily change this to be a file with any delimiter instead of a `,`**_

### SNOMED

These data files are for the various codes/concepts in SNOMED used to be the base of the TTC model.

- **Data Structure**: `code|text`
   - Code: These are unique numerical identifiers for clinical concepts, such as a specific disease, a symptom, or a procedure.
   - Text: Each concept code is associated with one or more textual descriptions that human-readable terms for the concept. A concept can have several descriptions, including synonyms, which represent the same clinical idea.  For this data file there will just be a single text, the common name/term/description, associated with each code.

- [Lab Values](../data/snoinc_extracts/snomed_lab_value_20250926.csv) - SNOMED CT does not code the specific quantitative values of lab results (e.g., "glucose 105 mg/dL") but rather provides codes for the qualitative interpretation of a result (e.g., positive, negative, abnormal). The quantitative value and its units are typically stored separately in the health record. 


### HL7

These data files are for the various codes & displays from various HL7 ValueSets and CodeSystems used in the base of the TTC model.

- **Data Structure**: `code|text`
   - Code: The unique machine-readable identifier for a concept.
   - Text: Human-readable text describing the concept.

- [Lab Interpretations](../data/snoinc_extracts/hl7_lab_interp_20250926.csv) - In an HL7 message, the value from the ObservationInterpretation code system and/or a value set derived from it is used to provide additional context to the reported lab result. For instance, alongside a quantitative lab value, an interpretation code might indicate whether the result is "High" or "Low". This helps clinicians understand the significance of a result without having to interpret raw data themselves. 


## Instructions

### Generating SNOINC Extracts

