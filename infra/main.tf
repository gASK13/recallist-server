provider "aws" {
  region = "us-east-1" # Change as needed
}

data "aws_region" "current" {}

data "aws_caller_identity" "current" {}

terraform {
  backend "s3" {
    bucket  = "recallist-terraform-state"
    key     = "env/dev/terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}

#############################
# IAM Role for Lambda
#############################
resource "aws_iam_role" "lambda_exec_role" {
  name = "recallist-lambda-vocab-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action = "sts:AssumeRole",
      Effect = "Allow",
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_custom_policy" {
  name = "recallist-lambda-vocab-custom-policy"
  role = aws_iam_role.lambda_exec_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "dynamodb:*",
          "bedrock:*" # for future use
        ],
        Effect   = "Allow",
        Resource = "*"
      }
    ]
  })
}

#############################
# DynamoDB Table for topics
#############################
resource "aws_dynamodb_table" "items_table" {
  name           = "recallist_items"
  billing_mode   = "PROVISIONED"
  read_capacity  = 1
  write_capacity = 1
  hash_key       = "user_id"
  range_key      = "item"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "item"
    type = "S"
  }
}

#############################
# DynamoDB API kyes table
#############################
resource "aws_dynamodb_table" "api_keys_table" {
  name           = "recallist_api_keys"
  billing_mode   = "PROVISIONED"
  read_capacity  = 1
  write_capacity = 1
  hash_key       = "api_key"
  range_key      = "user_id"

  attribute {
    name = "api_key"
    type = "S"
  }

  attribute {
    name = "user_id"
    type = "S"
  }
}

#############################
# Lambda Function
#############################
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "../lambda"
  output_path = "lambda.zip"
}

# TODO: Built by CI/CD pipeline, this is kind of a pain point now and should be automated better
resource "aws_lambda_layer_version" "recallist_layer" {
  filename            = "../layers/recallist_layer.zip"
  layer_name          = "recallist-layer"
  compatible_runtimes = ["python3.11"]
  description         = "Basic Recallist layer with FastAPI and Mangum dependencies."
  source_code_hash    = filebase64sha256("../lambda/requirements.txt")
}

resource "aws_lambda_function" "api_handler" {
  function_name    = "recallist-api-handler"
  role             = aws_iam_role.lambda_exec_role.arn
  handler          = "app.handler"
  runtime          = "python3.11"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = 20 # Increase from default (3s) to allow for AI calls later
  memory_size      = 256
  publish          = true
  layers = [
    aws_lambda_layer_version.recallist_layer.arn
  ]
}

# Authorizer Lambda package
data "archive_file" "authorizer_zip" {
  type        = "zip"
  source_dir  = "../lambda_authorizer"
  output_path = "lambda_authorizer.zip"
}

# Either-Or Authorizer Lambda
resource "aws_lambda_function" "either_or_authorizer" {
  function_name    = "recallist-token-authorizer"
  role             = aws_iam_role.lambda_exec_role.arn
  handler          = "main.handler"
  runtime          = "python3.11"
  filename         = data.archive_file.authorizer_zip.output_path
  source_code_hash = data.archive_file.authorizer_zip.output_base64sha256
  timeout          = 5
  memory_size      = 128
  environment {
    variables = {
      API_KEYS_TABLE = aws_dynamodb_table.api_keys_table.name
    }
  }
}


# Build API Gateway authorizer URI
locals {
  authorizer_uri = "arn:aws:apigateway:${data.aws_region.current.name}:lambda:path/2015-03-31/functions/${aws_lambda_function.either_or_authorizer.arn}/invocations"
}

#############################
# HTTP API (API Gateway v2)
#############################
resource "aws_apigatewayv2_api" "recallist_http_api" {
  name          = "recallist-http-api"
  protocol_type = "HTTP"
}

