# Terraform Infrastructure Overview

This directory contains Terraform configuration for deploying the TTC (Text-to-Code) Lambda and its supporting AWS infrastructure. All resources are deployed into a private VPC with no public internet access.

## Architecture

```
S3 Bucket (dibbs-text-to-code)
    │
    ├── reingestion/ prefix  (staging area for new embeddings)
    │       │  synced by the re-ingestion pipeline during a model update
    │       ▼
    ├── ingestion/ prefix
    │       │  ObjectCreated → EventBridge → ttc-osis-trigger-queue (SQS)
    │       │
    │       └── OpenSearch Ingestion Pipeline (OSIS)
    │               │  polls the queue, reads NDJSON
    │               ▼
    │       OpenSearch Domain (ttc-os-domain)
    │               ▲
    │               │ KNN queries
    └── TTC Lambda (ttc-lambda, container image from ECR)
```

All components live inside a private VPC (no NAT gateway, no internet gateway). Lambda and OpenSearch communicate over a VPC endpoint; S3 is accessed via a Gateway VPC endpoint (no internet required).

## Resources

### Networking (`main.tf`)

- **VPC** (`module.vpc`): A private-only VPC (`10.0.0.0/16`) with three private subnets across three availability zones (`us-east-2a/b/c`). No NAT gateway or internet gateway — all traffic stays within AWS.
- **S3 VPC Endpoint** (`aws_vpc_endpoint.s3_endpoint`): Gateway endpoint routing S3 traffic through the private route tables, allowing Lambda to read/write S3 without internet access.
- **Lambda Security Group** (`aws_security_group.lambda_sg`): Attached to all Lambda functions. Allows all outbound traffic; no inbound rules (Lambda initiates all connections).
- **OpenSearch Security Group** (`aws_security_group.opensearch_sg`): Allows inbound HTTPS (port 443) only from the Lambda security group. All outbound traffic permitted.

### OpenSearch (`main.tf`)

- **OpenSearch Domain** (`aws_opensearch_domain.os`): A 3-node `r5.large.search` cluster with zone awareness across all three AZs. Configured with:
  - Encryption at rest and node-to-node encryption
  - HTTPS enforced with TLS 1.2+
  - Engine version `OpenSearch_3.1` (minimum required for KNN vector queries)
  - Access policy permitting the Lambda IAM role, the ingestion pipeline role, and the deploying IAM principal
- **OpenSearch VPC Endpoint** (`aws_opensearch_vpc_endpoint.os_vpc_endpoint`): Exposes the domain inside the VPC. Its endpoint URL is injected into the TTC Lambda as `OPENSEARCH_ENDPOINT_URL`.

### ECR (`main.tf`)

- **ECR Repository** (`aws_ecr_repository.ttc_lambda`): Stores the Docker container image for the main TTC Lambda. The image installs all workspace Python packages (`shared-models`, `lambda-handler`, `text-to-code`, `text-to-code-lambda`) and bakes in the SentenceTransformer model (`intfloat/e5-large-v2`) at build time. Images are built and pushed by CI/CD during `terraform apply`.
- **ECR Repository** (`aws_ecr_repository.index_lambda`): Stores the Docker container image for the index bootstrap Lambda, built from `Dockerfile.index` at repo root.
- **ECR Repository** (`aws_ecr_repository.augmentation_lambda`): Stores the Docker container image for the augmentation Lambda, built from `Dockerfile.augmentation` at repo root.

### IAM (`main.tf`)

Each Lambda function has its own IAM role scoped to least-privilege S3 permissions:

- **TTC Lambda IAM Role** (`aws_iam_role.ttc_lambda_role`): Attached policies:
  - `AWSLambdaVPCAccessExecutionRole` — allows ENI creation for VPC placement
  - `AWSLambdaBasicExecutionRole` — allows CloudWatch Logs writes
  - Inline S3 policy — `s3:GetObject`/`s3:HeadObject` on `TextToCodeSubmissionV2/` and `ValidationResponseV2/` prefixes; `s3:PutObject` on `TTCAugmentationMetadataV2/` and `TTCMetadataV2/` prefixes
  - Inline OpenSearch policy — grants OpenSearch HTTP actions (`ESHttpGet/Post/Put/Delete/Head/Patch/Options`)
- **Index Lambda IAM Role** (`aws_iam_role.index_lambda_role`): Attached policies:
  - `AWSLambdaVPCAccessExecutionRole` — allows ENI creation for VPC placement
  - `AWSLambdaBasicExecutionRole` — allows CloudWatch Logs writes
  - Inline OpenSearch policy — grants OpenSearch HTTP actions (no S3 access needed)
