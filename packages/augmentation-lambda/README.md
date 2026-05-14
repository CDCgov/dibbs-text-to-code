# DIBBs Augmentation Lambda

**General disclaimer** This repository was created for use by CDC programs to collaborate on public health related projects in support of the CDC mission: <https://www.cdc.gov/about/cdc/#cdc_about_cio_mission-our-mission>. GitHub is not hosted by the CDC, but is a third party website used by CDC and its partners to share information and collaborate on software. CDC use of GitHub does not imply an endorsement of any one particular service, product, or enterprise.

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
- Managing a S3-derived persistence ID for the augmented document and set IDs.
- Writing the augmented eICR XML back to S3.
- Writing augmentation metadata back to S3.

## Environment Variables

The Lambda reads these environment variables:

```text
S3_BUCKET
TTC_INPUT_PREFIX
TTC_OUTPUT_PREFIX
AUGMENTED_EICR_PREFIX
AUGMENTATION_METADATA_PREFIX
```

## Tests

Run the package tests with:

```bash
just test all packages/augmentation-lambda/tests
```
