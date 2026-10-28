#############
# GPU Inference Service
#
# Serves the retriever and reranker models over HTTP from a single GPU instance on ECS
# Managed Instances. The TTC Lambda calls it inside the VPC at local.inference_url.
#
# Models are not baked into the image: the service downloads them at startup from
# var.inference_retriever_model_uri / var.inference_reranker_model_uri, so swapping a
# model is a variable change and a rolling restart.
#
# The service scales to zero. A message arriving on the TTC input queue wakes it
# (desired count 1); once the queue has been empty for var.inference_idle_minutes it
# goes back to 0, and ECS terminates the idle instance after
# var.inference_instance_idle_seconds.
#############

locals {
  inference_name = "${var.name_prefix}-inference"
  inference_port = 8080
  inference_url  = "http://inference.${var.name_prefix}.internal:${local.inference_port}"

  inference_retriever_model_uri = coalesce(
    var.inference_retriever_model_uri,
    "s3://${var.s3_bucket}/models/ttc-retriever-v1.0/",
  )
  inference_reranker_model_uri = coalesce(
    var.inference_reranker_model_uri,
    "s3://${var.s3_bucket}/models/ttc-reranker-v1.0/",
  )

  # The TTC Lambda reads these when ttc_use_inference_service is on. The model paths
  # become the S3 URIs so TTC metadata records which models served the request.
  inference_lambda_environment = var.ttc_use_inference_service ? {
    INFERENCE_SERVICE_URL           = local.inference_url
    INFERENCE_READY_TIMEOUT_SECONDS = tostring(var.inference_ready_timeout_seconds)
    RETRIEVER_MODEL_PATH            = local.inference_retriever_model_uri
    RERANKER_MODEL_PATH             = local.inference_reranker_model_uri
  } : {}
}

#############
# ECR
#############
resource "aws_ecr_repository" "inference" {
  name         = local.inference_name
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.tags
}

resource "aws_ecr_lifecycle_policy" "inference" {
  repository = aws_ecr_repository.inference.name

  # The CUDA image is several GB, so don't keep every build.
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images (including the build cache's superseded layers)"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep the 10 most recent tagged images"
        selection = {
          tagStatus      = "tagged"
          tagPatternList = ["*"]
          countType      = "imageCountMoreThan"
          countNumber    = 10
        }
        action = { type = "expire" }
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "inference" {
  name              = "/ecs/${local.inference_name}"
  retention_in_days = 14
  tags              = local.tags
}

#############
# IAM
#############

# Lets ECS launch and manage the GPU instances.
resource "aws_iam_role" "inference_infrastructure" {
  name = "${local.inference_name}-infrastructure-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "ecs.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })

  tags = local.tags
}

resource "aws_iam_role_policy_attachment" "inference_infrastructure" {
  role       = aws_iam_role.inference_infrastructure.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonECSInfrastructureRolePolicyForManagedInstances"
}

# The managed policy only allows passing roles named ecsInstanceRole*, so grant our
# instance role explicitly.
resource "aws_iam_role_policy" "inference_infrastructure_pass_instance_role" {
  name = "${local.inference_name}-pass-instance-role"
  role = aws_iam_role.inference_infrastructure.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = aws_iam_role.inference_instance.arn
        Condition = {
          StringEquals = { "iam:PassedToService" = "ec2.amazonaws.com" }
        }
      }
    ]
  })
}

# Assumed by the ECS agent on the GPU instances.
resource "aws_iam_role" "inference_instance" {
  name = "${local.inference_name}-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "ec2.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })

  tags = local.tags
}

resource "aws_iam_role_policy_attachment" "inference_instance" {
  role       = aws_iam_role.inference_instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonECSInstanceRolePolicyForManagedInstances"
}

resource "aws_iam_instance_profile" "inference_instance" {
  name = "${local.inference_name}-instance-profile"
  role = aws_iam_role.inference_instance.name
  tags = local.tags
}

# Pulls the image and writes logs.
resource "aws_iam_role" "inference_execution" {
  name = "${local.inference_name}-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "ecs-tasks.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })

  tags = local.tags
}

