# Text-to-Code Lambda

The Text-to-Code (TTC) Lambda infers structured medical codes (ICD-10, SNOMED, LOINC, etc.) from free text in eICRs when the original document is missing standard coded values. It is triggered via SQS messages that originate from S3 EventBridge notifications.

## Source-Bucket Directed Architecture

The TTC Lambda does **not** use a static, environment-variable-configured S3 bucket. Instead, it extracts the bucket name directly from the incoming S3 event payload (`detail.bucket.name`). All reads and writes for a given invocation target the bucket that triggered the event.

This design enables a single deployed Lambda to serve multiple, independent data pipelines without any reconfiguration. In the case of AIMS, the same TTC Lambda is used for:

- **eCR Pipeline** (`ecr-data-repository` bucket) — production processing of eICRs that fail TTC schematron validation.
- **TTC Training Pipeline** (`ecr-ttc-training` bucket) — offline evaluation of TTC model performance against anonymized, baseline-tagged data.

Because the Lambda follows the event to whatever bucket produced it, adding a new pipeline is as simple as wiring a new bucket's EventBridge rule to the existing SQS queue — no Lambda code or environment changes are required.

### IAM Requirements

The Lambda's execution role must have **s3:GetObject** and **s3:PutObject** permissions on every bucket that may produce events for it. This is a direct consequence of the source-bucket directed model: the Lambda reads inputs from — and writes outputs back to — whichever bucket the event originated from.

When onboarding a new bucket, ensure the Lambda's IAM policy is updated to grant read/write access to that bucket.

### Logging

Every TTC invocation logs the **event bucket** and **object key** as structured fields at the start of record processing, and carries the **bucket name** and **persistence ID** as context keys through all subsequent log lines. This makes it straightforward to filter CloudWatch logs by bucket or object when debugging cross-pipeline issues.

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `EICR_INPUT_PREFIX` | No | `eCRMessageV2/` | S3 key prefix for original eICR documents |
| `SCHEMATRON_ERROR_PREFIX` | No | `ValidationResponseV2/` | S3 key prefix for schematron validation responses |
| `TTC_INPUT_PREFIX` | No | `TextToCodeSubmissionV2/` | S3 key prefix for TTC submission triggers |
| `TTC_OUTPUT_PREFIX` | No | `TTCAugmentationMetadataV2/` | S3 key prefix for TTC augmentation output |
| `TTC_METADATA_PREFIX` | No | `TTCMetadataV2/` | S3 key prefix for TTC analysis metadata |
| `AWS_REGION` | Yes | — | AWS region |
| `OPENSEARCH_ENDPOINT_URL` | Yes | — | OpenSearch cluster endpoint |
| `OPENSEARCH_INDEX` | No | `ttc-index` | OpenSearch index name for vector search |