# Lambda proxy integration for the FastAPI handler
resource "aws_apigatewayv2_integration" "lambda_integration" {
  api_id                 = aws_apigatewayv2_api.recallist_http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api_handler.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

#############################
# Cognito (JWT) authorizer for /api/*
#############################
resource "aws_cognito_user_pool" "recallist_user_pool" {
  name = "recallist-user-pool"

  password_policy {
    minimum_length    = 8
    require_numbers   = true
    require_uppercase = true
    require_lowercase = true
    require_symbols   = false
  }

  mfa_configuration = "OFF"

  auto_verified_attributes = ["email"]
}

# A client is needed to provide an audience for the JWT authorizer
resource "aws_cognito_user_pool_client" "recallist_client" {
  name         = "recallist-client"
  user_pool_id = aws_cognito_user_pool.recallist_user_pool.id
  generate_secret = false
}

resource "aws_apigatewayv2_authorizer" "jwt_cognito" {
  api_id           = aws_apigatewayv2_api.recallist_http_api.id
  name             = "recallist-cognito-jwt"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.recallist_client.id]
    issuer   = "https://cognito-idp.${data.aws_region.current.name}.amazonaws.com/${aws_cognito_user_pool.recallist_user_pool.id}"
  }
}

#############################
# Lambda REQUEST authorizer for /gpt/* (simple token check)
#############################
resource "aws_lambda_permission" "allow_httpapi_authorizer" {
  statement_id  = "AllowInvokeFromHttpApiAuthorizer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.either_or_authorizer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.recallist_http_api.execution_arn}/authorizers/*"
}

resource "aws_apigatewayv2_authorizer" "lambda_request" {
  api_id                            = aws_apigatewayv2_api.recallist_http_api.id
  name                              = "recallist-token-authorizer"
  authorizer_type                   = "REQUEST"
  authorizer_uri                    = local.authorizer_uri
  identity_sources                  = ["$request.header.x-api-key"]
  authorizer_payload_format_version = "2.0"
  enable_simple_responses           = true
}

#############################
# Routes
#############################
# Public docs for /api
resource "aws_apigatewayv2_route" "api_openapi" {
  api_id    = aws_apigatewayv2_api.recallist_http_api.id
  route_key = "GET /api/openapi.json"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
  authorization_type = "NONE"
}

resource "aws_apigatewayv2_route" "api_docs" {
  api_id    = aws_apigatewayv2_api.recallist_http_api.id
  route_key = "GET /api/docs"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
  authorization_type = "NONE"
}

# Protected /api/* via Cognito JWT
resource "aws_apigatewayv2_route" "api_proxy" {
  api_id             = aws_apigatewayv2_api.recallist_http_api.id
  route_key          = "ANY /api/{proxy+}"
  target             = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt_cognito.id
}

# Public docs for /gpt
resource "aws_apigatewayv2_route" "gpt_openapi" {
  api_id    = aws_apigatewayv2_api.recallist_http_api.id
  route_key = "GET /gpt/openapi.json"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
  authorization_type = "NONE"
}

resource "aws_apigatewayv2_route" "gpt_docs" {
  api_id    = aws_apigatewayv2_api.recallist_http_api.id
  route_key = "GET /gpt/docs"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
  authorization_type = "NONE"
}

# Protected /gpt/* via Lambda REQUEST authorizer
resource "aws_apigatewayv2_route" "gpt_proxy" {
  api_id             = aws_apigatewayv2_api.recallist_http_api.id
  route_key          = "ANY /gpt/{proxy+}"
  target             = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda_request.id
}

#############################
# Stage (auto-deploy)
#############################
resource "aws_apigatewayv2_stage" "default" {
  api_id = aws_apigatewayv2_api.recallist_http_api.id
  name   = "$default"
  auto_deploy = true
}

#############################
# Permissions for the main Lambda to be invoked by HTTP API
#############################
resource "aws_lambda_permission" "allow_httpapi_invoke" {
  statement_id  = "AllowInvokeFromHttpApi"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_handler.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.recallist_http_api.execution_arn}/*/*"
}

#############################
# Outputs
#############################

output "http_api_endpoint" {
  value = aws_apigatewayv2_api.recallist_http_api.api_endpoint
  description = "HTTP API base URL"
}