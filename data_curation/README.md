# DIBBS Text to Code (TTC) - Data Curation

## Table of Contents

## Overview

The `data_curation` folder contains scripts for TTC model development, tuning, and evaluation.  

## Scripts

### terminology_valueset_sync.py

Contains various functions to pull data from SNOMED, LOINC, and HL7 APIs to provide data for the TTC model. For detailed instructions on how to use the various scripts [see link section below](#terminology-valueset-sync-script)

### augmentation.py

A gathering of various functions to modify data from the different terminology data sets to help with model training and tuning.


## Data Files

- LOINC:
   - [Lab Orders](../data/snoinc_extracts/loinc_lab_orders_20250926.csv) - LOINC provides codes that represent the specific clinical concept of the test being ordered, or in other words a request made to a laboratory to perform a specific test or panel of tests.   In HL7v2 this would be the equivalent of an OBR.

   Date Structure:

      `code|short_name|long_name|display_name|definition_desc|related_names`


      - Code: A unique identifier for a specific test or observation, typically in a 5-digit-then-a-dash format (e.g., 806-0). 
      - Short Name: A concise name used for quick displays, such as in a report's column header. 
      - Long Name (Long Common Name): A more readable, expanded version of the LOINC concept, created to be user-friendly for clinicians. 
      - Display Name: A flexible field that can be the Long Common Name, Short Name, or another name for the term, depending on how the user or system wants to present it. 
      - Definition Description (Fully-Specified Name): The formal, six-part description that provides the complete and standardized meaning of the observation. 
      - Related Names: This category can include various other terms or synonyms used to describe the same test or observation, helping to map local codes to the LOINC standard. List of terms is `;` delimited.

   - [Lab Results](../data/snoinc_extracts/loinc_lab_result_20250926.csv) - The LOINC code identifies the performed test, the actual information or observation that comes back from the laboratory after the order has been fulfilled, and is combined with a result value and unit of measure (See other valuesets for more information) to form the complete lab result.   In HL7v2 this would be the equivalent of an OBX.
   - [Lab Names](../data/snoinc_extracts/loinc_lab_names_20250926.csv) - The LOINC codes and terms for both Lab Orders and Lab Results in a single set.  This is primarily used to satisfy the models used for determining the correct code for Lab Orders and Resulting Labs in TTC.
   - 


## Instructions

### Terminology ValueSet Sync Script

### RELMA DB