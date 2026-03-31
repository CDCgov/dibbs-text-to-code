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

### IAM (`main.tf`)

- **Lambda IAM Role** (`aws_iam_role.lambda_role`): Shared by both Lambda functions. Attached policies:
  - `AWSLambdaVPCAccessExecutionRole` — allows ENI creation for VPC placement
  - `AWSLambdaBasicExecutionRole` — allows CloudWatch Logs writes
  - `AmazonS3FullAccess` — S3 read/write (TODO: scope down to specific bucket/prefix)
  - Inline policy — grants OpenSearch HTTP actions (`ESHttpGet/Post/Put/Delete/Head/Patch/Options`)
- **Ingestion Pipeline IAM Role** (`aws_iam_role.os_ingestion_pipeline_role`): Assumed by the OSIS pipeline service. Grants S3 `ListBucket`/`GetObject` on the data bucket and full OpenSearch HTTP access on the domain.

### Lambda Functions (`main.tf`, `lambda/`)

#### Index Bootstrap Lambda (`ttc-index-lambda`, `packages/index-lambda`)

Deployed as a **container image** from ECR (`package_type = "Image"`) using `Dockerfile.index` at repo root. Responsible for creating the OpenSearch KNN index at deploy time. It is **invoked by Terraform** (`aws_lambda_invocation.index_bootstrap`) during `terraform apply`, before the ingestion pipeline is created.

The index it creates has LOINC-specific field mappings including `description_vector` (1024-dimension `knn_vector` using HNSW/faiss/cosine), `loinc_type`, `loinc_code`, `loinc_name_type`, and other LOINC metadata fields. Uses the `lambda_handler` shared utilities and reads `OPENSEARCH_ENDPOINT_URL` from its environment.

#### Main TTC Lambda (`ttc-lambda`, `Dockerfile.ttc`)

Deployed as a **container image** from ECR (`package_type = "Image"`). The Docker image (`Dockerfile.ttc` at repo root) installs the full `text-to-code-lambda` package along with its workspace dependencies (`shared-models`, `lambda-handler`, `text-to-code`).

At runtime, the Lambda runs the real `text_to_code_lambda.lambda_function.handler`, which:

1. Loads the SentenceTransformer model from `/opt/model` during initialization (cold start)
2. Parses eICR XML documents from S3 to extract text candidates
3. Evaluates and selects the best candidate for each data field
4. Generates embeddings and executes KNN queries against OpenSearch
5. Returns standardized code mappings (LOINC/SNOMED)

Environment variables injected at deploy time: `OPENSEARCH_ENDPOINT_URL`, `OPENSEARCH_INDEX`, `REGION`, `S3_BUCKET`, `RETRIEVER_MODEL_PATH`, `RERANKER_MODEL_PATH`, `EICR_INPUT_PREFIX`, `SCHEMATRON_ERROR_PREFIX`, `TTC_INPUT_PREFIX`, `TTC_OUTPUT_PREFIX`, `TTC_METADATA_PREFIX`.

### OpenSearch Ingestion Pipeline (`main.tf`)

An **AWS OpenSearch Ingestion Service (OSIS)** pipeline (`aws_osis_pipeline.ttc_ingestion_pipeline`) that:

- Polls `s3://dibbs-text-to-code/ingestion/` monthly for new NDJSON files
- Parses each line as a document and bulk-writes it into the `ttc-index` OpenSearch index
- Runs within the VPC using the same private subnets as Lambda
- Logs audit events to CloudWatch Logs (`/aws/vendedlogs/OpenSearchIngestion/ttc-ingestion-pipeline/audit-logs`, 14-day retention)
- Scales between 1 and 4 OCUs (OpenSearch Compute Units)

The pipeline **depends on** the index bootstrap invocation completing first, ensuring the KNN-enabled index exists before any data is loaded.

## Deployment Order

Terraform manages dependency ordering automatically, but conceptually the sequence is:

1. VPC, subnets, security groups, S3 endpoint created
2. ECR repositories created (TTC lambda + index lambda)
3. Docker images built and pushed to ECR (in CI/CD, before full `terraform apply`)
4. OpenSearch domain and VPC endpoint created
5. Lambda IAM role created
6. Index bootstrap Lambda deployed and **immediately invoked** — creates the KNN index in OpenSearch
7. Ingestion pipeline deployed — begins polling S3 for NDJSON embeddings to load
8. Main TTC Lambda deployed with container image from ECR — loads model at cold start, ready to serve KNN queries

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
3. **Docker**: CI/CD builds both container images (`Dockerfile.ttc` for TTC lambda, `Dockerfile.index` for index lambda) automatically. For local development, Docker must be available to build the images.

> **Note:** The SentenceTransformer model and heavy Python dependencies (sentence-transformers, torch) are baked into the Lambda container image at build time via the Dockerfile. The Dockerfile installs the real `text-to-code-lambda` package and all its workspace dependencies.

## Known TODOs

- OpenSearch error logs should be sent to CloudWatch Logs (noted in `main.tf`)
- S3 IAM policy should be scoped down to the specific bucket and prefix instead of `AmazonS3FullAccess`
- Polling frequency for the OSIS pipeline is set to monthly since LOINC updates infrequently, but can be adjusted as needed
- The `/ingestion/` prefix in the `dibbs-text-to-code` S3 bucket should be created as part of Terraform rather than manually