- **Augmentation Lambda IAM Role** (`aws_iam_role.augmentation_lambda_role`): Attached policies:
  - `AWSLambdaVPCAccessExecutionRole` — allows ENI creation for VPC placement
  - `AWSLambdaBasicExecutionRole` — allows CloudWatch Logs writes
  - Inline S3 policy — `s3:PutObject` on `AugmentationEICRV2/` and `AugmentationMetadataV2/` prefixes (no OpenSearch access needed)
- **Ingestion Pipeline IAM Role** (`aws_iam_role.os_ingestion_pipeline_role`): Assumed by the OSIS pipeline service. Grants S3 `ListBucket`/`GetBucketLocation`/`GetObject` on the data bucket, `sqs:ReceiveMessage`/`DeleteMessage`/`GetQueueAttributes`/`ChangeMessageVisibility` on the pipeline's trigger queue, and full OpenSearch HTTP access on the domain.

### Lambda Functions (`main.tf`, `lambda/`)

#### Index Bootstrap Lambda (`ttc-index-lambda`, `packages/index-lambda`)

Deployed as a **container image** from ECR (`package_type = "Image"`) using `Dockerfile.index` at repo root. Responsible for creating the OpenSearch KNN Index and the OpenSearch Result Cache Index at deploy time. It is **invoked by Terraform** (`aws_lambda_invocation.index_bootstrap`) during `terraform apply`, before the ingestion pipeline is created.

The first Index it creates–the Vector Search Index–has LOINC-specific field mappings including `description_vector` (1024-dimension `knn_vector` using HNSW/faiss/cosine), `loinc_type`, `loinc_code`, `loinc_name_type`, and other LOINC metadata fields. Uses the `lambda_handler` shared utilities and reads `OPENSEARCH_ENDPOINT_URL` from its environment.

The second Index it creates–the Result Cache Index–contains the hashed results of previously computed embeddings and nearest neighbor queries, so that when the pipeline later receives eICRs containing a previously hashed value, the correct standardized code can simply be looked-up, rather than re-embedded and re-ranked. The Result Cache Index shares handling with the `lambda_handler` using the same functions but different actions than the Vector Search Index.

#### Main TTC Lambda (`ttc-lambda`, `Dockerfile.ttc`)

Deployed as a **container image** from ECR (`package_type = "Image"`). The Docker image (`Dockerfile.ttc` at repo root) installs the full `text-to-code-lambda` package along with its workspace dependencies (`shared-models`, `lambda-handler`, `text-to-code`).

At runtime, the Lambda runs the real `text_to_code_lambda.lambda_function.handler`, which:

1. Loads the SentenceTransformer model from `/opt/model` during initialization (cold start)
2. Parses eICR XML documents from S3 to extract text candidates
3. Evaluates and selects the best candidate for each data field
4. Generates embeddings and executes KNN queries against OpenSearch
5. Returns standardized code mappings (LOINC/SNOMED)

Environment variables injected at deploy time: `OPENSEARCH_ENDPOINT_URL`, `OPENSEARCH_INDEX`, `REGION`, `S3_BUCKET`, `RETRIEVER_MODEL_PATH`, `RERANKER_MODEL_PATH`, `SCHEMATRON_ERROR_PREFIX`, `TTC_INPUT_PREFIX`, `TTC_OUTPUT_PREFIX`, `TTC_METADATA_PREFIX`.

#### Augmentation Lambda (`ttc-augmentation-lambda`, `Dockerfile.augmentation`)

Deployed as a **container image** from ECR (`package_type = "Image"`). The Docker image (`Dockerfile.augmentation` at repo root) installs the `augmentation-lambda` package along with its workspace dependencies (`shared-models`, `lambda-handler`, `augmentation`).

At runtime, the Lambda processes augmentation requests containing eICR XML and nonstandard code mappings from the TTC Lambda. It:

1. Parses incoming eICR XML and nonstandard code instances
2. Inserts standardized LOINC/SNOMED `<translation>` elements into the eICR
3. Updates document headers (ID, effectiveTime, setId, versionNumber) and adds author/provenance metadata
4. Writes the augmented eICR XML and metadata JSON to S3

The augmentation Lambda uses only the Lambda security group (not the OpenSearch security group) since it does not require OpenSearch access. It is configured with lower memory (512 MB) and timeout (300s) defaults compared to the TTC Lambda, as it does not load ML models.

Environment variables injected at deploy time: `S3_BUCKET`, `AUGMENTED_EICR_PREFIX`, `AUGMENTATION_METADATA_PREFIX`, `REGION`.

