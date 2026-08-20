# DIBBs Text to Code

[![codecov](https://codecov.io/github/CDCgov/dibbs-text-to-code/graph/badge.svg)](https://codecov.io/github/CDCgov/dibbs-text-to-code)
![python](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2FCDCgov%2Fdibbs-text-to-code%2Frefs%2Fheads%2Fmain%2Fpyproject.toml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

**General disclaimer** This repository was created for use by CDC programs to collaborate on public health related projects in support of the [CDC mission](https://www.cdc.gov/about/cdc/#cdc_about_cio_mission-our-mission). GitHub is not hosted by the CDC, but is a third party website used by CDC and its partners to share information and collaborate on software. CDC use of GitHub does not imply an endorsement of any one particular service, product, or enterprise.

## Related documents

- [Open Practices](open_practices.md)
- [Rules of Behavior](rules_of_behavior.md)
- [Thanks and Acknowledgements](thanks.md)
- [Disclaimer](DISCLAIMER.md)
- [Contribution Notice](CONTRIBUTING.md)
- [Code of Conduct](code-of-conduct.md)

## Table of Contents

- [Overview](#overview)
- [Getting Started](#getting-started)
- [Quality Assurance](#quality-assurance)
- [Releases](#releases)

## Overview

DIBBs Text to Code (TTC) is a CDC public health tool that maps nonstandard clinical text in [eICR](https://www.hl7.org/implement/standards/product_brief.cfm?product_id=436) (Electronic Initial Case Report) documents to standardized medical codes — primarily [LOINC](https://loinc.org/) and [SNOMED CT](https://www.snomed.org/) — using vector embeddings and approximate nearest-neighbor search.

Public health reporting relies on eICR documents that often contain free-text lab names and results that vary across labs and EHR systems. TTC bridges that gap by finding the best-fit standardized code for each piece of clinical text and writing it back into the document.

### How It Works

TTC has two sequential workflows:

### 1. Text-to-Code (TTC)

Given an eICR XML document and a corresponding [Schematron](https://www.schematron.com/) validation report identifying relevant errors, TTC:

1. Reads the Schematron report to identify which sections of the eICR contain errors that need standardized codes
2. Parses the XML and extracts text candidates for each configured data field (e.g., lab test names) using XPath expressions
3. Selects the best candidate text using priority-based evaluation criteria (e.g., prefers LOINC-sourced text over free text)
4. Embeds the selected text as a vector using [`NCHS/ttc-retriever-mvp`](https://huggingface.co/NCHS/ttc-retriever-mvp) — a SentenceTransformer model fine-tuned from [`intfloat/e5-large-v2`](https://huggingface.co/intfloat/e5-large-v2)
5. Queries an [OpenSearch](https://opensearch.org/) KNN index to find the nearest-neighbor standardized codes
6. Returns ranked `TTCAugmentation` objects containing the matched code, display name, and source location in the document

### 2. Augmentation

Given TTC results, the augmenter:

1. Updates [clinical document](http://hl7.org/cda/us/ccda/StructureDefinition/USRealmHeader) headers (ID, effective time, version number) to create a new derived document
2. Preserves the original eICR as a [`relatedDocument`](http://hl7.org/cda/stds/core/StructureDefinition/RelatedDocument) reference
3. Inserts an author entry identifying the TTC system at the clinical document level and for every updated observation
4. Writes `<translation>` elements at each code location with the matched standardized codes

### Repository Structure

This is a **uv workspace** (Python). All Python packages live under `packages/`.

| Package                                                | Role                                                                                                       |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| [`shared-models`](packages/shared-models/)             | Pydantic models shared across packages: `DataField`, `TTCAugmentation`, `TTCAugmenterInput`                |
| [`text-to-code`](packages/text-to-code/)               | Core TTC logic: XML parsing, candidate evaluation, embedding, and OpenSearch query building                |
| [`augmentation`](packages/augmentation/)               | Writes TTC results back into eICR XML as `<translation>` elements                                          |
| [`text-to-code-lambda`](packages/text-to-code-lambda/) | AWS Lambda handler for the TTC workflow (S3 → SQS triggered); also exposes the synchronous demo API        |
| [`augmentation-lambda`](packages/augmentation-lambda/) | AWS Lambda handler for the augmentation workflow, triggered by SQS events                                  |
| [`index-lambda`](packages/index-lambda/)               | AWS Lambda that bootstraps the OpenSearch KNN index (1024-dim HNSW/faiss/cosine) at deploy time            |
| [`lambda-handler`](packages/lambda-handler/)           | Shared Lambda runtime utilities (S3/OpenSearch clients, event parsing) used by the Lambda packages         |
| [`utils`](packages/utils/)                             | Path, regex, and LOINC name parsing utilities                                                              |
| [`data-curation`](packages/data-curation/)             | Scripts for pulling terminology data from LOINC, SNOMED, UMLS, and HL7 APIs; generates training data       |
| [`validation`](packages/validation/)                   | Functionality to validate an eICR and to create Schematron output                                          |
| [`frontend`](frontend/)                                | Static HTML/CSS/JS demo page for the synchronous text-to-code API (run with [`demo.sh`](frontend/demo.sh)) |

### Architecture Diagram

```text
              ┌─────────────────────────────────────────────────────┐
              │                   AWS Infrastructure                │
              │                                                     │
  eICR XML    │  SQS ──► text-to-code-lambda                        │
  (from S3)   │                    │                                │
              │         ┌──────────▼──────────┐                     │
              │         │    text-to-code     │                     │
              │         │  ┌───────────────┐  │                     │
              │         │  │ EicrProcessor │  │  XPath extraction   │
              │         │  │   Evaluator   │  │  Candidate selection│
              │         │  │   Embedder    │  │  Vector embedding   │
              │         │  │ QueryBuilder  │  │  KNN query          │
              │         │  └───────┬───────┘  │                     │
              │         └──────────┼──────────┘                     │
              │                    │                                │
              │         ┌──────────▼──────────┐                     │
              │         │     OpenSearch      │  KNN / HNSW index   │
              │         └──────────┬──────────┘                     │
              │                    │ TTCAugmentation results        │
              │  SQS ──► augmentation-lambda                        │
              │                    │                                │
              │         ┌──────────▼──────────┐                     │
              │         │    augmentation     │  XML modification   │
              │         └──────────┬──────────┘                     │
              └──────────────────┬─┴────────────────────────────────┘
                                 │
                      Augmented eICR XML (to S3)
```

In production, the two Lambda functions handle large-scale eICR processing.

### Key Design Patterns

- **Registry pattern**: `EICR_REGISTRY` and `EVALUATION_REGISTRY` map `DataField` enum values to their XPath/evaluation configuration. Adding support for a new clinical field only requires adding a new entry to each registry.
- **Config-driven extraction**: XPath expressions for text candidate extraction are defined per data field in subclasses of `BaseLabField`, keeping extraction logic declarative and field-specific.
- **Pluggable evaluation**: `BaseEvaluationCriteria` subclasses define candidate selection rules (priority ordering, code system preference) independently from the extraction logic.

## Getting Started

### Pre-requisites

- Python 3.14
- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/) [optional]

### Setup

#### Requirements

- [just](https://just.systems) - command runner
- [uv](https://docs.astral.sh/uv/) - to manage Python
- [pre-commit](https://pre-commit.com/) - Pre-commit hooks

After installing the above requirements run `just bootstrap` to initiate the Python environment and install pre-commit:

```sh
just bootstrap
```

To run tests:

```sh
just test
```

### Build and Verify

Use the following to build the lambda image and verify that its accepting requests:
(_requires Docker Compose_)

```sh
docker compose up -d
curl -XPOST "http://localhost:8080/2015-03-31/functions/function/invocations" -d '{"input": "test"}'
docker compose down
```

## Quality Assurance

**NOTE:** By default, pre-commit hooks are installed to run linting and formatting
checks on each commit. These hooks will attempt to automatically fix any issues
encountered. To force a commit without running the pre-commit hooks, use the
[!NOTE] 
By default, pre-commit hooks are installed to run linting and formatting
checks on each commit. These hooks will attempt to automatically fix any issues
encountered. To force a commit without running the pre-commit hooks, use the
following command:

```sh
git commit --no-verify
```

### Unit Tests

The unit tests require access to a private Hugging Face model. To run them locally, create a [Hugging Face access token](https://huggingface.co/settings/tokens) with `read` permissions and export it in your shell config (e.g., `~/.zshrc` or `~/.bashrc`):

```sh
export HF_TOKEN="hf_your_token_here"
```

To run all the unit tests, use the following command:

```sh
just test unit
```

To run a single unit test, use the following command:

```sh
just test unit tests/unit/test_utils.py::test_function
```

To update snapshots:

```sh
just test all --snapshot-update
```

To check coverage for a specific package or test suite:

```sh
just test coverage packages/augmentation-lambda
```

### e2e Tests

To run e2e tests, use the following command:

```sh
just test e2e
```

e2e test use [boto3](https://github.com/boto/boto3) to mock the various AWS systems we use: S3, SQS, and Lambdas. However, it currently does not simulate EventBridge invoking the Lambdas and passing them the SQS event, instead SQS event is manually built and passed to the lambda handler function.

## Validation Test

To ensure the latest schematron updates are being used when running `packages/validation` locally, use the following command:

```sh
just test validation
```

### Type checks

To run type checks, use the following command:

```sh
just ty
```

To type check a specific file, use the following command:

```sh
just ty path/to/file.py
```

### Terraform Commands

To run Terraform commands, use the following format:

```sh
just terraform <command> [options]
```

For example, to initialize the Terraform configuration:

```sh
just terraform init
```

### Linting

To run linting checks, use the following command:

```sh
just ruff
```

To lint a specific file, use the following command:

```sh
just ruff path/to/file.py
```

### Formatting

To run code formatting, use the following command:

```sh
ruff format
```

To format a specific file, use the following command:

```sh
ruff format path/to/file.py
```

### Logging

Lambda entry points use `aws_lambda_powertools.Logger` for structured JSON logs. TTC and augmentation Lambda logs include shared correlation fields such as `function_request_id`, `persistence_id`, `bucket_name`, `trigger_s3_key`, `s3_key`, and `status`.

Core packages that are also used outside Lambda, such as `text-to-code`, should use standard Python `logging` so non-Lambda callers do not depend on Lambda-specific logging behavior.

## Releases

See the [Releases](docs/releases.md) page for details.

## Standard Notices

### Public Domain Standard Notice

This repository constitutes a work of the United States Government and is not
subject to domestic copyright protection under 17 USC § 105. This repository is in
the public domain within the United States, and copyright and related rights in
the work worldwide are waived through the [CC0 1.0 Universal public domain dedication](https://creativecommons.org/publicdomain/zero/1.0/).
All contributions to this repository will be released under the CC0 dedication. By
submitting a pull request you are agreeing to comply with this waiver of
copyright interest.

### License Standard Notice

The repository utilizes code licensed under the terms of the Apache Software
License and therefore is licensed under ASL v2 or later.

This source code in this repository is free: you can redistribute it and/or modify it under
the terms of the Apache Software License version 2, or (at your option) any
later version.

This source code in this repository is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the Apache Software License for more details.

You should have received a copy of the Apache Software License along with this
program. If not, see the [Apache Software License](http://www.apache.org/licenses/LICENSE-2.0.html).

The source code forked from other open source projects will inherit its license.

### Privacy Standard Notice

This repository contains only non-sensitive, publicly available data and
information. All material and community participation is covered by the
[Disclaimer](DISCLAIMER.md)
and [Code of Conduct](code-of-conduct.md).
For more information about CDC's privacy policy, please visit [http://www.cdc.gov/other/privacy.html](https://www.cdc.gov/other/privacy.html).

### Contributing Standard Notice

Anyone is encouraged to contribute to the repository by [forking](https://help.github.com/articles/fork-a-repo)
and submitting a pull request. (If you are new to GitHub, you might start with a
[basic tutorial](https://help.github.com/articles/set-up-git).) By contributing
to this project, you grant a world-wide, royalty-free, perpetual, irrevocable,
non-exclusive, transferable license to all users under the terms of the
[Apache Software License v2](http://www.apache.org/licenses/LICENSE-2.0.html) or
later.

All comments, messages, pull requests, and other submissions received through
CDC including this GitHub page may be subject to applicable federal law, including but not limited to the Federal Records Act, and may be archived. Learn more at [http://www.cdc.gov/other/privacy.html](http://www.cdc.gov/other/privacy.html).

### Records Management Standard Notice

This repository is not a source of government records, but is a copy to increase
collaboration and collaborative potential. All government records will be
published through the [CDC web site](http://www.cdc.gov).

### Additional Standard Notices

Please refer to [CDC's Template Repository](https://github.com/CDCgov/template) for more information about [contributing to this repository](https://github.com/CDCgov/template/blob/main/CONTRIBUTING.md), [public domain notices and disclaimers](https://github.com/CDCgov/template/blob/main/DISCLAIMER.md), and [code of conduct](https://github.com/CDCgov/template/blob/main/code-of-conduct.md).
