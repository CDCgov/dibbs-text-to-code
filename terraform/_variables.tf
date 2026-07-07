### General Variables
variable "project" {
  description = "The project name"
  type        = string
  default     = "dibbs-ttc"
}

variable "owner" {
  description = "The owner of the infrastructure"
  type        = string
  default     = "skylight"
}

variable "region" {
  type    = string
  default = "us-east-2"
}

### OpenSearch Variables
variable "opensearch_domain_name" {
  type    = string
  default = "ttc-os-domain"
}

variable "opensearch_engine_version" {
  type        = string
  default     = "OpenSearch_3.1"
  description = "The version of the OpenSearch engine; must be >= 3.1 to support OpenSearch KNN queries which are used for vector search in the main TTC lambda function"
}

### VPC Variables
variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "private_subnet_cidrs" {
  description = "The private subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}
variable "availability_zones" {
  type        = list(string)
  default     = ["us-east-2a", "us-east-2b", "us-east-2c"]
  description = "The zones that the private subnets and OpenSearch domain will be deployed in. Must be in the same region as specified in the 'region' variable"
}

### Lambda Variables
variable "lambda_function_name" {
  type        = string
  default     = "ttc-lambda"
  description = "The name of the main TTC lambda"
}

variable "lambda_timeout" {
  type        = number
  default     = 900
  description = "The timeout for the main TTC and index lambda functions in seconds, default is 15 minutes which is the maximum timeout allowed for Lambda functions."
}


variable "lambda_os_actions" {
  type = list(string)
  default = [
    "es:ESHttpGet",
    "es:ESHttpPost",
    "es:ESHttpPut",
    "es:ESHttpDelete",
    "es:ESHttpHead",
    "es:ESHttpPatch",
    "es:ESHttpOptions"
  ]
  description = "The actions that the Lambda function can perform on OpenSearch"

}

variable "index_lambda_function_name" {
  type        = string
  default     = "ttc-index-lambda"
  description = "The name of the lambda function responsible for creating the OpenSearch index at deployment time"
}

# Ingestion Pipeline Variables
variable "ingestion_pipeline_name" {
  type    = string
  default = "ttc-ingestion-pipeline"
}

variable "s3_bucket" {
  type        = string
  default     = "dibbs-text-to-code"
  description = "The name of the s3_bucket where TTC data is stored"
}

variable "ingestion_prefix" {
  type        = string
  default     = "ingestion"
  description = "The prefix for the ingestion pipeline 'folder' in the s3 bucket. Files added to this prefix will be ingested into OpenSearch by the ingestion pipeline"
}

variable "index_name" {
  type        = string
  default     = "ttc-index"
  description = "The name of the Vector Search index in OpenSearch created by the index lambda function at deployment time"
}

variable "result_cache_index_name" {
  type        = string
  default     = "ttc-result-cache"
  description = "The name of the Result Cache index in OpenSearch created by the index lambda function at deployment time"
}

### S3 Prefix Variables (for TTC Lambda)
variable "schematron_error_prefix" {
  type        = string
  default     = "ValidationResponseV2/"
  description = "S3 prefix for schematron validation response files"
}

variable "ttc_input_prefix" {
  type        = string
  default     = "TextToCodeSubmissionV2/"
  description = "S3 prefix for TTC input submission files"
}

variable "ttc_output_prefix" {
  type        = string
  default     = "TTCAugmentationMetadataV2/"
  description = "S3 prefix for TTC augmentation metadata output files"
}

variable "ttc_metadata_prefix" {
  type        = string
  default     = "TTCMetadataV2/"
  description = "S3 prefix for TTC analysis metadata files"
}

variable "augmented_eicr_prefix" {
  type        = string
  default     = "AugmentationEICRV2/"
  description = "S3 prefix for augmented eICR output files"
}

variable "augmentation_metadata_prefix" {
  type        = string
  default     = "AugmentationMetadataV2/"
  description = "S3 prefix for augmentation metadata files"
}

### Augmentation Lambda Variables
variable "augmentation_lambda_function_name" {
  type        = string
  default     = "ttc-augmentation-lambda"
  description = "The name of the augmentation lambda function"
}

variable "augmentation_lambda_memory_size" {
  type        = number
  default     = 512
  description = "Memory allocation in MB for the augmentation lambda. Lower than the TTC lambda since no ML models are loaded."
}

variable "augmentation_lambda_timeout" {
  type        = number
  default     = 300
  description = "Timeout in seconds for the augmentation lambda function"
}

### Container Image Variables
variable "ttc_lambda_image_tag" {
  type        = string
  default     = "latest"
  description = "The image tag for the TTC Lambda container image in ECR"
}

variable "index_lambda_image_tag" {
  type        = string
  default     = "latest"
  description = "The image tag for the index Lambda container image in ECR"
}

variable "augmentation_lambda_image_tag" {
  type        = string
  default     = "latest"
  description = "The image tag for the augmentation Lambda container image in ECR"
}

### Debug Access Variables (temporary — revert when done)
variable "debug_allowed_ips" {
  description = "CIDR blocks permitted to hit the public OpenSearch endpoint with the debug IAM principals. Used only while vpc_options is stripped from aws_opensearch_domain.os."
  type        = list(string)
  default     = []
}

variable "debug_iam_principals" {
  description = "Additional IAM user/role ARNs granted ES HTTP access to the public domain (e.g. a developer's SSO role). Paired with debug_allowed_ips."
  type        = list(string)
  default     = []
}

### S3 Prefix Variables for Medical Terminologies
variable "terminology_prefix" {
  type        = string
  default     = "Terminologies"
  description = "The prefix for the terminologies extract and update pipeline 'folder' in the s3 bucket. Files added to this prefix will be used for keeping ther terminolgies and hence embeddings up to date."
}
