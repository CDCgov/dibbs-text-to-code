locals {
  vpc_name = "${var.project}-${var.owner}-${terraform.workspace}"
  tags = {
    Name      = local.vpc_name
    project   = var.project
    owner     = var.owner
    workspace = terraform.workspace
  }
}

variable "dlq_alarm_action_arns" {
  description = "CloudWatch alarm action ARNs notified when Lambda DLQs contain visible messages."
  type        = list(string)
}

#############
# ECR Repository
#############
resource "aws_ecr_repository" "ttc_lambda" {
  name         = "ttc-lambda"
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.tags
}

resource "aws_ecr_repository" "index_lambda" {
  name         = "ttc-index-lambda"
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.tags
}

resource "aws_ecr_repository" "augmentation_lambda" {
  name         = "ttc-augmentation-lambda"
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.tags
}

#############
# VPC
# Note: If APHL wants to use their own VPC without this module, they will need to provide
# the VPC ID, private subnet IDs, and replace the calls to this module.
#############
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.16.0"

  name            = local.vpc_name
  cidr            = var.vpc_cidr
  azs             = var.availability_zones
  private_subnets = var.private_subnet_cidrs
  # if internal is true, then the VPC will not have a NAT or internet gateway
  enable_nat_gateway = false
  single_nat_gateway = false
  create_igw         = false
  tags               = local.tags
}

#############
# S3 VPC Endpoint
#############
resource "aws_vpc_endpoint" "s3_endpoint" {
  vpc_id            = module.vpc.vpc_id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"

  route_table_ids = module.vpc.private_route_table_ids

  tags = {
    Name = "ttc-s3-endpoint"
  }
}

#############
# Security Groups
#############
resource "aws_vpc_security_group_egress_rule" "lambda_all_egress" {
  security_group_id = aws_security_group.lambda_sg.id

  cidr_ipv4   = "0.0.0.0/0"
  ip_protocol = "-1"
}

resource "aws_security_group" "lambda_sg" {
  name        = "ttc-lambda-sg"
  description = "Security group for TTC Lambda function"
  vpc_id      = module.vpc.vpc_id

  tags = {
    Name = "ttc-lambda-sg"
  }
}

resource "aws_vpc_security_group_egress_rule" "opensearch_all_egress" {
  security_group_id = aws_security_group.opensearch_sg.id

  cidr_ipv4   = "0.0.0.0/0"
  ip_protocol = "-1"
}

resource "aws_vpc_security_group_ingress_rule" "opensearch_https_from_lambda" {
  security_group_id = aws_security_group.opensearch_sg.id

  from_port   = 443
  to_port     = 443
  ip_protocol = "tcp"

  referenced_security_group_id = aws_security_group.lambda_sg.id
  description                  = "Allow HTTPS access from Lambda SG"
}


resource "aws_security_group" "opensearch_sg" {
  name        = "ttc-opensearch-sg"
  description = "Security group for TTC OpenSearch domain to allow HTTPS access from Lambda"
  vpc_id      = module.vpc.vpc_id

  tags = { Name = "ttc-opensearch-sg" }

}

#############
# OpenSearch Domain
#############
data "aws_iam_policy_document" "opensearch_access_policy" {
  statement {
    sid    = "AllowLambdaRole"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = [aws_iam_role.ttc_lambda_role.arn, aws_iam_role.index_lambda_role.arn, aws_iam_role.os_ingestion_pipeline_role.arn, data.aws_caller_identity.current.arn]
    }
    actions   = var.lambda_os_actions
    resources = ["arn:aws:es:${var.region}:${data.aws_caller_identity.current.account_id}:domain/${var.opensearch_domain_name}/*"]
  }

  dynamic "statement" {
    for_each = length(var.debug_allowed_ips) > 0 && length(var.debug_iam_principals) > 0 ? [1] : []
    content {
      sid    = "AllowDebugFromAllowlist"
      effect = "Allow"
      principals {
        type        = "AWS"
        identifiers = var.debug_iam_principals
      }
      actions   = var.lambda_os_actions
      resources = ["arn:aws:es:${var.region}:${data.aws_caller_identity.current.account_id}:domain/${var.opensearch_domain_name}/*"]
      condition {
        test     = "IpAddress"
        variable = "aws:SourceIp"
        values   = var.debug_allowed_ips
      }
    }
  }
}

