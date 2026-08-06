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

output "osis_trigger_queue_url" {
  value       = aws_sqs_queue.osis_trigger_queue.url
  description = "URL of the SQS queue the OpenSearch ingestion pipeline polls for ingestion-prefix object events"
}

output "demo_url" {
  value       = "https://${var.demo_domain_name}"
  description = "The URL of the TTC demo (Basic auth required)"
}

output "demo_cloudfront_url" {
  value       = "https://${aws_cloudfront_distribution.demo.domain_name}"
  description = "The distribution's default cloudfront.net URL for the TTC demo"
}

output "demo_cert_validation_records" {
  value = [
    for dvo in aws_acm_certificate.demo.domain_validation_options : {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  ]
  description = "DNS records to create in the dibbs.tools zone (Azure DNS) to validate the demo ACM certificate"
}

output "api_lambda_function_url" {
  value       = aws_lambda_function_url.api.function_url
  description = "Direct Function URL of the demo API lambda (IAM-auth; only invokable through CloudFront)"
}

output "ttc_reingestion_ci_role_arn" {
  description = "IAM role ARN for the TTC re-ingestion GitHub Actions workflow."
  value       = aws_iam_role.ttc_reingestion_ci_role.arn
}

output "ttc_input_event_source_mapping_uuid" {
  value       = aws_lambda_event_source_mapping.ttc_input_sqs.uuid
  description = "UUID of the TTC Lambda SQS event source mapping"
}

output "ttc_input_queue_url" {
  value       = aws_sqs_queue.ttc_input_queue.url
  description = "URL of the TTC Lambda input queue"
}

output "ttc_input_dlq_url" {
  value       = aws_sqs_queue.ttc_input_dlq.url
  description = "URL of the TTC Lambda dead-letter queue"
}

output "dlq_alarm_notifications_topic_arn" {
  value       = aws_sns_topic.dlq_alarm_notifications.arn
  description = "SNS topic ARN used for critical TTC re-ingestion notifications"
}
