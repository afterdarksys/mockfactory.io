# MockFactory Terraform Example
# Test your AWS infrastructure without paying Amazon

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Configure AWS provider to use MockFactory
provider "aws" {
  region = "us-east-1"

  # Mock credentials (MockFactory doesn't validate these)
  access_key = "mock"
  secret_key = "mock"

  # Skip AWS-specific validation
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  # Point to MockFactory instead of real AWS
  endpoints {
    ec2 = "https://env-YOUR_ENV_ID.mockfactory.io/aws/ec2"
    s3  = "https://env-YOUR_ENV_ID.mockfactory.io/aws/s3"
  }
}

# Launch "fake" EC2 instances
resource "aws_instance" "web" {
  count         = 3
  ami           = "ami-ubuntu-22.04"
  instance_type = "t2.micro"

  tags = {
    Name        = "web-server-${count.index}"
    Environment = "testing"
    ManagedBy   = "terraform"
  }
}

# Create "fake" S3 bucket
resource "aws_s3_bucket" "data" {
  bucket = "my-test-data-bucket-${random_id.bucket_suffix.hex}"

  tags = {
    Name        = "Test Data Bucket"
    Environment = "testing"
  }
}

# Random bucket suffix
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# Outputs
output "instance_ids" {
  value = aws_instance.web[*].id
  description = "Mock EC2 instance IDs (stored in PostgreSQL)"
}

output "instance_public_ips" {
  value = aws_instance.web[*].public_ip
  description = "Mock public IPs (fake but realistic)"
}

output "bucket_name" {
  value = aws_s3_bucket.data.id
  description = "Mock S3 bucket name"
}

output "total_cost" {
  value = "REAL AWS: ~$50/month | MockFactory: $0"
  description = "Cost comparison"
}
