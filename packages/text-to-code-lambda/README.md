# Text-to-Code Lambda

## Table of Contents

- [Overview](#overview)
- [Demo API (synchronous text-to-code)](#demo-api-synchronous-text-to-code)
- [Source-Bucket Directed Architecture](#source-bucket-directed-architecture)
- [Pipeline Behavior](#pipeline-behavior)
- [Outputs](#outputs)
- [IAM Requirements](#iam-requirements)
- [Logging](#logging)
- [Environment Variables](#environment-variables)
- [Tests](#tests)

## Overview

The Text-to-Code (TTC) Lambda infers structured medical codes, such as LOINC, from free text in eICRs when the original document is missing standard coded values.

It is triggered by SQS messages that wrap S3 EventBridge notifications. Each record points to an incoming TTC submission object in S3. The Lambda loads the related schematron validation response, loads the original eICR, evaluates candidate free-text values, embeds selected text, queries OpenSearch, reranks returned code suggestions, and writes TTC output artifacts back to S3.

The TTC output is consumed by downstream augmentation workflows.

## Demo API (synchronous text-to-code)

Alongside the SQS batch worker, this package exposes a small **synchronous** path
that maps a raw lab-test string directly to a LOINC code — no eICR XML, no S3.
It powers the demo webpage (`frontend/index.html`) and reuses the exact embed → KNN →
rerank pipeline via the shared `service` module.

- `service.py` — `code_for_text(text, data_field, client, index)` and
  `results_for_inputs(...)`, the framework-agnostic core.
- `api_handler.py` — AWS Lambda **Function URL** handler. Intended to deploy as a
  second Lambda built from the **same image** as the batch worker, with the
  container command overridden to `text_to_code_lambda.api_handler.handler`.
- `local_server.py` — a **FastAPI** dev server (dev dependency only; not shipped
  in the image) for running the backend locally against the real OpenSearch
  domain.

### Request / response

```text
POST /text-to-code
{ "inputs": ["Glucose measurement", ...], "data_field": "Lab Test Name Ordered" }  // data_field optional
```

```json
{
  "results": [
    {
      "input": "Glucose measurement",
      "matched": true,
      "code": "110283-9",
      "code_system": "2.16.840.1.113883.6.1",
      "code_system_name": "LOINC",
      "display_name": "Glucose [Measurement]"
    }
  ]
}
```

`data_field` defaults to `Lab Test Name Ordered`; pass `Lab Test Name Resulted`
to filter to observation-typed LOINC codes instead. Unrecognized values fall back
to the default.

### Run locally

Requires AWS credentials permitted on the OpenSearch domain, and local access to
the retriever/reranker models (cached, or via `HF_TOKEN`).

```bash
OPENSEARCH_ENDPOINT_URL=https://<domain-endpoint> \
OPENSEARCH_INDEX=ttc-index \
AWS_REGION=us-east-2 \
uv run uvicorn text_to_code_lambda.local_server:app --port 8080
```

Then point the webpage's `API_BASE` at `http://localhost:8080`. Serve the page
over HTTP (e.g. `python -m http.server 8000`) so the browser sends a real CORS
origin; set `CORS_ALLOW_ORIGINS` to that origin to restrict cross-origin access.

## Source-Bucket Directed Architecture

The TTC Lambda does **not** use a static, environment-variable-configured S3 bucket. Instead, it extracts the bucket name directly from the incoming S3 event payload at `detail.bucket.name`.

All reads and writes for a given invocation target the bucket that triggered the event.

This design enables a single deployed Lambda to serve multiple, independent data pipelines without reconfiguration. In the case of AIMS, the same TTC Lambda can be used for:

- **eCR Pipeline** (`ecr-data-repository` bucket) — production processing of eICRs that fail TTC schematron validation.
- **TTC Training Pipeline** (`ecr-ttc-training` bucket) — offline evaluation of TTC model performance against anonymized, baseline-tagged data.

Because the Lambda follows the event to whatever bucket produced it, adding a new pipeline is as simple as wiring a new bucket's EventBridge rule to the existing SQS queue. No Lambda code or bucket environment-variable change is required.

If an event does not include `detail.bucket.name`, the Lambda raises an error instead of falling back to a static bucket.

## Pipeline Behavior

For each SQS record, the Lambda:

- Parses the SQS body as an EventBridge S3 event.
- Extracts the triggering object key and source bucket.
- Extracts the `persistence_id` from the object key using `TTC_INPUT_PREFIX`.
- Loads schematron validation responses from S3.
- Extracts relevant schematron data fields for TTC processing.
- Loads the original eICR from S3.
- Extracts eICR metadata.
- Evaluates free-text candidates from the eICR.
- Determines if the selected candidate can be auto-mapped using known input-to-code mappings.
- Selects the most relevant candidate text for each schematron error.
- Embeds the selected text.
- Queries OpenSearch using vector search.
- Reranks OpenSearch results.
- Builds `NonstandardCodeInstance` outputs for matched results.
- Tracks unmatched schematron errors and reasons.
- Saves TTC output for augmentation.
- Saves TTC metadata output for analysis and evaluation.

If no relevant schematron fields are found, the Lambda writes TTC metadata explaining why processing was skipped and returns a successful no-match result.

If relevant fields are found but no code matches are selected, the Lambda still writes outputs and returns a successful no-match result.

## Outputs

The Lambda writes two S3 artifacts.

### TTC augmentation output

Written to:

```text
<TTC_OUTPUT_PREFIX><persistence_id>
```

Default prefix:

```text
TTCAugmentationMetadataV2/
```

This output is consumed by the Augmentation Lambda. It includes:

- `persistence_id`
- `eicr_metadata`
- matched `schematron_errors`
- `unmatched_schematron_errors`

### TTC metadata output

Written to:

```text
<TTC_METADATA_PREFIX><persistence_id>.json
```

Default prefix:

```text
TTCMetadataV2/
```

This output is used for TTC analysis, debugging, and model evaluation. It includes:

- `persistence_id`
- `eicr_metadata`
- processed schematron error details
- OpenSearch result metadata
- reranker result metadata
- `processed_at`

## IAM Requirements

The Lambda's execution role must have **s3:GetObject** and **s3:PutObject** permissions on every bucket that may produce events for it.

This is required by the source-bucket directed model: the Lambda reads inputs from, and writes outputs back to, whichever bucket the event originated from.

When onboarding a new bucket, update the Lambda's IAM policy to grant read/write access to that bucket.

The Lambda also needs permissions to access the configured OpenSearch cluster.

## Logging

Every TTC invocation logs the record count at the start.

For each record, the Lambda logs the event bucket, triggering object key, and derived persistence ID as structured fields. It also carries the bucket name, persistence ID, and trigger S3 key as structured context through downstream log lines during record processing.

This makes it possible to filter CloudWatch logs by bucket, object key, or persistence ID when debugging cross-pipeline issues.

## Environment Variables

| Variable                  | Required | Default                      | Description                                                  |
| ------------------------- | -------- | ---------------------------- | ------------------------------------------------------------ |
| `SCHEMATRON_ERROR_PREFIX` | No       | `ValidationResponseV2/`      | S3 key prefix for schematron validation responses            |
| `TTC_INPUT_PREFIX`        | No       | `TextToCodeSubmissionV2/`    | S3 key prefix for TTC submission triggers                    |
| `TTC_OUTPUT_PREFIX`       | No       | `TTCAugmentationMetadataV2/` | S3 key prefix for TTC augmentation output                    |
| `TTC_METADATA_PREFIX`     | No       | `TTCMetadataV2/`             | S3 key prefix for TTC analysis metadata                      |
| `AWS_REGION`              | No       | Auto-provided by Lambda      | AWS region used by shared AWS client helpers                 |
| `S3_ENDPOINT_URL`         | No       | —                            | Optional custom S3 endpoint for local or mocked environments |
| `OPENSEARCH_ENDPOINT_URL` | Yes      | —                            | OpenSearch cluster endpoint                                  |
| `OPENSEARCH_INDEX`        | No       | `ttc-index`                  | OpenSearch index name for vector search                      |

## Tests

Run the package tests with:

```bash
just test all packages/text-to-code-lambda/tests
```