resource "aws_iam_role_policy_attachment" "inference_execution" {
  role       = aws_iam_role.inference_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Used by the service itself: read model weights, and allow ECS Exec for debugging.
resource "aws_iam_role" "inference_task" {
  name = "${local.inference_name}-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "ecs-tasks.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })

  tags = local.tags
}

resource "aws_iam_role_policy" "inference_task" {
  name = "${local.inference_name}-task-policy"
  role = aws_iam_role.inference_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = ["arn:aws:s3:::${var.s3_bucket}/models/*", "arn:aws:s3:::${var.s3_bucket}/parity/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = ["arn:aws:s3:::${var.s3_bucket}"]
        Condition = {
          StringLike = { "s3:prefix" = ["models/*"] }
        }
      },
      {
        Effect = "Allow"
        Action = [
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel",
        ]
        Resource = "*"
      },
    ]
  })
}

#############
# Security Group
# Applied to both the instances and the task. Only the TTC Lambda can call the service.
#############
resource "aws_security_group" "inference" {
  name        = "${local.inference_name}-sg"
  description = "GPU inference service, reachable only from the TTC Lambda"
  vpc_id      = module.vpc.vpc_id

  tags = { Name = "${local.inference_name}-sg" }
}

resource "aws_vpc_security_group_ingress_rule" "inference_from_lambda" {
  security_group_id = aws_security_group.inference.id

  from_port   = local.inference_port
  to_port     = local.inference_port
  ip_protocol = "tcp"

  referenced_security_group_id = aws_security_group.lambda_sg.id
  description                  = "Allow the TTC Lambda to call the inference service"
}

resource "aws_vpc_security_group_egress_rule" "inference_all_egress" {
  security_group_id = aws_security_group.inference.id

  cidr_ipv4   = "0.0.0.0/0"
  ip_protocol = "-1"
}

#############
# ECS Cluster and Capacity
#############
resource "aws_ecs_cluster" "inference" {
  name = local.inference_name

  setting {
    name  = "containerInsights"
    value = "disabled"
  }

  tags = local.tags
}

resource "aws_ecs_capacity_provider" "inference_gpu" {
  name    = "${local.inference_name}-gpu"
  cluster = aws_ecs_cluster.inference.name

  managed_instances_provider {
    infrastructure_role_arn = aws_iam_role.inference_infrastructure.arn
    propagate_tags          = "CAPACITY_PROVIDER"

    # How long an instance with no tasks is kept before ECS terminates it. A short window
    # keeps the instance warm across back-to-back batches without paying for idle hours.
    infrastructure_optimization {
      scale_in_after = var.inference_instance_idle_seconds
    }

    instance_launch_template {
      ec2_instance_profile_arn = aws_iam_instance_profile.inference_instance.arn
      capacity_option_type     = var.inference_capacity_option_type
      monitoring               = "BASIC"

      network_configuration {
        subnets         = module.vpc.private_subnets
        security_groups = [aws_security_group.inference.id]
      }

      # Image layers plus downloaded model weights.
      storage_configuration {
        storage_size_gib = 100
      }

      instance_requirements {
        allowed_instance_types    = [var.inference_instance_type]
        accelerator_types         = ["gpu"]
        accelerator_manufacturers = ["nvidia"]

        accelerator_count {
          min = 1
          max = 1
        }

        vcpu_count {
          min = 4
        }

        memory_mib {
          min = 16384
        }
      }
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.inference_infrastructure,
    aws_iam_role_policy.inference_infrastructure_pass_instance_role,
    aws_iam_role_policy_attachment.inference_instance,
  ]

  tags = local.tags
}

# The capacity provider returns while still CREATING; it must be ACTIVE before it can be
# associated with the cluster.
resource "time_sleep" "inference_capacity_provider_active" {
  create_duration = "20s"

  triggers = {
    capacity_provider = aws_ecs_capacity_provider.inference_gpu.name
  }
}

resource "aws_ecs_cluster_capacity_providers" "inference" {
  cluster_name       = aws_ecs_cluster.inference.name
  capacity_providers = [time_sleep.inference_capacity_provider_active.triggers["capacity_provider"]]

  default_capacity_provider_strategy {
    capacity_provider = time_sleep.inference_capacity_provider_active.triggers["capacity_provider"]
    weight            = 1
  }
}

#############
# Service Discovery
# The task registers an A record (inference.<prefix>.internal) while it is healthy.
# With no running task the name does not resolve, which the Lambda client treats as
# "still starting".
#############
resource "aws_service_discovery_private_dns_namespace" "inference" {
  name        = "${var.name_prefix}.internal"
  description = "Private service discovery for TTC services"
  vpc         = module.vpc.vpc_id
  tags        = local.tags
}

resource "aws_service_discovery_service" "inference" {
  name = "inference"

  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.inference.id
    routing_policy = "MULTIVALUE"

    dns_records {
      type = "A"
      ttl  = 10
    }
  }

  # ECS reports the container health check to Cloud Map, so the name only resolves once the
  # models are loaded. failure_threshold is deprecated (AWS always uses 1), but an empty
  # block is never sent to the API.
  health_check_custom_config {
    failure_threshold = 1
  }

  force_destroy = true
  tags          = local.tags
}

