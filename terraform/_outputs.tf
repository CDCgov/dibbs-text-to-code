
output "opensearch_endpoint" {
  value       = aws_opensearch_domain.os.endpoint
  description = "The OpenSearch endpoint URL"
}

output "opensearch_arn" {
  value       = aws_opensearch_domain.os.arn
  description = "The ARN of the OpenSearch domain"
}

output "lambda_function_name" {
  value       = aws_lambda_function.lambda.function_name
  description = "The name of the main TTC lambda function"
}

output "lambda_role_arn" {
  value       = aws_iam_role.lambda_role.arn
  description = "The ARN of the IAM role attached to the main and index TTC lambda functions"
}

output "opensearch_vpc_endpoint" {
  value       = aws_opensearch_vpc_endpoint.os_vpc_endpoint.endpoint
  description = "The VPC endpoint URL for the OpenSearch domain"
}

output "ecr_repository_url" {
  value       = aws_ecr_repository.ttc_lambda.repository_url
  description = "The URL of the ECR repository for the TTC Lambda container image"
}

output "index_ecr_repository_url" {
  value       = aws_ecr_repository.index_lambda.repository_url
  description = "The URL of the ECR repository for the index Lambda container image"
}
