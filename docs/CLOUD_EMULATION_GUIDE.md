# 🚀 MockFactory Cloud Emulation - Test AWS/GCP/Azure Without Paying Them

## What Is This?

**MockFactory emulates AWS, GCP, and Azure APIs** so you can test your cloud applications **without spending a dime on real cloud providers.**

```
Your App → MockFactory → Fake Cloud Resources → $0 Cloud Bills
```

## Why Use MockFactory?

### The Problem:
- Testing on **real AWS**: $500/month for test environments
- Every developer needs their own cloud account
- CI/CD pipelines rack up huge bills
- Accidentally leave resources running = $$$ wasted

### The Solution:
- **MockFactory**: $20/month for unlimited fake cloud testing
- Test locally or in CI/CD
- Auto-shutdown prevents runaway costs
- Get realistic API responses without the bill

---

## 🟧 AWS Emulation

### Supported Services:
- **EC2**: Virtual machines
- **S3**: Object storage
- **Lambda**: Serverless functions (coming soon)
- **RDS**: Databases (coming soon)

### Quick Start - Python (boto3)

```python
import boto3

# Point boto3 at MockFactory instead of AWS
ec2 = boto3.client(
    'ec2',
    endpoint_url='https://env-abc123.mockfactory.io/aws/ec2',
    aws_access_key_id='mock',
    aws_secret_access_key='mock',
    region_name='us-east-1'
)

# Launch a "fake" EC2 instance
response = ec2.run_instances(
    ImageId='ami-ubuntu',
    InstanceType='t2.micro',
    MinCount=1,
    MaxCount=1
)

print(f"Launched instance: {response['Instances'][0]['InstanceId']}")
# Output: Launched instance: i-1234567890abcdef0

# Your app thinks it's real AWS!
# But it's all stored in PostgreSQL, costs you $0
```

### Terraform Example

```hcl
# Configure AWS provider to use MockFactory
provider "aws" {
  region                      = "us-east-1"
  access_key                  = "mock"
  secret_key                  = "mock"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    ec2 = "https://env-abc123.mockfactory.io/aws/ec2"
    s3  = "https://env-abc123.mockfactory.io/aws/s3"
  }
}

# Now use Terraform normally
resource "aws_instance" "web" {
  ami           = "ami-ubuntu"
  instance_type = "t2.micro"

  tags = {
    Name = "MockFactory Test Server"
  }
}

# terraform apply → Creates mock EC2 in PostgreSQL
# Real AWS bill: $0.00
```

### S3 Example

```python
import boto3

s3 = boto3.client(
    's3',
    endpoint_url='https://env-abc123.mockfactory.io/aws/s3',
    aws_access_key_id='mock',
    aws_secret_access_key='mock'
)

# Create bucket
s3.create_bucket(Bucket='my-test-bucket')

# Upload file
s3.put_object(
    Bucket='my-test-bucket',
    Key='data.json',
    Body=b'{"test": "data"}'
)

# Download file
obj = s3.get_object(Bucket='my-test-bucket', Key='data.json')
print(obj['Body'].read())
```

---

## 🔵 GCP Emulation

### Supported Services:
- **Compute Engine**: Virtual machines
- **Cloud Storage**: Object storage
- **Cloud SQL**: Databases (coming soon)

### Quick Start - Python (google-cloud)

```python
from google.cloud import compute_v1

# Set environment variables
import os
os.environ['GOOGLE_CLOUD_PROJECT'] = 'mock-project'
os.environ['COMPUTE_ENGINE_ENDPOINT'] = 'https://env-abc123.mockfactory.io/gcp'

# Create compute client
client = compute_v1.InstancesClient()

# Launch instance
instance = compute_v1.Instance()
instance.name = "test-vm"
instance.machine_type = "zones/us-central1-a/machineTypes/e2-micro"

operation = client.insert(
    project='mock-project',
    zone='us-central1-a',
    instance_resource=instance
)

print(f"Created instance: {instance.name}")
# Real GCP bill: $0.00
```

### Cloud Storage Example

