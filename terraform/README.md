# MockFactory.io - Terraform Infrastructure

Infrastructure as Code for MockFactory.io on Oracle Cloud Infrastructure (OCI).

## Structure

```
terraform/
├── main.tf              # Main infrastructure definitions
├── variables.tf         # Input variables
├── outputs.tf           # Output values
├── terraform.tfvars     # Variable values (gitignored - create from example)
├── terraform.tfvars.example
├── modules/
│   ├── oke-cluster/     # OKE Kubernetes cluster
│   ├── vcn/             # Virtual Cloud Network
│   ├── load-balancer/   # Load balancer configuration
│   └── mock-compartment/ # Isolated compartment for mock AWS resources
└── environments/
    ├── production/
    └── staging/

```

## Key Resources Managed

### Core Infrastructure
- **OKE Cluster**: 14-node Kubernetes cluster for main application
- **VCN**: Virtual Cloud Network with subnets
- **Load Balancer**: undateable-lb (141.148.79.30)
- **Object Storage**: Buckets for S3/GCS/Azure emulation

### Mock AWS Infrastructure (Isolated)
- **Mock Compartment**: `mock-aws-compartment` - isolated from core infra
- **VCNs**: Created dynamically per user VPC request
- **Compute**: Lambda execution containers
- **Networking**: Security groups, subnets, route tables

## Prerequisites

```bash
# Install Terraform
brew install terraform

# Configure OCI CLI
oci setup config

# Verify OCI credentials
oci iam region list
```

## Usage

```bash
cd terraform/

# Initialize Terraform
terraform init

# Copy example variables
cp terraform.tfvars.example terraform.tfvars

# Edit with your values
vim terraform.tfvars

# Plan infrastructure changes
terraform plan

# Apply changes
terraform apply

# View outputs
terraform output
```

## Important Notes

- **Compartment Isolation**: Mock AWS resources MUST be in separate compartment
- **Cost Management**: Auto-shutdown enabled for dev environments
- **State Backend**: Consider using OCI Object Storage for remote state
- **Secrets**: Never commit terraform.tfvars - use Vault for sensitive values

## Compartments

- `undateable-compartment`: Core MockFactory infrastructure (OKE, LB, Storage)
- `mock-aws-compartment`: User-created mock AWS resources (VPCs, Lambda, etc.)

## Network Architecture

```
Internet → Load Balancer (141.148.79.30)
              ↓
          OKE Cluster (14 nodes)
              ↓
          Backend Services:
          - API (FastAPI)
          - PostgreSQL
          - Redis
          - Docker Proxy
          - Nginx

Isolated:
  Mock AWS Compartment → User VPCs/Lambdas/etc
```