#### Demo API Lambda (`ttc-api-lambda`, `demo.tf`)

Serves the interactive demo (see below). Built from the **same container image** as the main TTC Lambda — `image_config.command` overrides the CMD to `text_to_code_lambda.api_handler.handler`, so both Lambdas roll forward together whenever `ttc_lambda_image_tag` changes. It exposes a Lambda Function URL with `AWS_IAM` auth; only CloudFront can invoke it (via an Origin Access Control plus `lambda:InvokeFunctionUrl` and `lambda:InvokeFunction` permissions scoped to the distribution — since October 2025, OAC requires both actions). Its IAM role has OpenSearch access only — the synchronous API never touches S3.

### Demo Frontend (`demo.tf`)

A CloudFront distribution serves the static demo page (`frontend/`) and the synchronous API from one origin:

- **Default behavior** → private S3 bucket (`dibbs-ttc-demo-frontend`, Origin Access Control, all public access blocked) holding `index.html`, `app.js`, and `styles.css`, uploaded by Terraform as `aws_s3_object` resources whenever the files change. Caching is disabled (managed `CachingDisabled` policy), so no invalidations are needed.
- **`/text-to-code` behavior** → the demo API Lambda's Function URL. Because the page and API share an origin, no CORS configuration is involved. The origin read timeout is 60s (CloudFront's max without a quota increase). A cold start streams ~2 GB of model weights from the lazily-loaded container image and takes several minutes — far past that window — so an EventBridge rule (`ttc-api-lambda-warmer`, every 4 minutes) runs a real single-input inference to keep one execution environment warm; interactive requests then respond in seconds. Right after a deploy (or if the warm environment is recycled), the first request may still 504 and succeed on a later retry.
- **Basic auth**: a CloudFront Function (`ttc-demo-basic-auth`, viewer-request on both behaviors) requires a username/password before serving anything. The credential comes from `demo_auth_username` / `demo_auth_password` (the password has no default and is supplied in CI via the `DEMO_AUTH_PASSWORD` GitHub Actions secret → `TF_VAR_demo_auth_password`). After validating, the function strips the `Authorization` header so the Lambda OAC can attach its own SigV4 signature.

- **Custom domain**: the distribution serves `ttc.dibbs.tools` (`demo_domain_name`) with an ACM certificate issued in us-east-1 (a CloudFront requirement). DNS for `dibbs.tools` is managed in **Azure DNS** (zone `dibbs.tools`, resource group `dibbs-global-demo`): both the `ttc` CNAME to the distribution and the ACM validation CNAME (see the `demo_cert_validation_records` output) live there. `terraform apply` blocks on certificate issuance, so the validation record must exist in Azure DNS for a first apply to complete.

The demo URL is exported as the `demo_url` output.

### Logging

Lambda packages use `aws_lambda_powertools.Logger` for structured JSON logging.

The different text-to-code Lambdas emit structured logs with consistent keys so a TTC invocation can be correlated with the augmentation job that consumes its output. Lambda handlers use `@logger.inject_lambda_context` so Powertools adds Lambda runtime metadata, including `function_request_id`.

Standard log keys:

- `function_request_id`: Injected by Powertools from the Lambda context
- `persistence_id`: Shared identifier used to correlate TTC output with augmentation input
- `bucket_name`: S3 bucket being read from or written to
- `trigger_s3_key`: S3 object key from the EventBridge/SQS event that triggered the Lambda record
- `s3_key`: S3 object key being read from or written to by a specific log line
- `status`: Processing state or terminal result, such as `processing`, `success`, `skipped`, `error`, `matched`, `no_matches_found`, or `partial_failure`

Lambda entry points initialize a service logger:

```python
from aws_lambda_powertools import Logger

logger = Logger(service="ttc")
```

Lambda handlers inject runtime context:

```python
@logger.inject_lambda_context
def handler(event, context):
    ...
```

Use `trigger_s3_key` for the incoming event object and `s3_key` for individual S3 read/write operations:

```python
with logger.append_context_keys(
    persistence_id=persistence_id,
    bucket_name=bucket_name,
    trigger_s3_key=object_key,
):
    logger.info("Processing TTC event", status="processing")
```

```python
logger.info(
    "Retrieving eICR from S3",
    bucket_name=bucket_name,
    s3_key=object_key,
    status="processing",
)
```

