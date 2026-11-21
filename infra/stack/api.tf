# The `api` Lambda: FastAPI behind Lambda Web Adapter, reachable only through CloudFront.
# Its Function URL uses AWS_IAM and only the distribution may invoke it (AWS, «Borde»,
# option 1). Starting values from AWS, «Lambda: configuración de partida».

locals {
  api_name = "twochi-api"

  # Lambda Web Adapter v1.1.0, arm64, published by AWS in every region.
  web_adapter_layer = "arn:aws:lambda:eu-west-1:753240598075:layer:LambdaAdapterLayerArm64:30"
}

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "api" {
  name                 = local.api_name
  assume_role_policy   = data.aws_iam_policy_document.lambda_trust.json
  permissions_boundary = data.aws_iam_policy.workload_boundary.arn
}

data "aws_iam_policy_document" "api" {
  statement {
    sid       = "OwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.api.arn}:*"]
  }
}

resource "aws_iam_role_policy" "api" {
  name   = local.api_name
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

# Declared here so it gets a retention; created by Lambda it would never expire.
resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.api_name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "api" {
  function_name = local.api_name
  role          = aws_iam_role.api.arn
  runtime       = "python3.14"
  architectures = ["arm64"]
  memory_size   = 1024
  timeout       = 30

  s3_bucket = local.artifacts_bucket
  s3_key    = var.api_package_key

  # Lambda Web Adapter starts run.sh, which serves the app with uvicorn.
  handler = "run.sh"
  layers  = [local.web_adapter_layer]

  environment {
    variables = {
      AWS_LAMBDA_EXEC_WRAPPER      = "/opt/bootstrap"
      AWS_LWA_PORT                 = "8080"
      AWS_LWA_READINESS_CHECK_PATH = "/api/health"
      # buffered until the SSE turn lands; then response_stream here and on the URL.
      AWS_LWA_INVOKE_MODE = "buffered"
      TWOCHI_SUPABASE_URL = var.supabase_url
    }
  }

  logging_config {
    log_format = "JSON"
    log_group  = aws_cloudwatch_log_group.api.name
  }

  depends_on = [aws_iam_role_policy.api]
}

resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "AWS_IAM"
  invoke_mode        = "BUFFERED"
}

# Both permissions, each conditioned on the distribution: CloudFront signs with OAC and
# Lambda checks InvokeFunctionUrl and InvokeFunction.
resource "aws_lambda_permission" "cloudfront_url" {
  statement_id           = "AllowCloudFrontInvokeFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.api.function_name
  principal              = "cloudfront.amazonaws.com"
  source_arn             = aws_cloudfront_distribution.edge.arn
  function_url_auth_type = "AWS_IAM"
}

resource "aws_lambda_permission" "cloudfront_invoke" {
  statement_id             = "AllowCloudFrontInvokeFunction"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.api.function_name
  principal                = "cloudfront.amazonaws.com"
  source_arn               = aws_cloudfront_distribution.edge.arn
  invoked_via_function_url = true
}
