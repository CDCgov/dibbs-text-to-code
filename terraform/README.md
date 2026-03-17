<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | ~> 1.7.4 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | ~> 5.86.0 |
| <a name="requirement_opensearch"></a> [opensearch](#requirement\_opensearch) | 2.3.2 |
| <a name="requirement_random"></a> [random](#requirement\_random) | ~> 3.6.3 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_aws"></a> [aws](#provider\_aws) | 5.86.1 |

## Modules

| Name | Source | Version |
|------|--------|---------|
| <a name="module_vpc"></a> [vpc](#module\_vpc) | terraform-aws-modules/vpc/aws | 5.16.0 |

## Resources

| Name | Type |
|------|------|
| [aws_cloudwatch_log_group.ttc_ingestion_pipeline_logs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_group) | resource |
| [aws_iam_role.lambda_role](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role.os_ingestion_pipeline_role](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role_policy.lambda_opensearch_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy) | resource |
| [aws_iam_role_policy.os_ingestion_pipeline_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy) | resource |
| [aws_iam_role_policy_attachment.cloudwatch_logs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.s3_access](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.vpc_access](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_lambda_function.index_lambda](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_function) | resource |
| [aws_lambda_function.lambda](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_function) | resource |
| [aws_lambda_invocation.index_bootstrap](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_invocation) | resource |
| [aws_lambda_layer_version.lambda_layer](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_layer_version) | resource |
| [aws_opensearch_domain.os](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/opensearch_domain) | resource |
| [aws_opensearch_vpc_endpoint.os_vpc_endpoint](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/opensearch_vpc_endpoint) | resource |
| [aws_osis_pipeline.ttc_ingestion_pipeline](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/osis_pipeline) | resource |
| [aws_security_group.lambda_sg](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/security_group) | resource |
| [aws_security_group.opensearch_sg](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/security_group) | resource |
| [aws_vpc_endpoint.s3_endpoint](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/vpc_endpoint) | resource |
| [aws_vpc_security_group_egress_rule.lambda_all_egress](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/vpc_security_group_egress_rule) | resource |
| [aws_vpc_security_group_egress_rule.opensearch_all_egress](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/vpc_security_group_egress_rule) | resource |
| [aws_vpc_security_group_ingress_rule.opensearch_https_from_lambda](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/vpc_security_group_ingress_rule) | resource |
| [aws_caller_identity.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/caller_identity) | data source |
| [aws_iam_policy_document.lambda_assume_role](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_iam_policy_document.opensearch_access_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_availability_zones"></a> [availability\_zones](#input\_availability\_zones) | The zones that the private subnets and OpenSearch domain will be deployed in. Must be in the same region as specified in the 'region' variable | `list(string)` | <pre>[<br>  "us-east-2a",<br>  "us-east-2b",<br>  "us-east-2c"<br>]</pre> | no |
| <a name="input_index_lambda_function_name"></a> [index\_lambda\_function\_name](#input\_index\_lambda\_function\_name) | The name of the lambda function responsible for creating the OpenSearch index at deployment time | `string` | `"ttc-index-lambda"` | no |
| <a name="input_index_lambda_function_zip_path"></a> [index\_lambda\_function\_zip\_path](#input\_index\_lambda\_function\_zip\_path) | Path to the index lambda function zip file | `string` | `"lambda/build/index_lambda_function.zip"` | no |
| <a name="input_index_lambda_handler"></a> [index\_lambda\_handler](#input\_index\_lambda\_handler) | Lambda handler for the index lambda function | `string` | `"index_lambda_function.lambda_handler"` | no |
| <a name="input_index_name"></a> [index\_name](#input\_index\_name) | The name of the index in OpenSearch created by the index lambda function at deployment time | `string` | `"ttc-index"` | no |
| <a name="input_ingestion_pipeline_name"></a> [ingestion\_pipeline\_name](#input\_ingestion\_pipeline\_name) | Ingestion Pipeline Variables | `string` | `"ttc-ingestion-pipeline"` | no |
| <a name="input_ingestion_prefix"></a> [ingestion\_prefix](#input\_ingestion\_prefix) | The prefix for the ingestion pipeline 'folder' in the s3 bucket. Files added to this prefix will be ingested into OpenSearch by the ingestion pipeline | `string` | `"ingestion"` | no |
| <a name="input_lambda_function_name"></a> [lambda\_function\_name](#input\_lambda\_function\_name) | The name of the main TTC lambda | `string` | `"ttc-lambda"` | no |
| <a name="input_lambda_function_zip_path"></a> [lambda\_function\_zip\_path](#input\_lambda\_function\_zip\_path) | Path to the main TTC lambda file | `string` | `"lambda/build/lambda_function.zip"` | no |
| <a name="input_lambda_handler"></a> [lambda\_handler](#input\_lambda\_handler) | Lambda handler for the main TTC lambda | `string` | `"lambda_function.lambda_handler"` | no |
| <a name="input_lambda_layer_name"></a> [lambda\_layer\_name](#input\_lambda\_layer\_name) | The name of the Lambda layer that contains the TTC lambda dependencies | `string` | `"ttc-lambda-layer"` | no |
| <a name="input_lambda_layer_zip_path"></a> [lambda\_layer\_zip\_path](#input\_lambda\_layer\_zip\_path) | Path to the lambda layer the main TTC lambda | `string` | `"lambda/build/lambda_layer.zip"` | no |
| <a name="input_lambda_os_actions"></a> [lambda\_os\_actions](#input\_lambda\_os\_actions) | The actions that the Lambda function can perform on OpenSearch | `list(string)` | <pre>[<br>  "es:ESHttpGet",<br>  "es:ESHttpPost",<br>  "es:ESHttpPut",<br>  "es:ESHttpDelete",<br>  "es:ESHttpHead",<br>  "es:ESHttpPatch",<br>  "es:ESHttpOptions"<br>]</pre> | no |
| <a name="input_lambda_runtime"></a> [lambda\_runtime](#input\_lambda\_runtime) | The runtime for the main TTC and index lambda functions | `string` | `"python3.12"` | no |
| <a name="input_lambda_timeout"></a> [lambda\_timeout](#input\_lambda\_timeout) | The timeout for the main TTC and index lambda functions in seconds, default is 15 minutes which is the maximum timeout allowed for Lambda functions. | `number` | `900` | no |
| <a name="input_opensearch_domain_name"></a> [opensearch\_domain\_name](#input\_opensearch\_domain\_name) | ## OpenSearch Variables | `string` | `"ttc-os-domain"` | no |
| <a name="input_opensearch_engine_version"></a> [opensearch\_engine\_version](#input\_opensearch\_engine\_version) | The version of the OpenSearch engine; must be >= 3.1 to support OpenSearch KNN queries which are used for vector search in the main TTC lambda function | `string` | `"OpenSearch_3.1"` | no |
| <a name="input_owner"></a> [owner](#input\_owner) | The owner of the infrastructure | `string` | `"skylight"` | no |
| <a name="input_private_subnet_cidrs"></a> [private\_subnet\_cidrs](#input\_private\_subnet\_cidrs) | The private subnets | `list(string)` | <pre>[<br>  "10.0.1.0/24",<br>  "10.0.2.0/24",<br>  "10.0.3.0/24"<br>]</pre> | no |
| <a name="input_project"></a> [project](#input\_project) | The project name | `string` | `"dibbs-ttc"` | no |
| <a name="input_region"></a> [region](#input\_region) | n/a | `string` | `"us-east-2"` | no |
| <a name="input_s3_bucket"></a> [s3\_bucket](#input\_s3\_bucket) | The name of the s3\_bucket where TTC data is stored | `string` | `"dibbs-ttc"` | no |
| <a name="input_vpc_cidr"></a> [vpc\_cidr](#input\_vpc\_cidr) | ## VPC Variables | `string` | `"10.0.0.0/16"` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_lambda_function_name"></a> [lambda\_function\_name](#output\_lambda\_function\_name) | The name of the main TTC lambda function |
| <a name="output_lambda_role_arn"></a> [lambda\_role\_arn](#output\_lambda\_role\_arn) | The ARN of the IAM role attached to the main and index TTC lambda functions |
| <a name="output_opensearch_arn"></a> [opensearch\_arn](#output\_opensearch\_arn) | The ARN of the OpenSearch domain |
| <a name="output_opensearch_endpoint"></a> [opensearch\_endpoint](#output\_opensearch\_endpoint) | The OpenSearch endpoint URL |
| <a name="output_opensearch_vpc_endpoint"></a> [opensearch\_vpc\_endpoint](#output\_opensearch\_vpc\_endpoint) | The VPC endpoint URL for the OpenSearch domain |
<!-- END_TF_DOCS -->