```python
from google.cloud import storage

storage_client = storage.Client(
    project='mock-project',
    # Point to MockFactory
    _http=custom_session  # Configure HTTP session to hit MockFactory
)

# Create bucket
bucket = storage_client.create_bucket('my-mock-bucket')

# Upload file
blob = bucket.blob('test.txt')
blob.upload_from_string('Hello MockFactory!')

# Download file
content = blob.download_as_text()
print(content)
```

---

## ☁️ Azure Emulation

### Supported Services:
- **Virtual Machines**
- **Blob Storage**
- **Cosmos DB** (coming soon)

### Quick Start - Python (azure-sdk)

```python
from azure.mgmt.compute import ComputeManagementClient
from azure.identity import DefaultAzureCredential

# Configure to use MockFactory
credential = DefaultAzureCredential()
compute_client = ComputeManagementClient(
    credential,
    subscription_id='mock-subscription',
    base_url='https://env-abc123.mockfactory.io/azure'
)

# Create VM
vm_parameters = {
    'location': 'eastus',
    'properties': {
        'hardwareProfile': {'vmSize': 'Standard_B1s'},
        'osProfile': {
            'computerName': 'test-vm',
            'adminUsername': 'azureuser'
        }
    }
}

vm = compute_client.virtual_machines.begin_create_or_update(
    'mock-resource-group',
    'test-vm',
    vm_parameters
).result()

print(f"Created VM: {vm.name}")
# Real Azure bill: $0.00
```

---

## 💡 Real-World Use Cases

### 1. **CI/CD Testing**
```yaml
# GitHub Actions
- name: Test against mock AWS
  env:
    AWS_ENDPOINT: https://env-${{ github.run_id }}.mockfactory.io/aws/ec2
  run: |
    pytest tests/test_infrastructure.py
    # No real AWS resources created
    # No cleanup needed
    # $0 cost
```

### 2. **Local Development**
```bash
# Developer laptop
export AWS_ENDPOINT_URL="https://env-dev-john.mockfactory.io/aws/ec2"
python my_aws_app.py

# Test your infrastructure code locally
# No need for AWS credentials
# No accidental cloud charges
```

### 3. **Training & Workshops**
```python
# Give each student their own "AWS account"
# Actually just MockFactory environments
# No one can accidentally rack up bills
# Perfect for learning Terraform/CloudFormation
```

### 4. **Integration Testing**
```python
# Test that your app handles AWS failures correctly
# Simulate outages without breaking real infrastructure
# Test S3 upload/download flows
# Validate IAM permissions logic
```

---

## 🎯 How It Works

### Architecture

```
┌─────────────────────────────────────┐
│   Your App (boto3, Terraform, etc) │
└─────────────────┬───────────────────┘
                  │
                  │ AWS/GCP/Azure API Calls
                  ↓
┌─────────────────────────────────────┐
│      MockFactory API Gateway         │
│  (Detects provider from endpoint)   │
└─────────────────┬───────────────────┘
                  │
       ┌──────────┼──────────┐
       ↓          ↓          ↓
┌─────────┐ ┌─────────┐ ┌──────────┐
│AWS Emu  │ │GCP Emu  │ │Azure Emu │
└────┬────┘ └────┬────┘ └────┬─────┘
     │           │           │
     └───────────┴───────────┘
                 ↓
┌─────────────────────────────────────┐
│   PostgreSQL (Resource State)       │
│   - mock_ec2_instances              │
│   - mock_s3_buckets                 │
│   - mock_gcp_compute_instances      │
│   - mock_azure_vms                  │
└─────────────────────────────────────┘
```

### What Gets Mocked:
- **EC2 instances**: Just rows in Postgres with fake IPs
- **S3 objects**: Metadata in DB, files in OCI Object Storage
- **API responses**: Valid AWS/GCP/Azure XML/JSON
- **Resource IDs**: Realistic (i-abc123, ami-def456, etc.)

### What Doesn't Work (Yet):
- **Actual compute**: No real VMs spin up
- **Code execution**: Lambda/Functions don't run code
- **Networking**: No actual VPC/subnets created

**But for testing infrastructure-as-code, API integration, and learning cloud platforms → it's perfect!**

---

## 💰 Pricing Comparison

### Testing 50 EC2 instances for 1 week:

| Provider | Cost |
|----------|------|
| **Real AWS** | ~$200 (t2.micro × 50 × 168 hours) |
| **MockFactory** | **$0** (unlimited mock resources) |

