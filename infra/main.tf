provider "aws" {
  region = "us-east-1" # Change as needed
}

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
  handler          = "main.handler"
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

#############################
# REST API Gateway
#############################
resource "aws_api_gateway_rest_api" "recallist_api" {
  name        = "recallist-rest-api"
  description = "Recallist REST API for vocabulary app"
  body = templatefile("openapi.yaml", {
    lambda_arn = aws_lambda_function.api_handler.invoke_arn
    cognito_user_pool_arn = aws_cognito_user_pool.recallist_user_pool.arn
  })
}

# Lambda permission for API Gateway
resource "aws_lambda_permission" "allow_apigw" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_handler.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.recallist_api.execution_arn}/*/*"
}

resource "aws_api_gateway_stage" "recallist_stage" {
  deployment_id = aws_api_gateway_deployment.recallist_deployment.id
  rest_api_id   = aws_api_gateway_rest_api.recallist_api.id
  stage_name    = "dev"
}

# Deployment
resource "aws_api_gateway_deployment" "recallist_deployment" {
  depends_on  = [aws_api_gateway_rest_api.recallist_api]
  rest_api_id = aws_api_gateway_rest_api.recallist_api.id

  lifecycle {
    create_before_destroy = true
  }

  triggers = {
    always_deploy = timestamp()
  }
}

#############################
# Cognito User Pool
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

#############################
# Update Lambda permissions to allow Cognito claims in the event
#############################
resource "aws_lambda_permission" "allow_apigw_with_cognito" {
  statement_id  = "AllowExecutionFromAPIGatewayWithCognito"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_handler.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.recallist_api.execution_arn}/*/*"
}

#############################
# Outputs
#############################

# Empty, we do not copy it anywhere and it is safer to check in console / get it in the other app build :)