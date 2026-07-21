
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

output "ttc_lambda_role_arn" {
  value       = aws_iam_role.ttc_lambda_role.arn
  description = "The ARN of the IAM role attached to the TTC lambda function"
}

output "index_lambda_role_arn" {
  value       = aws_iam_role.index_lambda_role.arn
  description = "The ARN of the IAM role attached to the index lambda function"
}

output "augmentation_lambda_role_arn" {
  value       = aws_iam_role.augmentation_lambda_role.arn
  description = "The ARN of the IAM role attached to the augmentation lambda function"
}

output "ecr_repository_url" {
  value       = aws_ecr_repository.ttc_lambda.repository_url
  description = "The URL of the ECR repository for the TTC Lambda container image"
}

output "index_ecr_repository_url" {
  value       = aws_ecr_repository.index_lambda.repository_url
  description = "The URL of the ECR repository for the index Lambda container image"
}

output "augmentation_ecr_repository_url" {
  value       = aws_ecr_repository.augmentation_lambda.repository_url
  description = "The URL of the ECR repository for the augmentation Lambda container image"
}

output "augmentation_lambda_function_name" {
  value       = aws_lambda_function.augmentation_lambda.function_name
  description = "The name of the augmentation lambda function"
}

output "demo_url" {
  value       = "https://${aws_cloudfront_distribution.demo.domain_name}"
  description = "The CloudFront URL of the TTC demo (Basic auth required)"
}

output "api_lambda_function_url" {
  value       = aws_lambda_function_url.api.function_url
  description = "Direct Function URL of the demo API lambda (IAM-auth; only invokable through CloudFront)"
}