resource "aws_opensearch_domain" "os" {
  domain_name    = var.opensearch_domain_name
  engine_version = var.opensearch_engine_version

  cluster_config {
    instance_type          = "r5.large.search"
    instance_count         = 3
    zone_awareness_enabled = true
    zone_awareness_config {
      availability_zone_count = 3
    }
  }

  ebs_options {
    ebs_enabled = true
    volume_type = "gp3"
    volume_size = 10
  }

  advanced_security_options {
    enabled = false
  }

  encrypt_at_rest {
    enabled = true
  }

  node_to_node_encryption {
    enabled = true
  }

  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }
  access_policies = data.aws_iam_policy_document.opensearch_access_policy.json

  log_publishing_options {
    cloudwatch_log_group_arn = aws_cloudwatch_log_group.opensearch_app_logs.arn
    log_type                 = "ES_APPLICATION_LOGS"
  }

  log_publishing_options {
    cloudwatch_log_group_arn = aws_cloudwatch_log_group.opensearch_index_slow_logs.arn
    log_type                 = "INDEX_SLOW_LOGS"
  }

  log_publishing_options {
    cloudwatch_log_group_arn = aws_cloudwatch_log_group.opensearch_search_slow_logs.arn
    log_type                 = "SEARCH_SLOW_LOGS"
  }

  tags = { Name = var.opensearch_domain_name }
}

