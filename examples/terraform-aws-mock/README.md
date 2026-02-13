# Terraform + MockFactory Example

Test your AWS Terraform code **without creating real AWS resources or paying Amazon.**

## What This Does

This example creates:
- 3 "fake" EC2 instances
- 1 "fake" S3 bucket

**Cost on real AWS:** ~$50/month
**Cost on MockFactory:** $0

## Prerequisites

1. MockFactory account → https://mockfactory.io
2. Terraform installed → `brew install terraform`
3. Create an environment and get your environment ID

## Setup

1. **Create MockFactory Environment**
```bash
# Via API
curl -X POST https://mockfactory.io/api/v1/environments \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "name": "Terraform Test",
    "services": [{"type": "aws_ec2"}, {"type": "aws_s3"}]
  }'

# Or via dashboard: https://mockfactory.io/app.html
```

You'll get an environment ID like: `env-abc123`

2. **Update main.tf**
```hcl
# Replace YOUR_ENV_ID with your actual environment ID
endpoints {
  ec2 = "https://env-abc123.mockfactory.io/aws/ec2"
  s3  = "https://env-abc123.mockfactory.io/aws/s3"
}
```

3. **Initialize Terraform**
```bash
terraform init
```

## Usage

### Plan (Preview Changes)
```bash
terraform plan
```

Expected output:
```
Terraform will perform the following actions:

  # aws_instance.web[0] will be created
  + resource "aws_instance" "web" {
      + ami           = "ami-ubuntu-22.04"
      + instance_type = "t2.micro"
      + public_ip     = (known after apply)
      ...
    }

  # ... 2 more instances

  # aws_s3_bucket.data will be created
  + resource "aws_s3_bucket" "data" {
      + bucket = "my-test-data-bucket-a1b2c3d4"
      ...
    }

Plan: 4 to add, 0 to change, 0 to destroy.
```

### Apply (Create Resources)
```bash
terraform apply
```

**What happens:**
- Terraform sends API calls to MockFactory (not AWS)
- MockFactory creates rows in PostgreSQL
- Returns realistic AWS responses
- Terraform thinks it created real resources

**What you get:**
```
Outputs:

instance_ids = [
  "i-1a2b3c4d5e6f7g8h9",
  "i-9h8g7f6e5d4c3b2a1",
  "i-5f4e3d2c1b0a9h8g7"
]

instance_public_ips = [
  "54.123.45.67",
  "54.234.56.78",
  "54.345.67.89"
]

bucket_name = "my-test-data-bucket-a1b2c3d4"

total_cost = "REAL AWS: ~$50/month | MockFactory: $0"
```

### View State
```bash
terraform show
```

### Check MockFactory Dashboard
Visit https://mockfactory.io/app.html to see your mock resources!

### Destroy Resources
```bash
terraform destroy
```

This deletes the rows from PostgreSQL (instant, free).

## Comparison

### Using Real AWS
```bash
# Connect to real AWS
terraform apply
# → Creates real EC2 instances
# → Costs ~$50/month
# → Forgot to destroy? $$$
```

### Using MockFactory
```bash
# Connect to MockFactory
terraform apply
# → Creates mock EC2 instances in PostgreSQL
# → Costs $0
# → Auto-deletes after 4 hours
```

## What You Can Test

✅ **Terraform syntax** - Does your code compile?
✅ **Resource dependencies** - Are they in the right order?
✅ **Outputs** - Do they work correctly?
✅ **Variables** - Are they passed properly?
✅ **Modules** - Do they compose correctly?
✅ **State management** - Does Terraform track changes?

❌ **Actual networking** - No real VPC/subnets
❌ **SSH access** - No real VMs to connect to
❌ **Running code** - No actual compute

## CI/CD Integration

```yaml
# GitHub Actions
name: Test Terraform

on: [pull_request]

jobs:
  terraform:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2

      - name: Create MockFactory Environment
        run: |
          ENV_ID=$(curl -X POST https://mockfactory.io/api/v1/environments \
            -H "Authorization: Bearer ${{ secrets.MOCKFACTORY_API_KEY }}" \
            -d '{"name":"GH-${{ github.run_id }}"}' | jq -r .id)
          echo "ENV_ID=$ENV_ID" >> $GITHUB_ENV

      - name: Update Terraform Config
        run: |
          sed -i "s/YOUR_ENV_ID/$ENV_ID/g" main.tf

      - name: Terraform Plan
        run: terraform plan

      - name: Terraform Apply
        run: terraform apply -auto-approve

      # Environment auto-deletes, no cleanup needed!
```

## Pro Tips

1. **Use unique environment per test**
   - Prevents conflicts between developers
   - Each git branch can have its own environment

2. **Check the dashboard**
   - See all your mock resources visually
   - Verify Terraform actually created them

3. **Test failure scenarios**
   - What happens if EC2 launch fails?
   - What if S3 bucket already exists?

4. **Don't commit state files**
   - Add `*.tfstate*` to `.gitignore`
   - State contains your env ID

## Troubleshooting

### Error: "endpoint URL must be a valid URL"
**Fix:** Make sure your endpoint includes `https://`

### Error: "UnauthorizedOperation"
**Fix:** This shouldn't happen with MockFactory. Check your env ID is correct.

### No resources showing in dashboard?
**Fix:**
1. Verify environment ID is correct
2. Check you ran `terraform apply` (not just `plan`)
3. Refresh the dashboard

## Learn More

- **MockFactory Docs**: https://mockfactory.io/docs
- **Terraform AWS Provider**: https://registry.terraform.io/providers/hashicorp/aws

## Cost Breakdown

| Resource | Real AWS | MockFactory |
|----------|----------|-------------|
| 3x t2.micro instances (24/7) | $25.92/mo | $0 |
| S3 bucket + 1GB storage | $0.023/mo | $0 |
| Data transfer | $0.09/GB | $0 |
| **Developer time saved** | Priceless | ✨ |

---

**Remember:** This is for TESTING infrastructure code, not running production workloads.

Happy testing! 🚀
