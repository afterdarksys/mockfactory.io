# Terraform Provider: MockFactory

Custom Terraform provider for managing MockFactory.io emulated AWS resources.

## Overview

This provider allows you to use Terraform to manage mock AWS resources on MockFactory.io:
- **Pay-per-use**: Only pay credits when resources are actively used
- **Test IaC**: Test your Terraform code before deploying to real AWS
- **Dev Environments**: Cheap dev/test environments that behave like AWS

## Architecture

```
User writes Terraform → MockFactory Provider → MockFactory API → Creates resources
                                                ↓
                                         Real OCI Infrastructure
                                         (VPCs, Containers, etc.)
```

## Installation

```bash
# Clone provider repo
git clone https://github.com/mockfactory/terraform-provider-mockfactory
cd terraform-provider-mockfactory

# Build provider
go build -o terraform-provider-mockfactory

# Install locally
mkdir -p ~/.terraform.d/plugins/mockfactory.io/app/mockfactory/0.1.0/darwin_amd64
cp terraform-provider-mockfactory ~/.terraform.d/plugins/mockfactory.io/app/mockfactory/0.1.0/darwin_amd64/
```

## Usage

### Provider Configuration

```hcl
terraform {
  required_providers {
    mockfactory = {
      source  = "mockfactory.io/app/mockfactory"
      version = "~> 0.1"
    }
  }
}

provider "mockfactory" {
  api_key = var.mockfactory_api_key  # From environment: TF_VAR_mockfactory_api_key
  api_url = "https://mockfactory.io/api/v1"
  environment_id = "env-abc123"  # Your MockFactory environment
}
```

### Example: Create VPC

```hcl
resource "mockfactory_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "test-vpc"
    Environment = "dev"
  }
}

resource "mockfactory_subnet" "public" {
  vpc_id            = mockfactory_vpc.main.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "us-east-1a"  # Mock AZ

  tags = {
    Name = "public-subnet"
  }
}
```

### Example: Create Lambda Function

```hcl
resource "mockfactory_lambda_function" "api" {
  function_name = "my-api-function"
  runtime       = "python3.9"
  handler       = "index.handler"
  memory_size   = 128  # MB
  timeout       = 30   # seconds

  # Code from local file
  filename      = "lambda.zip"
  source_code_hash = filebase64sha256("lambda.zip")

  environment {
    variables = {
      DB_HOST = "localhost"
      DEBUG   = "true"
    }
  }
}

# Invoke Lambda (charges credits!)
data "mockfactory_lambda_invocation" "test" {
  function_name = mockfactory_lambda_function.api.function_name

  input = jsonencode({
    key1 = "value1"
    key2 = "value2"
  })
}

output "lambda_result" {
  value = data.mockfactory_lambda_invocation.test.result
}
```

### Example: Create DynamoDB Table

```hcl
resource "mockfactory_dynamodb_table" "users" {
  name           = "users"
  billing_mode   = "PAY_PER_REQUEST"  # Charged per request
  hash_key       = "user_id"
  range_key      = "timestamp"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "N"
  }

  tags = {
    Name = "users-table"
  }
}
```

### Example: Create SQS Queue

```hcl
resource "mockfactory_sqs_queue" "notifications" {
  name                       = "notifications"
  visibility_timeout_seconds = 30
  message_retention_seconds  = 345600  # 4 days

  tags = {
    Environment = "dev"
  }
}
```

## How It Works

### 1. No Resources Created Until Used

```hcl
# This creates METADATA only (FREE!)
resource "mockfactory_lambda_function" "api" {
  function_name = "my-function"
  runtime       = "python3.9"
  memory_size   = 128
}

# This actually RUNS the container (COSTS CREDITS!)
data "mockfactory_lambda_invocation" "test" {
  function_name = mockfactory_lambda_function.api.function_name
  input = jsonencode({ test: "data" })
}
```

### 2. AWS-Style Billing

- **Lambda**: Per GB-second + per request
- **DynamoDB**: Per read/write request
- **SQS**: Per API request
- **VPC**: No charge for VPC itself, charges for data transfer

### 3. Real Infrastructure

Behind the scenes, MockFactory creates:
- **VPCs** → Real OCI VCNs (isolated compartment)
- **Lambda** → Real Docker containers
- **DynamoDB** → PostgreSQL with JSONB
- **SQS** → Real Redis queues

## Provider Implementation

### Required Resources

```go
// provider.go
package main

import (
    "github.com/hashicorp/terraform-plugin-sdk/v2/helper/schema"
)

func Provider() *schema.Provider {
    return &schema.Provider{
        Schema: map[string]*schema.Schema{
            "api_key": {
                Type:        schema.TypeString,
                Required:    true,
                Sensitive:   true,
                DefaultFunc: schema.EnvDefaultFunc("MOCKFACTORY_API_KEY", nil),
            },
            "api_url": {
                Type:     schema.TypeString,
                Optional: true,
                Default:  "https://mockfactory.io/api/v1",
            },
            "environment_id": {
                Type:     schema.TypeString,
                Required: true,
            },
        },
        ResourcesMap: map[string]*schema.Resource{
            "mockfactory_vpc":              resourceVPC(),
            "mockfactory_subnet":           resourceSubnet(),
            "mockfactory_security_group":   resourceSecurityGroup(),
            "mockfactory_lambda_function":  resourceLambdaFunction(),
            "mockfactory_dynamodb_table":   resourceDynamoDBTable(),
            "mockfactory_sqs_queue":        resourceSQSQueue(),
        },
        DataSourcesMap: map[string]*schema.Resource{
            "mockfactory_lambda_invocation": dataSourceLambdaInvocation(),
        },
        ConfigureFunc: providerConfigure,
    }
}
```

## Cost Estimation

Use Terraform to estimate MockFactory costs:

```bash
# Show what will be created
terraform plan

# MockFactory-specific cost estimate
terraform plan -out=tfplan
mockfactory-cost-estimator tfplan

# Output:
# Estimated monthly cost: $2.45 (245 credits)
# - Lambda invocations: 100,000 @ 100ms = $1.50
# - DynamoDB reads: 10,000 = $0.25
# - DynamoDB writes: 1,000 = $0.70
```

## Comparison: Real AWS vs MockFactory

| Resource | AWS Cost | MockFactory Cost | Notes |
|----------|----------|------------------|-------|
| Lambda (1M invocations, 128MB, 100ms) | $2.08 | $0.62 | 70% cheaper |
| DynamoDB (1M reads) | $0.25 | $0.25 | Same price |
| SQS (1M requests) | $0.40 | $0.40 | Same price |
| VPC | Free | Free | Free metadata |
| Data Transfer | $0.09/GB | $0.09/GB | Same as AWS |

**Benefits over real AWS:**
- No minimum charges
- No reserved capacity needed
- Instant teardown (no orphaned resources)
- Perfect for testing Terraform code

## Next Steps

1. **Build the provider**: Go implementation (terraform-plugin-sdk)
2. **Register with Terraform**: Publish to registry
3. **Add more resources**: EC2, RDS, ElastiCache, etc.
4. **Cost calculator**: Built-in cost estimation
