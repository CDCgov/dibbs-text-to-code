#############
# Demo Frontend + Synchronous API
#
# A single CloudFront distribution serves the static demo frontend (frontend/)
# from a private S3 bucket and routes POST /text-to-code to a second lambda
# built from the same container image as the batch TTC lambda, with the CMD
# overridden to the Function URL handler. A CloudFront Function enforces Basic
# auth on every request, and Origin Access Controls keep both origins
# unreachable except through the distribution.
#############

# API Lambda Role
resource "aws_iam_role" "ttc_api_lambda_role" {
  name               = "ttc-api-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = { Name = "ttc-api-lambda-role" }
}

resource "aws_iam_role_policy_attachment" "api_cloudwatch_logs" {
  role       = aws_iam_role.ttc_api_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "api_lambda_opensearch_policy" {
  name = "ttc-api-lambda-opensearch-inline-policy"
  role = aws_iam_role.ttc_api_lambda_role.id

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

#############
# API Lambda + Function URL
#############
resource "aws_lambda_function" "api_lambda" {
  function_name = var.api_lambda_function_name
  role          = aws_iam_role.ttc_api_lambda_role.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.ttc_lambda.repository_url}:${var.ttc_lambda_image_tag}"
  timeout       = var.api_lambda_timeout
  memory_size   = var.api_lambda_memory_size

  # Same image as the batch TTC lambda; only the handler differs.
  image_config {
    command = ["text_to_code_lambda.api_handler.handler"]
  }

  environment {
    variables = {
      OPENSEARCH_ENDPOINT_URL = "https://${aws_opensearch_domain.os.endpoint}"
      OPENSEARCH_INDEX        = var.index_name
      RESULT_CACHE_INDEX      = var.result_cache_index_name
      REGION                  = var.region
      RETRIEVER_MODEL_PATH    = "/opt/retriever_model"
      RERANKER_MODEL_PATH     = "/opt/reranker_model"
    }
  }

  tags = { Name = var.api_lambda_function_name }
}

resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api_lambda.function_name
  authorization_type = "AWS_IAM"
}

# Only CloudFront (signing requests via the lambda OAC) may invoke the Function URL.
resource "aws_lambda_permission" "cloudfront_invoke_api_url" {
  statement_id           = "AllowCloudFrontOACInvoke"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.api_lambda.function_name
  principal              = "cloudfront.amazonaws.com"
  source_arn             = aws_cloudfront_distribution.demo.arn
  function_url_auth_type = "AWS_IAM"
}

# Since October 2025, OAC-signed requests are rejected with a 403 unless the
# CloudFront service principal also holds lambda:InvokeFunction.
resource "aws_lambda_permission" "cloudfront_invoke_api_function" {
  statement_id  = "AllowCloudFrontOACInvokeFunction"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_lambda.function_name
  principal     = "cloudfront.amazonaws.com"
  source_arn    = aws_cloudfront_distribution.demo.arn
}

#############
# Frontend S3 Bucket
#############
resource "aws_s3_bucket" "demo_frontend" {
  bucket = var.demo_frontend_bucket_name
  tags   = local.tags
}

resource "aws_s3_bucket_public_access_block" "demo_frontend" {
  bucket = aws_s3_bucket.demo_frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "demo_frontend_bucket_policy" {
  statement {
    sid    = "AllowCloudFrontOACRead"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.demo_frontend.arn}/*"]
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.demo.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "demo_frontend" {
  bucket = aws_s3_bucket.demo_frontend.id
  policy = data.aws_iam_policy_document.demo_frontend_bucket_policy.json
}

locals {
  demo_frontend_files = {
    "index.html" = "text/html"
    "app.js"     = "text/javascript"
    "styles.css" = "text/css"
  }
}

# filemd5 as etag re-uploads a file whenever its content changes; with caching
# disabled at CloudFront no invalidation step is needed.
resource "aws_s3_object" "demo_frontend" {
  for_each = local.demo_frontend_files

  bucket       = aws_s3_bucket.demo_frontend.id
  key          = each.key
  source       = "${path.module}/../frontend/${each.key}"
  content_type = each.value
  etag         = filemd5("${path.module}/../frontend/${each.key}")
}

#############
# CloudFront
#############
data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer_except_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

locals {
  demo_basic_auth_token = base64encode("${var.demo_auth_username}:${var.demo_auth_password}")
  # The Function URL is "https://<id>.lambda-url.<region>.on.aws/"; CloudFront
  # origins take the bare hostname.
  api_function_url_domain = replace(replace(aws_lambda_function_url.api.function_url, "https://", ""), "/", "")
}

resource "aws_cloudfront_function" "demo_basic_auth" {
  name    = "ttc-demo-basic-auth"
  runtime = "cloudfront-js-2.0"
  comment = "Basic auth gate for the TTC demo distribution"
  publish = true
  code    = <<-EOT
    function handler(event) {
      var request = event.request;
      var auth = request.headers.authorization;
      if (!auth || auth.value !== "Basic ${local.demo_basic_auth_token}") {
        return {
          statusCode: 401,
          statusDescription: "Unauthorized",
          headers: {
            "www-authenticate": { value: 'Basic realm="TTC demo", charset="UTF-8"' }
          }
        };
      }
      // The viewer Authorization header must not reach the origin: the lambda
      // OAC has to set its own SigV4 Authorization header when signing.
      delete request.headers.authorization;
      return request;
    }
  EOT
}

resource "aws_cloudfront_origin_access_control" "demo_s3" {
  name                              = "ttc-demo-s3-oac"
  description                       = "OAC for the demo frontend bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_origin_access_control" "demo_lambda" {
  name                              = "ttc-demo-lambda-oac"
  description                       = "OAC for the demo API lambda Function URL"
  origin_access_control_origin_type = "lambda"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "demo" {
  enabled             = true
  comment             = "TTC demo frontend and synchronous API"
  default_root_object = "index.html"
  price_class         = "PriceClass_100"

  origin {
    origin_id                = "demo-frontend-s3"
    domain_name              = aws_s3_bucket.demo_frontend.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.demo_s3.id
  }

  origin {
    origin_id                = "demo-api-lambda"
    domain_name              = local.api_function_url_domain
    origin_access_control_id = aws_cloudfront_origin_access_control.demo_lambda.id

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
      # A cold start loads both models (>60s even at high memory); 60s is the
      # maximum wait CloudFront allows without a quota increase, so the first
      # request may 504 while the container warms — the frontend surfaces a
      # "try again in ~30 seconds" hint for this case.
      origin_read_timeout      = 60
      origin_keepalive_timeout = 5
    }
  }

  default_cache_behavior {
    target_origin_id       = "demo-frontend-s3"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = data.aws_cloudfront_cache_policy.caching_disabled.id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.demo_basic_auth.arn
    }
  }

  ordered_cache_behavior {
    path_pattern           = "/text-to-code"
    target_origin_id       = "demo-api-lambda"
    viewer_protocol_policy = "https-only"
    # CloudFront's smallest method set that includes POST.
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id

    # The Basic auth gate applies to the API path too, not just the pages.
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.demo_basic_auth.arn
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = local.tags
}