#############
# Task Definition and Service
#############
resource "aws_ecs_task_definition" "inference" {
  family                   = local.inference_name
  requires_compatibilities = ["MANAGED_INSTANCES"]
  network_mode             = "awsvpc"
  cpu                      = 3072
  memory                   = 12288
  execution_role_arn       = aws_iam_role.inference_execution.arn
  task_role_arn            = aws_iam_role.inference_task.arn

  container_definitions = jsonencode([
    {
      name      = "inference"
      image     = "${aws_ecr_repository.inference.repository_url}:${var.inference_image_tag}"
      essential = true

      portMappings = [
        {
          containerPort = local.inference_port
          protocol      = "tcp"
        }
      ]

      resourceRequirements = [
        {
          type  = "GPU"
          value = "1"
        }
      ]

      environment = [
        { name = "RETRIEVER_MODEL_URI", value = local.inference_retriever_model_uri },
        { name = "RERANKER_MODEL_URI", value = local.inference_reranker_model_uri },
        { name = "MODEL_DTYPE", value = var.inference_model_dtype },
        { name = "MODEL_DEVICE", value = "cuda" },
        { name = "PORT", value = tostring(local.inference_port) },
      ]

      # Model download and load happen before /health turns green.
      healthCheck = {
        command     = ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${local.inference_port}/health', timeout=4)"]
        interval    = 15
        timeout     = 5
        retries     = 3
        startPeriod = 300
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.inference.name
          awslogs-region        = var.region
          awslogs-stream-prefix = "inference"
        }
      }
    }
  ])

  tags = local.tags
}

