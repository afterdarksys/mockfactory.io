# Full-stack AWS emulation example using MockFactory provider

terraform {
  required_providers {
    mockfactory = {
      source  = "mockfactory.io/app/mockfactory"
      version = "~> 0.1"
    }
  }
}

provider "mockfactory" {
  api_key        = var.mockfactory_api_key
  environment_id = var.environment_id
}

# Variables
variable "mockfactory_api_key" {
  type      = string
  sensitive = true
}

variable "environment_id" {
  type = string
}

# VPC
resource "mockfactory_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "test-vpc"
    Environment = "dev"
    ManagedBy   = "Terraform"
  }
}

# Public Subnet
resource "mockfactory_subnet" "public" {
  vpc_id                  = mockfactory_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "us-east-1a"
  map_public_ip_on_launch = true

  tags = {
    Name = "public-subnet"
    Type = "public"
  }
}

# Private Subnet
resource "mockfactory_subnet" "private" {
  vpc_id            = mockfactory_vpc.main.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "us-east-1a"

  tags = {
    Name = "private-subnet"
    Type = "private"
  }
}

# Security Group for Lambda
resource "mockfactory_security_group" "lambda_sg" {
  name        = "lambda-security-group"
  description = "Security group for Lambda functions"
  vpc_id      = mockfactory_vpc.main.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "lambda-sg"
  }
}

# DynamoDB Table
resource "mockfactory_dynamodb_table" "users" {
  name         = "users"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "created_at"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "N"
  }

  attribute {
    name = "email"
    type = "S"
  }

  global_secondary_index {
    name            = "email-index"
    hash_key        = "email"
    projection_type = "ALL"
  }

  tags = {
    Name        = "users-table"
    Environment = "dev"
  }
}

# SQS Queue for background jobs
resource "mockfactory_sqs_queue" "jobs" {
  name                       = "background-jobs"
  visibility_timeout_seconds = 30
  message_retention_seconds  = 345600  # 4 days
  max_message_size           = 262144  # 256 KB

  tags = {
    Name = "background-jobs-queue"
  }
}

# SQS Dead Letter Queue
resource "mockfactory_sqs_queue" "dlq" {
  name                      = "background-jobs-dlq"
  message_retention_seconds = 1209600  # 14 days

  tags = {
    Name = "background-jobs-dlq"
  }
}

# Lambda Function - API Handler
resource "mockfactory_lambda_function" "api_handler" {
  function_name = "api-handler"
  runtime       = "python3.9"
  handler       = "index.handler"
  memory_size   = 256
  timeout       = 30

  filename         = "${path.module}/lambda/api-handler.zip"
  source_code_hash = filebase64sha256("${path.module}/lambda/api-handler.zip")

  environment {
    variables = {
      DYNAMODB_TABLE = mockfactory_dynamodb_table.users.name
      SQS_QUEUE_URL  = mockfactory_sqs_queue.jobs.url
      ENVIRONMENT    = "dev"
    }
  }

  vpc_config {
    subnet_ids         = [mockfactory_subnet.private.id]
    security_group_ids = [mockfactory_security_group.lambda_sg.id]
  }

  tags = {
    Name = "api-handler"
  }
}

# Lambda Function - Background Worker
resource "mockfactory_lambda_function" "worker" {
  function_name = "background-worker"
  runtime       = "python3.9"
  handler       = "worker.handler"
  memory_size   = 512
  timeout       = 60

  filename         = "${path.module}/lambda/worker.zip"
  source_code_hash = filebase64sha256("${path.module}/lambda/worker.zip")

  environment {
    variables = {
      DYNAMODB_TABLE = mockfactory_dynamodb_table.users.name
      ENVIRONMENT    = "dev"
    }
  }

  tags = {
    Name = "background-worker"
  }
}

# Outputs
output "vpc_id" {
  value = mockfactory_vpc.main.id
}

output "public_subnet_id" {
  value = mockfactory_subnet.public.id
}

output "dynamodb_table_name" {
  value = mockfactory_dynamodb_table.users.name
}

output "sqs_queue_url" {
  value = mockfactory_sqs_queue.jobs.url
}

output "api_function_arn" {
  value = mockfactory_lambda_function.api_handler.arn
}

output "estimated_monthly_cost" {
  value = "Estimated: $5.00/month (500 credits) for 100K Lambda invocations + 50K DynamoDB ops"
}
