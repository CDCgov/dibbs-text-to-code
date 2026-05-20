# DIBBs Augmentation Lambda

## Table of Contents

- [Overview](#overview)
- [Getting Started](#getting-started)
- [Pre-requisites](#pre-requisites)
- [Responsibilities](#responsibilities)
- [Environment Variables](#environment-variables)
- [Tests](#tests)

## Overview

This package contains the AWS Lambda handler for running document augmentation after Text-to-Code output is written to S3.

Augmentation, specifically for the work in this repo, is related to eCR messages for various applications, such as Text-to-Code (TTC), eCR refinement, and Query Connector. This Lambda currently exists under the DIBBS-TEXT-TO-CODE project and product repo because TTC is the first application to leverage the augmentation functionality.

The Lambda package is intentionally kept separate from the core augmentation package. The core `augmentation` package owns the reusable XML augmentation behavior, while `augmentation-lambda` owns the AWS event handling, S3 reads and writes, and Lambda-specific orchestration.

For TTC, augmentation takes Text-to-Code output, retrieves the source eICR XML, adds the TTC-generated coded translations to the appropriate eICR locations, and writes both the augmented eICR and augmentation metadata back to S3.

Augmentation creates a new eICR iteration rather than replacing the original eICR in place. The augmented eICR preserves the source document history while adding the document identity, author, related document, template ID, XML comments, and translation metadata needed to identify what was changed and which application performed the augmentation.

## Getting Started

### Pre-requisites

- Python 3.11 or higher
- Docker
- Docker Compose [optional]

## Responsibilities

This package is responsible for:

- Reading the SQS-wrapped S3 event.
- Extracting the S3 persistence ID from the TTC output object key.
- Loading TTC output from S3.
- Loading the original eICR XML from S3.
- Parsing nonstandard code translations from TTC output.
- Running eICR augmentation through the core augmentation package.
- Seeding deterministic eICR document IDs from the persistence ID.
- Writing the augmented eICR XML back to S3.
- Writing augmentation metadata back to S3.

The Lambda coordinates the S3-based augmentation workflow. It does not own the low-level XML mutation logic. XML-specific augmentation behavior lives in the core `augmentation` package.

### Event flow

The augmentation flow starts when TTC output is written to S3.

At a high level:

1. TTC writes output containing nonstandard code results to S3.
2. The S3 event is wrapped by SQS and delivered to the Lambda.
3. The Lambda extracts the persistence ID from the TTC output object key.
4. The Lambda loads the TTC output from S3.
5. The Lambda loads the original eICR XML from S3.
6. The Lambda parses TTC nonstandard code results into `NonstandardCodeInstance` objects.
7. The Lambda builds a `TTCAugmenterInput` with the persistence ID and parsed nonstandard codes.
8. The Lambda creates an `EICRAugmenter` with the original eICR XML, nonstandard codes, TTC augmenter config, and deterministic ID seed.
9. The core augmentation package mutates the eICR XML and returns augmentation metadata.
10. The Lambda writes the augmented eICR XML to S3.
11. The Lambda writes augmentation metadata to S3.

### TTC output

The Lambda reads TTC output from `TTC_OUTPUT_PREFIX`.

TTC output is keyed by persistence ID and contains:

- The persistence ID.
- eICR metadata.
- Matched schematron errors grouped by data field.
- Unmatched schematron errors grouped by data field.

Matched schematron errors that include `new_translation` are converted into `NonstandardCodeInstance` objects and passed into the core augmentation package.

The current TTC output shape is:

```json
{
  "persistence_id": "<persistence id>",
  "eicr_metadata": {},
  "schematron_errors": {
    "<field type>": [
      {
        "schematron_error": "<schematron error>",
        "schematron_error_xpath": "<xpath>",
        "field_type": "<field type>",
        "new_translation": {
          "code": "<code>",
          "code_system": "<code system>",
          "code_system_name": "<code system name>",
          "display_name": "<display name>",
          "original_text": "<original text>"
        }
      }
    ]
  },
  "unmatched_schematron_errors": {}
}
```

TTC creates each matched nonstandard code from:

- The schematron error message.
- The schematron error context XPath.
- The schematron error field.
- The top-ranked LOINC match from OpenSearch and reranking.
- The original text candidate selected from the eICR.

The current TTC-generated translation fields are:

- `code`
- `code_system`
- `code_system_name`
- `display_name`
- `original_text`

For TTC LOINC mappings, the code system is `2.16.840.1.113883.6.1` and the code system name is `LOINC`.

### Augmentation input

The Lambda does not write a separate serialized augmentation input object to S3. It builds the augmentation inputs in memory.

Conceptually, the values handed to the core augmenter are:

```json
{
  "persistence_id": "<persistence id>",
  "original_eicr": "<full eICR XML>",
  "nonstandard_codes": [
    {
      "schematron_error": "<schematron error>",
      "schematron_error_xpath": "<xpath>",
      "field_type": "<field type>",
      "new_translation": {
        "code": "<code>",
        "code_system": "<code system>",
        "code_system_name": "<code system name>",
        "display_name": "<display name>",
        "original_text": "<original text>"
      }
    }
  ]
}
```

The Lambda passes those values into `EICRAugmenter` as:

- `document`: the original eICR XML string.
- `nonstandard_codes`: the parsed list of `NonstandardCodeInstance` objects.
- `config`: `TTCAugmenterConfig`.
- `deterministic_id_seed`: the persistence ID.

### eICR augmentation behavior

The Lambda invokes the core augmentation package to create a new augmented eICR.

For TTC, eICR augmentation updates the eICR in these main ways:

1. It creates new document identity metadata.
2. It adds the eICR data augmentation template ID.
3. It adds a related document reference back to the input eICR.
4. It adds a header-level author identifying TTC as the augmentation application.
5. It adds entry-level author metadata at the specific entry where augmentation occurred.
6. It adds TTC-generated coded values as translation elements under the affected code element.
7. It writes augmentation metadata describing the source eICR, augmented eICR, nonstandard code results, and inserted translation paths.

### Document identity metadata

Augmentation creates a new eICR document identity so the output is treated as a new iteration of the source eICR.

The augmented eICR receives:

- A new `ClinicalDocument/id`.
- A new `ClinicalDocument/effectiveTime`.
- A new `ClinicalDocument/setId`.
- A replacement `ClinicalDocument/versionNumber`.
- A new data augmentation `templateId`.

The `ClinicalDocument/id` and `ClinicalDocument/setId` roots are generated deterministically from:

- The application code.
- The persistence ID.
- The identifier type.

The current implementation uses the persistence ID as the deterministic ID seed. This makes augmented document and set identifiers stable for the same persistence ID.

The replacement `versionNumber` element uses the existing input eICR version value, defaulting to `1` when the input version value is missing.

The augmented eICR also receives the eICR data augmentation template ID:

```xml
<templateId root="2.16.840.1.113883.10.20.15.2.1.3" extension="2025-11-01"/>
```

### Related document metadata

Augmentation appends a `relatedDocument` element to the augmented eICR.

The related document uses:

```xml
<relatedDocument typeCode="XFRM">
```

The `relatedDocument` contains a `parentDocument` with the input eICR's:

- `id`
- `setId`
- `versionNumber`

If the input eICR document ID does not have an `assigningAuthorityName`, augmentation sets it to `original-document` in the parent document reference.

This preserves the relationship between the augmented eICR and the eICR that was used as input.

### Header-level author

Augmentation adds a header-level author indicating that Text-to-Code performed the augmentation.

Existing header authors are preserved.

The header-level author includes:

- The augmentation effective time.
- An assigned author with `nullFlavor="NA"` values for unavailable author identity fields.
- An assigned authoring device.
- A software name identifying the Text-to-Code data augmentation tool.

The header-level author documents that the eICR was transformed by the augmentation platform.

### Entry-level author

Augmentation adds entry-level author metadata at the specific entry where TTC added information.

The current augmenter uses the `schematron_error_xpath` from each `NonstandardCodeInstance` to locate the entry that should receive the entry-level author.

Each entry-level author includes a `functionCode` from the TTC augmenter configuration. The entry-level author documents the type of augmentation operation performed at that specific eICR entry.

There may be multiple entry-level authors when multiple TTC transformations occur in the same observation. For example, if TTC augments both an observation code and an observation value, the augmented eICR contains one header-level TTC author and separate entry-level authors for the individual augmented elements.

### Translation elements

TTC-generated codes are added as `translation` elements under the `code` element associated with the schematron validation error.

The current augmenter expects `schematron_error_xpath` to identify the eICR element that contains the `code` child. The translation is inserted under:

```text
<schematron_error_xpath>/code
```

The original code element is not replaced. Augmentation preserves the original source content and appends the TTC-generated mapped code as a translation.

The XML translation uses CDA-style XML attributes:

```xml
<translation
  code="<code>"
  codeSystem="2.16.840.1.113883.6.1"
  codeSystemName="LOINC"
  DisplayName="<display name>"
  originalText="<original text>"/>
```

The current implementation hardcodes the XML translation `codeSystem` to `2.16.840.1.113883.6.1` and `codeSystemName` to `LOINC`.

The `code`, `DisplayName`, and `originalText` attributes come from the TTC `new_translation` object.

### XML comments

The core eICR augmenter adds `DATA AUGMENTATION` XML comments before augmentation-related elements.

These comments mark:

- The eICR data augmentation header.
- The new document ID.
- The data augmentation operation time.
- The new set ID.
- The new version number.
- The related document relationship.
- The original or input document identity.
- The header-level author.
- The entry-level function code.
- The original code data.
- The augmented translation data.

These comments make the augmented XML easier to inspect and help distinguish original eICR content from augmentation-added content.

### Validation behavior

TTC augmentation adds valid LOINC mappings as translation elements.

The original observation code may remain unchanged, but the augmented eICR includes the TTC-generated code in the translation element. Validation can use the valid code in the translation element, so an augmented eICR can pass the relevant validation when the mapped LOINC code is present as a translation.

### Augmentation metadata

The Lambda writes augmentation metadata to S3 after augmentation completes.

The metadata records what augmentation did, which eICR was augmented, and where each new translation was inserted.

The current augmentation metadata shape is:

```json
{
  "original_eicr_id": "<original eICR id>",
  "augmented_eicr_id": "<augmented eICR id>",
  "nonstandard_codes": [
    {
      "schematron_error": "<schematron error>",
      "schematron_error_xpath": "<schematron error xpath>",
      "field_type": "<field type>",
      "new_translation": {
        "code": "<code>",
        "code_system": "<code system>",
        "code_system_name": "<code system name>",
        "display_name": "<display name>",
        "original_text": "<original text>"
      },
      "new_translation_xpath": "<new translation xpath>"
    }
  ]
}
```

The `new_translation_xpath` is generated after the translation element is inserted into the augmented eICR. It is returned as an absolute local-name XPath to the new `translation` element.

The metadata supports traceability between:

- The source eICR.
- The augmented eICR.
- The TTC result.
- The schematron error.
- The XML location where augmentation occurred.
- The XML location where the new translation was inserted.

### S3 outputs

The Lambda writes two outputs to S3:

- The augmented eICR XML.
- The augmentation metadata.

The augmented eICR XML is written under `AUGMENTED_EICR_PREFIX`.

The augmentation metadata is written under `AUGMENTATION_METADATA_PREFIX`.

The output object keys use the same persistence ID extracted from the triggering TTC output object key.

### Error handling

The Lambda processes each SQS record independently.

If a record fails, the Lambda logs the exception and records the failure for that message ID.

If all records succeed, the Lambda returns:

```json
{
  "statusCode": 200,
  "message": "Augmentation processed successfully!",
  "num_success_eicrs": 1
}
```

If one or more records fail, the Lambda returns:

```json
{
  "statusCode": 207,
  "message": "Augmentation processed with some failures!",
  "failures": [
    {
      "message_id": "<message id>",
      "error": "<error>"
    }
  ],
  "num_failure_eicrs": 1,
  "num_success_eicrs": 0
}
```

### Package boundary

The `augmentation-lambda` package owns Lambda-specific orchestration.

It handles:

- SQS event parsing.
- S3 object key parsing.
- S3 reads.
- S3 writes.
- Environment variable access.
- Calling the core augmentation package.

The core `augmentation` package owns reusable augmentation behavior.

It handles:

- eICR XML augmentation.
- Deterministic document ID generation.
- Deterministic set ID generation.
- Effective time replacement.
- Version number replacement.
- Data augmentation template ID insertion.
- Related document insertion.
- Header author insertion.
- Entry author insertion.
- Translation insertion.
- Augmentation metadata construction.

## Environment Variables

This package uses these environment variables and AWS runtime configuration values:

```text
S3_BUCKET
TTC_INPUT_PREFIX
TTC_OUTPUT_PREFIX
AUGMENTED_EICR_PREFIX
AUGMENTATION_METADATA_PREFIX
AWS_REGION
```

### `S3_BUCKET`

The S3 bucket used by the Lambda for TTC input, TTC output, augmented eICR output, and augmentation metadata output.

Default:

```text
dibbs-text-to-code
```

### `TTC_INPUT_PREFIX`

The S3 prefix where the source eICR XML is stored.

The Lambda uses this prefix when loading the original eICR XML that will be augmented.

Default:

```text
TextToCodeSubmissionV2/
```

### `TTC_OUTPUT_PREFIX`

The S3 prefix where TTC output is stored.

The SQS-wrapped S3 event points to an object under this prefix. The Lambda reads that object to get the TTC nonstandard code results used for augmentation.

Default:

```text
TTCAugmentationMetadataV2/
```

### `AUGMENTED_EICR_PREFIX`

The S3 prefix where the Lambda writes the augmented eICR XML.

Default:

```text
AugmentationEICRV2/
```

### `AUGMENTATION_METADATA_PREFIX`

The S3 prefix where the Lambda writes augmentation metadata.

Default:

```text
AugmentationMetadataV2/
```

### `AWS_REGION`

The AWS region available to the Lambda runtime and AWS clients.

## Tests

Run the package tests with:

```bash
just test all packages/augmentation-lambda/tests
```
