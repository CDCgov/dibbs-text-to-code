# DIBBS Text to Code Data

## Table of Contents

- [Overview](#overview)
- [Scripts](#scripts)
- [SNOINC Extract Data Files](#snoinc-extract-data-files)
   - [LOINC](#loinc)
   - [LOINC Part Synonyms & Abbreviations](#loinc-part-synonyms-&-abbreviations)
   - [LOINC Part Descriptions](#loinc-part-descriptions)
   - [LOINC UMLS Related Names](#loinc-umls-related-names)
   - [SNOMED](#snomed)
   - [HL7](#hl7)
    - [Instructions](#instructions)

## Overview

The `data` folder contains publicly available, synthetic, and augmented data used in
TTC model development, tuning, and evaluation.

Data extracted from queries, API calls, or other pulls from LOINC, SNOMED, and HL7 Valueset resources are categorized under 
`/snoinc_extracts`.

Data created as part of curation, augmentation, or synthetic generation for model training and evaluation is categorized under 
`/training_files/`.

## SNOINC Extract Data Files

### LOINC:

These data files are for the Lab codes/concepts in LOINC for the base TTC model.

#### Data Structure:

```csv
code|short_name|long_name|display_name|definition_desc|related_names
110636-8|APAP Msmt Ur|Acetaminophen [Measurement] in Urine|Acetaminophen (U) [Measurement]||ACET; Acetamidophenol; Acetaminoph; Acetominophen; APAP; c209; C55; Hydroxyacetanilide; Lab orders; Msmt; N-(4-Hydroxyphenyl)acetanilide; N-Acetyl-p-aminophenol; p-Acetamidophenol; Paracetamol; p-Hydroxyacetanilide; Tylenol; u209; UA; UR; Urn
53781-1|Acetamin+Propoxyph Pnl Ur-mCnc|Acetaminophen and Propoxyphene panel [Mass/volume] - Urine|Acetaminophen and Propoxyphene panel (U) [Mass/Vol]||ACET; Acetamidophenol; Acetamin+Propoxyph Pnl; Acetaminoph; Acetominophen; Algaphan; APAP; c209; C55; Cosalgesic; Cotonal-65; Darvocet; Darvon; Depronal; Dextrogesic; Dextropropoxyphene; Distalgesic; Dolasan; Doloxene; D-propoxyphene; DRUG/TOXICOLOGY; Drugs; Hydroxyacetanilide; Level; Mass concentration; N-(4-Hydroxyphenyl)acetanilide; N-Acetyl-p-aminophenol; Napsalgesic; p-Acetamidophenol; Pan; PANEL.DRUG & TOXICOLOGY; Panl; Paracetamol; p-Hydroxyacetanilide; Pnl; Point in time; Propoxyph pnl; QNT; Quan; Quant; Quantitative; Random; Tylenol; u209; UA; UR; Urn

```
- Code: A unique identifier for a specific test or observation, typically in a 5-digit-then-a-dash format (e.g., 806-0). 
- Short Name: A concise name used for quick displays, such as in a report's column header. 
- Long Name (Long Common Name): A more readable, expanded version of the LOINC concept, created to be user-friendly for clinicians. 
- Display Name: A flexible field that can be the Long Common Name, Short Name, or another name for the term, depending on how the user or system wants to present it. 
- Definition Description (Fully-Specified Name): The formal, six-part description that provides the complete and standardized meaning of the observation. 
- Related Names: This category can include various other terms or synonyms used to describe the same test or observation, helping to map local codes to the LOINC standard. List of terms is `;` delimited.

#### Extracts

- [Lab Orders](./snoinc_extracts/loinc_lab_orders_20250926.csv) - LOINC provides codes that represent the specific clinical concept of the test being ordered, or in other words a request made to a laboratory to perform a specific test or panel of tests.   In HL7v2 this would be the equivalent of an OBR.   

- [Lab Results](./snoinc_extracts/loinc_lab_result_20250926.csv) - The LOINC code that identifies the performed test; the actual information or observation that comes back from the laboratory after the order has been fulfilled, and is combined with a result value and unit of measure (See other valuesets for more information) to form the complete lab result.   In HL7v2 this would be the equivalent of an OBX.
   
- [Lab Names](./snoinc_extracts/loinc_lab_names_20250926.csv) - The LOINC codes and terms for both Lab Orders and Lab Results in a single set.  This is primarily used to satisfy the models used for determining the correct code for Lab Orders and Resulting Labs in TTC.

---

### LOINC Part Synonyms & Abbreviations

These data files are organizing all the possible abbreviations and synonyms for all the particular LOINC Part codes/concepts into a single JSON/Dictionary file.

LOINC terms are comprised of six parts, defining a specific clinical observation or measurement: Component (the analyte), Property (the characteristic being measured), Time Aspect (when it was measured), System (the specimen or source), Scale (how the result is expressed), and Method (how it was measured). These parts, joined by colons, create a fully specified name that provides clarity and standardization for clinical data exchange.  

#### Extracts

Each part provides unique information about the test or observation: 
- [Component](./snoinc_extracts/loinc_component_abbrv_syn_20250926.json): What is being measured (e.g., glucose, a specific organ part). 
- [Property](./snoinc_extracts/loinc_property_abbrv_syn_20250926.json): The specific attribute of the component being measured (e.g., length, mass, number). 
- [Time Aspect](./snoinc_extracts/loinc_time_abbrv_syn_20250926.json): The time frame or duration over which the measurement was made. 
- [System](./snoinc_extracts/loinc_system_abbrv_syn_20250926.json): The specimen source or origin of the measurement (e.g., serum, plasma, blood). 
- [Scale](./snoinc_extracts/loinc_scale_abbrv_syn_20250926.json): How the result is reported (e.g., quantitative for numbers, ordinal for ranked categories, narrative for text). 
- [Method](./snoinc_extracts/loinc_method_abbrv_syn_20250926.json): The technique or procedure used to perform the measurement. This part is the only one that is not mandatory for every LOINC term. 

#### Data Structure:

```json
{
   ...
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
    ...
}
```
- Key: LOINC Part Short Name
- code: The LOINC Part unique identifier, starting with LP then typically in a 6-digit-then-a-dash format (e.g., LP806123-0).
- abbrv: A list of abbreviations for the specific LOINC Part.
- synonyms: A list of synonyms for the specific LOINC Part.

---

### LOINC Part Descriptions

This is a data file that contains LOINC codes/concepts that also have a LOINC Part descriptions that give a more in-depth description of the LOINC Lab code/concept.  Not all LOINC codes/concepts will have a result in this data file.  A custom [sql query](./loinc/loinc_codes_with_part_descriptions.sql) was created to extract this data from the LOINC RELMA database, as the results weren't possible to be extracted using the LOINC API.

#### Data Structure:

```csv
LOINC_NUM,DESCRIPTION
21019-5,Metanephrine is a metabolite generated when epiniphrine is cleaved by catechol O-methyltransferase. It is also known as 4-hydroxy-3-methoxy-alpha-((methylamino)methyl) benzenemethanol with formula C10-H15-N-O3.
80974-9,"Sulfamethoxazole is a sulfonamide bacteriostatic antibiotic. It is most often used as part of a synergistic combination with trimethoprim in a 5:1 ratio in co-trimoxazole, which is also known as Bactrim or Septrin. It can be used as an alternative to amoxicillin -based antibiotics to treat sinusitis. Mechanism of action:Sulfonamides are structural anologs and competitive antagonists of para-aminobenzoic acid (PABA). They inhibit normal bacterial utilization of PABA for the synthesis of folic acid, an important metabolite in DNA synthesis. The effects seen are usually bacteriostatic in nature. Folic acid is not synthesized in humans, but is instead a dietary requirement. This allows for the selective toxicity to bacterial cells (or any cell dependent on synthesizing folic acid) over human cells."
```
- LOINC_NUM: A unique identifier for a specific test or observation, typically in a 5-digit-then-a-dash format (e.g., 806-0).
- DESCRIPTION: The description pulled for the 'Component Core' Part for correlating LOINC codes/concept.

#### Extracts:

- [LOINC Codes with Part Descriptions](./snoinc_extracts/loinc_codes_with_part_descriptions.csv)

_**NOTE: we can easily change this to be a file with any delimiter instead of a `,`**_

---

### LOINC UMLS Related Names

This data file organizes correlated terms from LOINC and other terminology sets, such as SNOMED, that correlate to a single LOINC code.  The UMLS `Atom` and `Crosswalk` APIs are leveraged to gather and organize this data.

#### Data Structure:

```json
{
   ...
    "Epidermal Allergen Mix (Dog dander+Cat epithelium+Horse dander) Ab.IgE panel - Serum or Plasma": {
        "code": "102115-3",
        "names": [
            "(Dog dander+Cat epithelium+Horse dander) Antibody.immunoglobulin E panel:-:To identify measures at a point in time:Serum/Plasma:-",
            "Epid Allerg Mix IgE pl SerPl",
            "(Dog dander+Cat epithelium+Horse dander) IgE pl",
            "(Dog dander+Cat epithelium+Horse dander) Ab.IgE panel:-:Pt:Ser/Plas:-"
        ]
    },
    ...
}
```
- Key: LOINC Full Common Name
- Code: A unique identifier for a specific test or observation, typically in a 5-digit-then-a-dash format (e.g., 806-0).
- Names: A list of all related terms/names from the `atom` and `crosswalk` APIs for the LOINC Code.

#### Extracts

- [Loinc UMLS Related Names](./snoinc_extracts/loinc_umls_related_names_20250929.json)

---

### SNOMED

These data files are for the various codes/concepts in SNOMED used to be the base of the TTC model.

#### Data Structure:

 ```csv
 code|text
442779003|Borderline low
281301001|Within reference range
 ```
- Code: These are unique numerical identifiers for clinical concepts, such as a specific disease, a symptom, or a procedure.
- Text: Each concept code is associated with one or more textual descriptions that human-readable terms for the concept. A concept can have several descriptions, including synonyms, which represent the same clinical idea.  For this data file there will just be a single text, the common name/term/description, associated with each code.

#### Extracts:

- [Lab Values](./snoinc_extracts/snomed_lab_value_20250926.csv) - SNOMED CT does not code the specific quantitative values of lab results (e.g., "glucose 105 mg/dL") but rather provides codes for the qualitative interpretation of a result (e.g., positive, negative, abnormal). The quantitative value and its units are typically stored separately in the health record. 

---

### HL7

These data files are for the various codes & displays from various HL7 ValueSets and CodeSystems used in the base of the TTC model.

#### Data Structure:

```csv
code|text
B|Better
D|Significant change down
```
- Code: The unique machine-readable identifier for a concept.
- Text: Human-readable text describing the concept.

#### Extracts:

- [Lab Interpretations](./snoinc_extracts/hl7_lab_interp_20250926.csv) - In an HL7 message, the value from the ObservationInterpretation code system and/or a value set derived from it is used to provide additional context to the reported lab result. For instance, alongside a quantitative lab value, an interpretation code might indicate whether the result is "High" or "Low". This helps clinicians understand the significance of a result without having to interpret raw data themselves. 

### Instructions

To generate these SNOINC Extract Files refer to this [README](../data_curation/README.md#instructions)