resource "aws_ecs_service" "inference" {
  name            = local.inference_name
  cluster         = aws_ecs_cluster.inference.id
  task_definition = aws_ecs_task_definition.inference.arn

  # Autoscaling owns the desired count; it starts at 0 so a fresh deploy costs nothing.
  desired_count = 0

  # There is only ever one GPU: stop the old task before starting the new one rather
  # than paying for a second instance during deploys.
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  capacity_provider_strategy {
    capacity_provider = aws_ecs_capacity_provider.inference_gpu.name
    weight            = 1
  }

  network_configuration {
    subnets          = module.vpc.private_subnets
    security_groups  = [aws_security_group.inference.id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.inference.arn
  }

  enable_execute_command = true
  wait_for_steady_state  = false
  force_delete           = true

  lifecycle {
    ignore_changes = [desired_count]
  }

  depends_on = [aws_ecs_cluster_capacity_providers.inference]

  tags = local.tags
}

#############
# Scale to zero
#
# Driven by the TTC input queue: any visible or in-flight message wakes the service, and
# an empty queue for var.inference_idle_minutes puts it back to sleep. (Lambda's
# Invocations metric would not work for waking: it is recorded when an invocation ends,
# and the invocation that is waiting on the GPU has not ended yet.)
#############
resource "aws_appautoscaling_target" "inference" {
  service_namespace  = "ecs"
  scalable_dimension = "ecs:service:DesiredCount"
  resource_id        = "service/${aws_ecs_cluster.inference.name}/${aws_ecs_service.inference.name}"
  min_capacity       = 0
  max_capacity       = 1

  # `just inference wake` suspends scale-in to hold the service up for manual testing.
  lifecycle {
    ignore_changes = [suspended_state]
  }
}

resource "aws_appautoscaling_policy" "inference_wake" {
  name               = "${local.inference_name}-wake"
  service_namespace  = aws_appautoscaling_target.inference.service_namespace
  scalable_dimension = aws_appautoscaling_target.inference.scalable_dimension
  resource_id        = aws_appautoscaling_target.inference.resource_id
  policy_type        = "StepScaling"

  step_scaling_policy_configuration {
    adjustment_type         = "ExactCapacity"
    cooldown                = 60
    metric_aggregation_type = "Maximum"

    step_adjustment {
      metric_interval_lower_bound = 0
      scaling_adjustment          = 1
    }
  }
}

resource "aws_appautoscaling_policy" "inference_sleep" {
  name               = "${local.inference_name}-sleep"
  service_namespace  = aws_appautoscaling_target.inference.service_namespace
  scalable_dimension = aws_appautoscaling_target.inference.scalable_dimension
  resource_id        = aws_appautoscaling_target.inference.resource_id
  policy_type        = "StepScaling"

  step_scaling_policy_configuration {
    adjustment_type         = "ExactCapacity"
    cooldown                = 60
    metric_aggregation_type = "Maximum"

    step_adjustment {
      metric_interval_upper_bound = 0
      scaling_adjustment          = 0
    }
  }
}

locals {
  # Visible + in-flight messages on the TTC input queue.
  inference_queue_depth_queries = [
    {
      id     = "visible"
      metric = "ApproximateNumberOfMessagesVisible"
    },
    {
      id     = "in_flight"
      metric = "ApproximateNumberOfMessagesNotVisible"
    },
  ]
}

resource "aws_cloudwatch_metric_alarm" "inference_wake" {
  alarm_name          = "${local.inference_name}-wake"
  alarm_description   = "Starts the GPU inference service when TTC has work queued"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_appautoscaling_policy.inference_wake.arn]

  metric_query {
    id          = "depth"
    expression  = "visible + in_flight"
    label       = "TTC input queue depth"
    return_data = true
  }

  dynamic "metric_query" {
    for_each = local.inference_queue_depth_queries
    content {
      id = metric_query.value.id
      metric {
        namespace   = "AWS/SQS"
        metric_name = metric_query.value.metric
        period      = 60
        stat        = "Maximum"
        dimensions  = { QueueName = aws_sqs_queue.ttc_input_queue.name }
      }
    }
  }

  tags = local.tags
}

resource "aws_cloudwatch_metric_alarm" "inference_sleep" {
  alarm_name          = "${local.inference_name}-sleep"
  alarm_description   = "Stops the GPU inference service after the TTC input queue has been empty for ${var.inference_idle_minutes} minutes"
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  evaluation_periods  = var.inference_idle_minutes
  datapoints_to_alarm = var.inference_idle_minutes
  # SQS stops publishing metrics for queues that have been idle for a while; idle is empty.
  treat_missing_data = "breaching"
  alarm_actions      = [aws_appautoscaling_policy.inference_sleep.arn]

  metric_query {
    id          = "depth"
    expression  = "visible + in_flight"
    label       = "TTC input queue depth"
    return_data = true
  }

  dynamic "metric_query" {
    for_each = local.inference_queue_depth_queries
    content {
      id = metric_query.value.id
      metric {
        namespace   = "AWS/SQS"
        metric_name = metric_query.value.metric
        period      = 60
        stat        = "Maximum"
        dimensions  = { QueueName = aws_sqs_queue.ttc_input_queue.name }
      }
    }
  }

  tags = local.tags
}