### Leaving resources running by accident:

| Provider | Cost |
|----------|------|
| **Real AWS** | $$$$ (keeps charging until you notice) |
| **MockFactory** | **$0** (auto-shutdown after 4 hours) |

---

## 🔧 Getting Started

### 1. Create Environment
```bash
curl -X POST https://mockfactory.io/api/v1/environments \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "name": "AWS Test Environment",
    "services": [
      {"type": "aws_ec2"},
      {"type": "aws_s3"}
    ]
  }'

# Returns: env-abc123
```

### 2. Get Your Endpoint
```
https://env-abc123.mockfactory.io/aws/ec2
https://env-abc123.mockfactory.io/aws/s3
https://env-abc123.mockfactory.io/gcp/compute/v1
https://env-abc123.mockfactory.io/azure/subscriptions/...
```

### 3. Point Your Code
```python
# Before:
ec2 = boto3.client('ec2')  # Hits real AWS

# After:
ec2 = boto3.client('ec2',
    endpoint_url='https://env-abc123.mockfactory.io/aws/ec2')
# Hits MockFactory → $0
```

---

## 📊 Supported Operations

### AWS EC2
- ✅ RunInstances
- ✅ DescribeInstances
- ✅ TerminateInstances
- ✅ StopInstances
- ✅ StartInstances

### AWS S3
- ✅ CreateBucket
- ✅ ListBuckets
- ✅ PutObject
- ✅ GetObject
- ✅ DeleteObject
- ✅ ListObjects

### GCP Compute
- ✅ instances.insert
- ✅ instances.list
- ✅ instances.get
- ✅ instances.delete

### GCP Storage
- ✅ buckets.insert
- ✅ buckets.list
- ✅ buckets.get
- ✅ buckets.delete

### Azure VMs
- ✅ Create/Update VM
- ✅ List VMs
- ✅ Get VM
- ✅ Delete VM
- ✅ Start VM
- ✅ Stop VM

### Azure Storage
- ✅ Create Storage Account
- ✅ List Storage Accounts
- ✅ Delete Storage Account

---

## 🤝 Who Is This For?

✅ **DevOps Engineers**: Test Terraform/CloudFormation locally
✅ **Developers**: Build cloud apps without AWS credentials
✅ **Students**: Learn AWS/GCP/Azure without spending money
✅ **Companies**: Cut cloud testing costs by 90%
✅ **CI/CD Pipelines**: Test infrastructure changes safely

---

## 🚨 Limitations

**MockFactory is NOT:**
- ❌ A production cloud provider
- ❌ A replacement for real AWS/GCP/Azure
- ❌ Able to run actual compute workloads
- ❌ 100% API compatible (we mock the most common operations)

**MockFactory IS:**
- ✅ Perfect for testing infrastructure-as-code
- ✅ Great for learning cloud platforms
- ✅ Ideal for CI/CD validation
- ✅ Excellent for integration testing

---

## 📚 Examples Repository

Check out real-world examples:
- `/examples/terraform-aws/` - Deploy fake EC2 cluster
- `/examples/boto3-s3/` - S3 upload/download testing
- `/examples/github-actions/` - CI/CD integration
- `/examples/docker-compose/` - Local development setup

---

## 🎓 Learn More

- **API Documentation**: https://mockfactory.io/docs
- **Dashboard**: https://mockfactory.io/app.html
- **Support**: support@mockfactory.io

---

## 💎 The Secret Sauce

MockFactory translates cloud provider APIs into PostgreSQL operations:

```python
# When you call:
ec2.run_instances(InstanceType='t2.micro')

# MockFactory does:
INSERT INTO mock_ec2_instances (
    id, instance_type, state, private_ip, public_ip
) VALUES (
    'i-abc123', 't2.micro', 'running',
    '10.0.1.5', '54.123.45.67'
)

# Returns AWS-compliant XML:
<RunInstancesResponse>
  <instanceId>i-abc123</instanceId>
  <instanceState><name>running</name></instanceState>
  ...
</RunInstancesResponse>
```

**Your code thinks it's AWS. Your wallet knows it's not.** 😎

---

**Built with ❤️ by MockFactory**
*Test like you're on the cloud. Pay like you're not.*