Core library packages that are also used outside Lambda should continue to use stdlib `logging` instead of Powertools. This keeps non-Lambda callers such as data-curation and evaluator scripts from depending on Lambda-specific logging behavior. Lambda packages are responsible for using Powertools at the invocation boundary and emitting the structured fields needed for CloudWatch correlation.

Do not use `print()` or `structlog` in Lambda packages.

Example CloudWatch Logs Insights query:

```sql
fields @timestamp, service, function_name, function_request_id, persistence_id, bucket_name, trigger_s3_key, s3_key, status, message
| filter persistence_id = "REPLACE_WITH_PERSISTENCE_ID"
| sort @timestamp asc
```

### OpenSearch Ingestion Pipeline (`main.tf`)

An **AWS OpenSearch Ingestion Service (OSIS)** pipeline (`aws_osis_pipeline.ttc_ingestion_pipeline`) that:

- Ingests **on S3 event**, not on a schedule: writing an object under `s3://dibbs-text-to-code/ingestion/` starts a load within seconds
- Parses each line as a document and bulk-writes it into the `ttc-index` OpenSearch index
- Runs within the VPC using the same private subnets as Lambda
- Logs audit events to CloudWatch Logs (`/aws/vendedlogs/OpenSearchIngestion/ttc-ingestion-pipeline/audit-logs`, 14-day retention)
- Scales between 1 and 4 OCUs (OpenSearch Compute Units)

The pipeline **depends on** the index bootstrap invocation completing first, ensuring the KNN-enabled index and the Result Cache Index exist before any data is loaded (wiping and refilling the Result Cache index as well as the normal Index for vector embeddings ensures that previously computed hashes do not survive either LOINC updates or model updates).

#### Event-driven source

The pipeline's S3 source runs in `notification_type: sqs` mode against **`ttc-osis-trigger-queue`** (`aws_sqs_queue.osis_trigger_queue`), replacing the 30-day scheduled scan (`scan.scheduling.interval = PT720H`) it used previously. This is what makes the re-ingestion runbook work: syncing new embeddings into `ingestion/` is itself the trigger, with no scan interval to wait out. See [`docs/spikes/502-reingestion-pause.md`](../docs/spikes/502-reingestion-pause.md) and [`docs/runbooks/reingest-loinc-embeddings.md`](../docs/runbooks/reingest-loinc-embeddings.md).

**Events reach the queue through EventBridge** (`aws_cloudwatch_event_rule.osis_ingestion_s3_trigger` → `aws_cloudwatch_event_target.osis_trigger_sqs_target`), not through a direct S3 bucket notification. Two reasons:

1. A bucket accepts exactly one notification configuration, and `s3.tf` already declares `aws_s3_bucket_notification.ttc_eventbridge` with `eventbridge = true`. Adding queue targets means folding them into that same resource, where a mistake takes the TTC and augmentation triggers down with it.
2. It matches how every other S3-driven consumer in this stack is wired (`ttc-lambda-queue`, `ttc-augmentation-lambda-queue`), so there is one pattern to reason about.

The trade-off is one extra hop of latency (typically a second or two) and a dependency on the bucket's EventBridge flag staying on — acceptable for a bulk-load path. The source therefore sets `notification_source: eventbridge`, since EventBridge messages have a different shape than raw S3 event notifications.

Other source settings worth knowing:

- **Visibility timeout — 10 minutes** (`osis_trigger_visibility_timeout`), applied to both the queue and the source's `visibility_timeout`. With `acknowledgments: true` the pipeline deletes a message only after OpenSearch acknowledges the write, so the message must stay invisible for the entire read-plus-index time of one NDJSON object.
- **`visibility_duplication_protection: true`** with **`maximum_messages: 1`**. Documents are indexed without an explicit `_id`, so a redelivered object becomes a second copy of every document in it — which the runbook's `_count` gate would read as an overshoot. Duplication protection extends visibility while an object is in flight; the batch size of 1 avoids a known failure of that mechanism on large objects when a full batch of 10 is claimed at once ([data-prepper#4812](https://github.com/opensearch-project/data-prepper/issues/4812)), and costs nothing since `workers: 1` processes serially regardless.
- **`ttc-osis-trigger-queue-dlq`** takes any event that fails three times, and alarms into the same Slack channel as the Lambda DLQs. Without it a poison object would loop silently until the retention period expired.

