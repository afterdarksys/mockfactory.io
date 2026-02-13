# OCI Provider Configuration
variable "tenancy_ocid" {
  description = "OCI Tenancy OCID"
  type        = string
}

variable "user_ocid" {
  description = "OCI User OCID"
  type        = string
}

variable "fingerprint" {
  description = "OCI API Key Fingerprint"
  type        = string
}

variable "private_key_path" {
  description = "Path to OCI API private key"
  type        = string
  default     = "~/.oci/oci_api_key.pem"
}

variable "region" {
  description = "OCI Region"
  type        = string
  default     = "us-ashburn-1"
}

# Compartment Configuration
variable "core_compartment_ocid" {
  description = "OCID for core infrastructure compartment (undateable-compartment)"
  type        = string
}

variable "mock_compartment_ocid" {
  description = "OCID for mock AWS resources compartment (mock-aws-compartment)"
  type        = string
}

# Network Configuration
variable "vcn_cidr" {
  description = "CIDR block for VCN"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for public subnet"
  type        = string
  default     = "10.0.1.0/24"
}

variable "private_subnet_cidr" {
  description = "CIDR block for private subnet"
  type        = string
  default     = "10.0.2.0/24"
}

# OKE Cluster Configuration
variable "oke_cluster_name" {
  description = "Name of the OKE cluster"
  type        = string
  default     = "mockfactory-cluster"
}

variable "kubernetes_version" {
  description = "Kubernetes version for OKE"
  type        = string
  default     = "v1.28.2"
}

variable "node_pool_size" {
  description = "Number of worker nodes in OKE cluster"
  type        = number
  default     = 14
}

variable "node_shape" {
  description = "Shape for OKE worker nodes"
  type        = string
  default     = "VM.Standard.E4.Flex"
}

variable "node_ocpus" {
  description = "OCPUs per node"
  type        = number
  default     = 2
}

variable "node_memory_gb" {
  description = "Memory in GB per node"
  type        = number
  default     = 16
}

# Load Balancer Configuration
variable "lb_shape" {
  description = "Load balancer shape"
  type        = string
  default     = "flexible"
}

variable "lb_min_bandwidth_mbps" {
  description = "Minimum bandwidth for flexible load balancer"
  type        = number
  default     = 10
}

variable "lb_max_bandwidth_mbps" {
  description = "Maximum bandwidth for flexible load balancer"
  type        = number
  default     = 100
}

# Application Configuration
variable "domain_name" {
  description = "Domain name for MockFactory"
  type        = string
  default     = "mockfactory.io"
}

variable "environment" {
  description = "Environment name (production, staging, dev)"
  type        = string
  default     = "production"
}

# Object Storage Configuration
variable "bucket_name" {
  description = "Name for cloud emulation storage bucket"
  type        = string
  default     = "mockfactory-cloud-emulation"
}

variable "bucket_storage_tier" {
  description = "Storage tier for buckets"
  type        = string
  default     = "Standard"
}

# Database Configuration
variable "postgres_shape" {
  description = "Shape for PostgreSQL database (if using managed DB)"
  type        = string
  default     = "VM.Standard.E4.Flex"
}

variable "postgres_storage_gb" {
  description = "Storage size for PostgreSQL in GB"
  type        = number
  default     = 100
}

# Redis Configuration
variable "redis_shape" {
  description = "Shape for Redis instance (if using OCI Cache)"
  type        = string
  default     = "VM.Standard.E4.Flex"
}

# Tags
variable "common_tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default = {
    Project     = "MockFactory"
    ManagedBy   = "Terraform"
    Environment = "production"
  }
}

# Auto-Shutdown Configuration
variable "enable_auto_shutdown" {
  description = "Enable auto-shutdown for dev environments"
  type        = bool
  default     = true
}

variable "auto_shutdown_time" {
  description = "Time for auto-shutdown (HH:MM format, UTC)"
  type        = string
  default     = "02:00"
}