#############
# OpenSearch CloudWatch Logging
#############
resource "aws_cloudwatch_log_group" "opensearch_app_logs" {
  name              = "/aws/opensearch/domains/${var.opensearch_domain_name}/application-logs"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "opensearch_index_slow_logs" {
  name              = "/aws/opensearch/domains/${var.opensearch_domain_name}/index-slow-logs"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "opensearch_search_slow_logs" {
  name              = "/aws/opensearch/domains/${var.opensearch_domain_name}/search-slow-logs"
  retention_in_days = 14
}

data "aws_iam_policy_document" "opensearch_log_publishing" {
  statement {
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:*:*:log-group:/aws/opensearch/domains/${var.opensearch_domain_name}/*"]
    principals {
      type        = "Service"
      identifiers = ["es.amazonaws.com"]
    }
  }
}

resource "aws_cloudwatch_log_resource_policy" "opensearch_log_publishing" {
  policy_document = data.aws_iam_policy_document.opensearch_log_publishing.json
  policy_name     = "opensearch-${var.opensearch_domain_name}-log-publishing"
}

#############
# IAM Roles for Lambda Functions
#############
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

# TTC Lambda Role
resource "aws_iam_role" "ttc_lambda_role" {
  name               = "ttc-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = { Name = "ttc-lambda-role" }
}

resource "aws_iam_role_policy_attachment" "ttc_vpc_access" {
  role       = aws_iam_role.ttc_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy_attachment" "ttc_cloudwatch_logs" {
  role       = aws_iam_role.ttc_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "ttc_lambda_s3_policy" {
  name = "ttc-lambda-s3-inline-policy"
  role = aws_iam_role.ttc_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowS3Read"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:HeadObject"]
        Resource = [
          "arn:aws:s3:::${var.s3_bucket}/${var.ttc_input_prefix}*",
          "arn:aws:s3:::${var.s3_bucket}/${var.schematron_error_prefix}*"
        ]
      },
      {
        Sid    = "AllowS3Write"
        Effect = "Allow"
        Action = ["s3:PutObject"]
        Resource = [
          "arn:aws:s3:::${var.s3_bucket}/${var.ttc_output_prefix}*",
          "arn:aws:s3:::${var.s3_bucket}/${var.ttc_metadata_prefix}*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "ttc_lambda_opensearch_policy" {
  name = "ttc-lambda-opensearch-inline-policy"
  role = aws_iam_role.ttc_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = var.lambda_os_actions
        Resource = "arn:aws:es:${var.region}:${data.aws_caller_identity.current.account_id}:domain/${var.opensearch_domain_name}/*"
      }
    ]
  })
}

# Index Lambda Role
resource "aws_iam_role" "index_lambda_role" {
  name               = "ttc-index-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = { Name = "ttc-index-lambda-role" }
}

resource "aws_iam_role_policy_attachment" "index_vpc_access" {
  role       = aws_iam_role.index_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy_attachment" "index_cloudwatch_logs" {
  role       = aws_iam_role.index_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "index_lambda_opensearch_policy" {
  name = "index-lambda-opensearch-inline-policy"
  role = aws_iam_role.index_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = var.lambda_os_actions
        Resource = "arn:aws:es:${var.region}:${data.aws_caller_identity.current.account_id}:domain/${var.opensearch_domain_name}/*"
      }
    ]
  })
}

# Augmentation Lambda Role
resource "aws_iam_role" "augmentation_lambda_role" {
  name               = "ttc-augmentation-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = { Name = "ttc-augmentation-lambda-role" }
}

resource "aws_iam_role_policy_attachment" "augmentation_vpc_access" {
  role       = aws_iam_role.augmentation_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy_attachment" "augmentation_cloudwatch_logs" {
  role       = aws_iam_role.augmentation_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "augmentation_lambda_s3_policy" {
  name = "augmentation-lambda-s3-inline-policy"
  role = aws_iam_role.augmentation_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowS3Read"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:HeadObject"]
        Resource = [
          "arn:aws:s3:::${var.s3_bucket}/${var.ttc_input_prefix}*",
          "arn:aws:s3:::${var.s3_bucket}/${var.ttc_output_prefix}*"
        ]
      },
      {
        Sid    = "AllowS3Write"
        Effect = "Allow"
        Action = ["s3:PutObject"]
        Resource = [
          "arn:aws:s3:::${var.s3_bucket}/${var.augmented_eicr_prefix}*",
          "arn:aws:s3:::${var.s3_bucket}/${var.augmentation_metadata_prefix}*"
        ]
      }
    ]
  })
}

#############
# Lambda Function
#############

resource "aws_lambda_function" "lambda" {
  function_name = var.lambda_function_name
  role          = aws_iam_role.ttc_lambda_role.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.ttc_lambda.repository_url}:${var.ttc_lambda_image_tag}"
  timeout       = var.lambda_timeout
  memory_size   = 3008

  environment {
    variables = {
      OPENSEARCH_ENDPOINT_URL = "https://${aws_opensearch_domain.os.endpoint}"
      OPENSEARCH_INDEX        = var.index_name
      RESULT_CACHE_INDEX      = var.result_cache_index_name
      REGION                  = var.region
      RETRIEVER_MODEL_PATH    = "/opt/retriever_model"
      RERANKER_MODEL_PATH     = "/opt/reranker_model"
      SCHEMATRON_ERROR_PREFIX = var.schematron_error_prefix
      TTC_INPUT_PREFIX        = var.ttc_input_prefix
      TTC_OUTPUT_PREFIX       = var.ttc_output_prefix
      TTC_METADATA_PREFIX     = var.ttc_metadata_prefix
    }
  }

  tags = { Name = var.lambda_function_name }
}

##############
# OpenSearch Ingestion Pipeline
###############

# IAM Role for OpenSearch Ingestion Pipeline
resource "aws_iam_role" "os_ingestion_pipeline_role" {
  name = "ttc-os-ingestion-pipeline-role"

  # Trust policy for pipeline service
  assume_role_policy = jsonencode(
    {
      "Version" : "2012-10-17",
      "Statement" : [
        {
          "Effect" : "Allow",
          "Principal" : {
            "Service" : "osis-pipelines.amazonaws.com"
          },
          "Action" : "sts:AssumeRole"
        }
      ]
    }

  )
}

resource "aws_iam_role_policy" "os_ingestion_pipeline_policy" {
  name = "ttc-os-ingestion-pipeline-inline-policy"
  role = aws_iam_role.os_ingestion_pipeline_role.id
  policy = jsonencode(
    {
      "Version" : "2012-10-17",
      "Statement" : [
        {
          "Sid" : "AllowS3BucketListing",
          "Effect" : "Allow",
          "Action" : [
            "s3:ListBucket"
          ],
          "Resource" : "arn:aws:s3:::${var.s3_bucket}"
        },
        {
          "Sid" : "AllowS3ObjectAccess",
          "Effect" : "Allow",
          "Action" : [
            "s3:GetObject"
          ],
          "Resource" : "arn:aws:s3:::${var.s3_bucket}/*"
        },
        {
          "Sid" : "OpenSearchAccess",
          "Effect" : "Allow",
          "Action" : [
            "es:ESHttpPost",
            "es:ESHttpPut",
            "es:ESHttpGet",
            "es:ESHttpDelete",
            "es:ESHttpHead",
            "es:DescribeDomain"
          ],
          "Resource" : [
            "arn:aws:es:${var.region}:${data.aws_caller_identity.current.account_id}:domain/${var.opensearch_domain_name}/*",
            "arn:aws:es:${var.region}:${data.aws_caller_identity.current.account_id}:domain/${var.opensearch_domain_name}"
          ]
        },
        {
          "Sid" : "CloudWatchLogsForPipeline",
          "Effect" : "Allow",
          "Action" : [
            "logs:CreateLogGroup",
            "logs:CreateLogStream",
            "logs:PutLogEvents",
            "logs:DescribeLogGroups",
            "logs:DescribeLogStreams"
          ],
          "Resource" : "*"
        }
      ]
    }

  )

}

resource "aws_cloudwatch_log_group" "ttc_ingestion_pipeline_logs" {
  name              = "/aws/vendedlogs/OpenSearchIngestion/${var.ingestion_pipeline_name}/audit-logs"
  retention_in_days = 14
}


resource "aws_osis_pipeline" "ttc_ingestion_pipeline" {
  pipeline_name = var.ingestion_pipeline_name


  min_units = 1
  max_units = 4

  # Publishing to CloudWatch Logs
  log_publishing_options {
    is_logging_enabled = true
    cloudwatch_log_destination {
      log_group = aws_cloudwatch_log_group.ttc_ingestion_pipeline_logs.name
    }

  }

  pipeline_configuration_body = <<-EOT
    version: '2'
    extension:
      osis_configuration_metadata:
        builder_type: visual

    ttc-ingestion-pipeline:
      source:
        s3:
          acknowledgments: true
          scan:
            buckets:
              - bucket:
                  name: ${var.s3_bucket}
                  filter:
                    include_prefix:
                      - ${var.ingestion_prefix}
            scheduling:
              interval: PT720H
          aws:
            region: ${var.region}
            sts_role_arn: ${aws_iam_role.os_ingestion_pipeline_role.arn}
          codec:
            ndjson: {}
          compression: none
          workers: '1'


      processor: []

      sink:
        - opensearch:
            hosts:
              - https://${aws_opensearch_domain.os.endpoint}
            aws:
              serverless: false
              region: ${var.region}
              sts_role_arn: ${aws_iam_role.os_ingestion_pipeline_role.arn}
            index_type: custom
            index: ${var.index_name}
            bulk_size: '5'
            flush_timeout: '300'
      
  EOT

  depends_on = [
    aws_lambda_invocation.index_bootstrap,
    aws_lambda_invocation.result_cache_index_bootstrap
  ]
}

# ##############
# # OpenSearch Index
# ###############

#############
# Lambda Function for Index Creation
#############

resource "aws_lambda_invocation" "index_bootstrap" {
  function_name = aws_lambda_function.index_lambda.function_name
  input = jsonencode({
    action = "create_index"
    index  = var.index_name
  })

  depends_on = [aws_lambda_function.index_lambda]
}

resource "aws_lambda_invocation" "result_cache_index_bootstrap" {
  function_name = aws_lambda_function.index_lambda.function_name
  input = jsonencode({
    action = "create_result_cache"
    index  = var.result_cache_index_name
  })

  depends_on = [aws_lambda_function.index_lambda]
}

resource "aws_lambda_function" "index_lambda" {
  function_name = var.index_lambda_function_name
  role          = aws_iam_role.index_lambda_role.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.index_lambda.repository_url}:${var.index_lambda_image_tag}"
  timeout       = var.lambda_timeout

  environment {
    variables = {
      OPENSEARCH_ENDPOINT_URL = "https://${aws_opensearch_domain.os.endpoint}"
      REGION                  = var.region
      INDEX_NAME              = var.index_name
      RESULT_CACHE_INDEX_NAME = var.result_cache_index_name
      S3_BUCKET               = var.s3_bucket
    }
  }

  tags = { Name = var.index_lambda_function_name }
}

#############
# Augmentation Lambda
#############

resource "aws_lambda_function" "augmentation_lambda" {
  function_name = var.augmentation_lambda_function_name
  role          = aws_iam_role.augmentation_lambda_role.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.augmentation_lambda.repository_url}:${var.augmentation_lambda_image_tag}"
  timeout       = var.augmentation_lambda_timeout
  memory_size   = var.augmentation_lambda_memory_size

  environment {
    variables = {
      S3_BUCKET                    = var.s3_bucket
      TTC_INPUT_PREFIX             = var.ttc_input_prefix
      TTC_OUTPUT_PREFIX            = var.ttc_output_prefix
      AUGMENTED_EICR_PREFIX        = var.augmented_eicr_prefix
      AUGMENTATION_METADATA_PREFIX = var.augmentation_metadata_prefix
    }
  }

  tags = { Name = var.augmentation_lambda_function_name }
}

#############
# Augmentation Lambda SQS Queue
#############

resource "aws_sqs_queue" "augmentation_dlq" {
  name = "${var.augmentation_lambda_function_name}-dlq"
  tags = local.tags
}

resource "aws_cloudwatch_metric_alarm" "augmentation_dlq_visible_messages" {
  alarm_name          = "${aws_sqs_queue.augmentation_dlq.name}-visible-messages"
  alarm_description   = "Visible messages are present in the augmentation Lambda DLQ."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  actions_enabled     = true
  alarm_actions       = var.dlq_alarm_action_arns

  dimensions = {
    QueueName = aws_sqs_queue.augmentation_dlq.name
  }

  tags = local.tags
}

resource "aws_sqs_queue" "augmentation_queue" {
  name                       = "${var.augmentation_lambda_function_name}-queue"
  visibility_timeout_seconds = var.augmentation_lambda_timeout * 6

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.augmentation_dlq.arn
    maxReceiveCount     = 3
  })

  tags = local.tags
}

resource "aws_sqs_queue_policy" "augmentation_queue_policy" {
  queue_url = aws_sqs_queue.augmentation_queue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "events.amazonaws.com" }
        Action    = "sqs:SendMessage"
        Resource  = aws_sqs_queue.augmentation_queue.arn
      }
    ]
  })
}

#############
# Augmentation Lambda EventBridge Rule
#############

resource "aws_cloudwatch_event_rule" "augmentation_s3_trigger" {
  name        = "${var.augmentation_lambda_function_name}-s3-trigger"
  description = "Trigger augmentation Lambda when TTC output is created in S3"

  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    detail = {
      bucket = { name = [var.s3_bucket] }
      object = { key = [{ prefix = var.ttc_output_prefix }] }
    }
  })

  tags = local.tags
}

resource "aws_cloudwatch_event_target" "augmentation_sqs_target" {
  rule      = aws_cloudwatch_event_rule.augmentation_s3_trigger.name
  target_id = "${var.augmentation_lambda_function_name}-sqs"
  arn       = aws_sqs_queue.augmentation_queue.arn
}

#############
# Augmentation Lambda Event Source Mapping
#############

resource "aws_lambda_event_source_mapping" "augmentation_sqs" {
  event_source_arn        = aws_sqs_queue.augmentation_queue.arn
  function_name           = aws_lambda_function.augmentation_lambda.arn
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]
}

resource "aws_iam_role_policy" "augmentation_sqs_policy" {
  name = "augmentation-sqs-inline-policy"
  role = aws_iam_role.augmentation_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
        ]
        Resource = aws_sqs_queue.augmentation_queue.arn
      }
    ]
  })
}

#############
# TTC Lambda SQS Queue
#############

resource "aws_sqs_queue" "ttc_input_dlq" {
  name = "${var.lambda_function_name}-dlq"
  tags = local.tags
}

resource "aws_cloudwatch_metric_alarm" "ttc_input_dlq_visible_messages" {
  alarm_name          = "${aws_sqs_queue.ttc_input_dlq.name}-visible-messages"
  alarm_description   = "Visible messages are present in the TTC input Lambda DLQ."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  actions_enabled     = true
  alarm_actions       = var.dlq_alarm_action_arns

  dimensions = {
    QueueName = aws_sqs_queue.ttc_input_dlq.name
  }

  tags = local.tags
}

resource "aws_sqs_queue" "ttc_input_queue" {
  name                       = "${var.lambda_function_name}-queue"
  visibility_timeout_seconds = var.lambda_timeout * 6

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.ttc_input_dlq.arn
    maxReceiveCount     = 3
  })

  tags = local.tags
}

resource "aws_sqs_queue_policy" "ttc_input_queue_policy" {
  queue_url = aws_sqs_queue.ttc_input_queue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "events.amazonaws.com" }
        Action    = "sqs:SendMessage"
        Resource  = aws_sqs_queue.ttc_input_queue.arn
      }
    ]
  })
}

#############
# TTC Lambda EventBridge Rule
#############

resource "aws_cloudwatch_event_rule" "ttc_input_s3_trigger" {
  name        = "${var.lambda_function_name}-s3-trigger"
  description = "Trigger the main TTC Lambda when submission data is loaded in S3"

  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    detail = {
      bucket = { name = [var.s3_bucket] }
      object = { key = [{ prefix = var.ttc_input_prefix }] }
    }
  })

  tags = local.tags
}

resource "aws_cloudwatch_event_target" "ttc_input_sqs_target" {
  rule      = aws_cloudwatch_event_rule.ttc_input_s3_trigger.name
  target_id = "${var.lambda_function_name}-sqs"
  arn       = aws_sqs_queue.ttc_input_queue.arn
}

#############
# TTC Lambda Event Source Mapping
#############

resource "aws_lambda_event_source_mapping" "ttc_input_sqs" {
  event_source_arn        = aws_sqs_queue.ttc_input_queue.arn
  function_name           = aws_lambda_function.lambda.arn
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]
}

resource "aws_iam_role_policy" "ttc_input_sqs_policy" {
  name = "ttc-input-sqs-inline-policy"
  role = aws_iam_role.ttc_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
        ]
        Resource = aws_sqs_queue.ttc_input_queue.arn
      }
    ]
  })
}