Because the source is event-driven, the pipeline only sees objects created **after** it starts polling. Files already sitting in `ingestion/` when the pipeline is created are not loaded — see [Prerequisites](#prerequisites).

Two things now write to `ingestion/` and so start an ingest: the re-ingestion runbook's full swap, and the **Terminology Updates** workflow (`.github/workflows/teminology_update.yml`), which drops a dated `<terminology>_<date>_<count>.jsonl` delta per run. The deltas used to sit until the next monthly scan and now land in the index within a minute of the workflow finishing. Each run writes a new key, so nothing is re-read.

Third-party deployers should ensure the following:

- Private VPC networking with private subnets, an S3 Gateway VPC endpoint, and an OpenSearch VPC endpoint
- An OpenSearch domain compatible with this stack’s engine version, node layout, encryption, and TLS settings
- IAM permissions for the deployer, Lambda, and ingestion pipeline to create and access OpenSearch resources
- The index bootstrap step that runs before ingestion begins
- Valid NDJSON files available in the configured S3 ingestion prefix for pipeline loading

## Deployment Order

Terraform manages dependency ordering automatically, but conceptually the sequence is:

1. VPC, subnets, security groups, S3 endpoint created
2. ECR repositories created (TTC lambda, index lambda, augmentation lambda)
3. Docker images built and pushed to ECR (in CI/CD, before full `terraform apply`)
4. OpenSearch domain and VPC endpoint created
5. Lambda IAM roles created (one per Lambda function)
6. Index bootstrap Lambda deployed and **immediately invoked** — creates the KNN index and the Result Cache index in OpenSearch.
7. Ingestion trigger queue, its DLQ, and the EventBridge rule created; ingestion pipeline deployed — begins polling the queue for `ingestion/` object events
8. Main TTC Lambda deployed with container image from ECR — loads model at cold start, ready to serve KNN queries
9. Augmentation Lambda deployed with container image from ECR — ready to process augmentation requests

## State Backend

Terraform state is stored remotely in **AWS S3** with DynamoDB locking:

- Bucket: `dibbs-ttc-terraform-state`
- Key: `terraform.tfstate`
- Region: `us-east-2`
- Lock table: `dibbs-ttc-terraform-lock`

The backend resources are created by the bootstrap configuration in `bootstrap/`.

## File Layout

```
terraform/
├── _config.tf                    # Terraform backend (S3) and provider versions
├── _data.tf                      # Data sources (current AWS caller identity)
├── _outputs.tf                   # Outputs (endpoints, ARNs, function names, ECR URL)
├── _variables.tf                 # All input variables with defaults
├── main.tf                       # All AWS resources
├── demo.tf                       # Demo frontend + synchronous API (CloudFront, S3 site bucket, API lambda)
├── s3.tf                         # S3 bucket for ingestion data
├── README.md                     # This file
├── bootstrap/                    # One-time setup for S3 state backend + DynamoDB lock table
│   ├── main.tf
│   ├── _variables.tf
│   └── _outputs.tf
└── (no lambda/ subdirectory — Dockerfiles live at repo root as Dockerfile.ttc and Dockerfile.index)
```

## Prerequisites

Before running `terraform apply`:

1. **Bootstrap**: Run `terraform apply` in `bootstrap/` first to create the S3 state bucket and DynamoDB lock table.
2. **Embedding files**: Upload NDJSON embedding files to `s3://dibbs-text-to-code/ingestion/` **after** the OSIS pipeline exists — the upload is the ingest trigger. If the files were already there before the pipeline was created (a rebuilt environment, say), re-copy them onto themselves to raise fresh `ObjectCreated` events:

   ```sh
   aws s3 cp s3://dibbs-text-to-code/ingestion/ s3://dibbs-text-to-code/ingestion/ \
     --recursive --metadata-directive REPLACE
   ```

3. **Docker**: CI/CD builds all container images (`Dockerfile.ttc` for TTC lambda, `Dockerfile.index` for index lambda, `Dockerfile.augmentation` for augmentation lambda) automatically. For local development, Docker must be available to build the images.

> **Note:** The SentenceTransformer model and heavy Python dependencies (sentence-transformers, torch) are baked into the Lambda container image at build time via the Dockerfile. The Dockerfile installs the real `text-to-code-lambda` package and all its workspace dependencies.

## Known TODOs

- OpenSearch error logs should be sent to CloudWatch Logs (noted in `main.tf`)
- The `/ingestion/` and `/reingestion/` prefixes in the `dibbs-text-to-code` S3 bucket should be created as part of Terraform rather than manually (Terraform declares their names in `_variables.tf` but creates no placeholder objects — see [S3 Data Bucket](#s3-data-bucket-s3tf))
- Neither `reingestion/` nor `ingestion-backup-<ts>/` has an S3 lifecycle rule; cleanup is a manual operator step. An expiration rule on `ingestion-backup-*` would be a reasonable safety net
