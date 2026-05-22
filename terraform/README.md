# Terraform Infrastructure Overview

This directory contains Terraform configuration for deploying the TTC (Text-to-Code) Lambda and its supporting AWS infrastructure. All resources are deployed into a private VPC with no public internet access.

## Architecture

```
S3 Bucket (dibbs-text-to-code)
    │
    ├── ingestion/ prefix
    │       │
    │       └── OpenSearch Ingestion Pipeline (OSIS)
    │               │  polls monthly, reads NDJSON
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
- **Ingestion Pipeline IAM Role** (`aws_iam_role.os_ingestion_pipeline_role`): Assumed by the OSIS pipeline service. Grants S3 `ListBucket`/`GetObject` on the data bucket and full OpenSearch HTTP access on the domain.

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

- Polls `s3://dibbs-text-to-code/ingestion/` monthly for new NDJSON files
- Parses each line as a document and bulk-writes it into the `ttc-index` OpenSearch index
- Runs within the VPC using the same private subnets as Lambda
- Logs audit events to CloudWatch Logs (`/aws/vendedlogs/OpenSearchIngestion/ttc-ingestion-pipeline/audit-logs`, 14-day retention)
- Scales between 1 and 4 OCUs (OpenSearch Compute Units)

The pipeline **depends on** the index bootstrap invocation completing first, ensuring the KNN-enabled index and the Result Cache Index exist before any data is loaded (wiping and refilling the Result Cache index as well as the normal Index for vector embeddings ensures that previously computed hashes do not survive either LOINC updates or model updates).

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
7. Ingestion pipeline deployed — begins polling S3 for NDJSON embeddings to load
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
2. **Embedding files**: Upload NDJSON embedding files to `s3://dibbs-text-to-code/ingestion/`. The OSIS pipeline will ingest these into OpenSearch.
3. **Docker**: CI/CD builds all container images (`Dockerfile.ttc` for TTC lambda, `Dockerfile.index` for index lambda, `Dockerfile.augmentation` for augmentation lambda) automatically. For local development, Docker must be available to build the images.

> **Note:** The SentenceTransformer model and heavy Python dependencies (sentence-transformers, torch) are baked into the Lambda container image at build time via the Dockerfile. The Dockerfile installs the real `text-to-code-lambda` package and all its workspace dependencies.

## Known TODOs

- OpenSearch error logs should be sent to CloudWatch Logs (noted in `main.tf`)
- Polling frequency for the OSIS pipeline is set to monthly since LOINC updates infrequently, but can be adjusted as needed
- The `/ingestion/` prefix in the `dibbs-text-to-code` S3 bucket should be created as part of Terraform rather than manually
