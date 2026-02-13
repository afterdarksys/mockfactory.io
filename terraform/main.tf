terraform {
  required_version = ">= 1.5.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 5.0"
    }
  }

  # TODO: Configure remote state backend
  # backend "s3" {
  #   bucket = "mockfactory-terraform-state"
  #   key    = "production/terraform.tfstate"
  #   region = "us-ashburn-1"
  #   endpoint = "https://namespace.compat.objectstorage.us-ashburn-1.oraclecloud.com"
  # }
}

provider "oci" {
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = var.user_ocid
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
  region           = var.region
}

# Data source for availability domains
data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

# Data source for existing compartments
data "oci_identity_compartment" "core" {
  id = var.core_compartment_ocid
}

data "oci_identity_compartment" "mock" {
  id = var.mock_compartment_ocid
}

# Virtual Cloud Network (Core Infrastructure)
resource "oci_core_vcn" "mockfactory_vcn" {
  compartment_id = var.core_compartment_ocid
  cidr_block     = var.vcn_cidr
  display_name   = "mockfactory-vcn"
  dns_label      = "mockfactory"

  freeform_tags = var.common_tags
}

# Internet Gateway
resource "oci_core_internet_gateway" "mockfactory_ig" {
  compartment_id = var.core_compartment_ocid
  vcn_id         = oci_core_vcn.mockfactory_vcn.id
  display_name   = "mockfactory-ig"
  enabled        = true

  freeform_tags = var.common_tags
}

# NAT Gateway (for private subnet)
resource "oci_core_nat_gateway" "mockfactory_nat" {
  compartment_id = var.core_compartment_ocid
  vcn_id         = oci_core_vcn.mockfactory_vcn.id
  display_name   = "mockfactory-nat"

  freeform_tags = var.common_tags
}

# Route Table for Public Subnet
resource "oci_core_route_table" "public_route_table" {
  compartment_id = var.core_compartment_ocid
  vcn_id         = oci_core_vcn.mockfactory_vcn.id
  display_name   = "public-route-table"

  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_internet_gateway.mockfactory_ig.id
  }

  freeform_tags = var.common_tags
}

# Route Table for Private Subnet
resource "oci_core_route_table" "private_route_table" {
  compartment_id = var.core_compartment_ocid
  vcn_id         = oci_core_vcn.mockfactory_vcn.id
  display_name   = "private-route-table"

  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_nat_gateway.mockfactory_nat.id
  }

  freeform_tags = var.common_tags
}

# Security List for Public Subnet
resource "oci_core_security_list" "public_security_list" {
  compartment_id = var.core_compartment_ocid
  vcn_id         = oci_core_vcn.mockfactory_vcn.id
  display_name   = "public-security-list"

  # Egress: Allow all outbound
  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }

  # Ingress: HTTPS (443)
  ingress_security_rules {
    protocol = "6" # TCP
    source   = "0.0.0.0/0"
    tcp_options {
      min = 443
      max = 443
    }
  }

  # Ingress: HTTP (80) - redirect to HTTPS
  ingress_security_rules {
    protocol = "6" # TCP
    source   = "0.0.0.0/0"
    tcp_options {
      min = 80
      max = 80
    }
  }

  # Ingress: SSH (22) - from specific IP only
  # TODO: Replace with your IP
  ingress_security_rules {
    protocol = "6" # TCP
    source   = "0.0.0.0/0" # CHANGE THIS TO YOUR IP!
    tcp_options {
      min = 22
      max = 22
    }
  }

  freeform_tags = var.common_tags
}

# Security List for Private Subnet
resource "oci_core_security_list" "private_security_list" {
  compartment_id = var.core_compartment_ocid
  vcn_id         = oci_core_vcn.mockfactory_vcn.id
  display_name   = "private-security-list"

  # Egress: Allow all outbound
  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }

  # Ingress: Allow all from VCN
  ingress_security_rules {
    protocol = "all"
    source   = var.vcn_cidr
  }

  freeform_tags = var.common_tags
}

# Public Subnet
resource "oci_core_subnet" "public_subnet" {
  compartment_id      = var.core_compartment_ocid
  vcn_id              = oci_core_vcn.mockfactory_vcn.id
  cidr_block          = var.public_subnet_cidr
  display_name        = "public-subnet"
  dns_label           = "public"
  route_table_id      = oci_core_route_table.public_route_table.id
  security_list_ids   = [oci_core_security_list.public_security_list.id]
  prohibit_public_ip_on_vnic = false

  freeform_tags = var.common_tags
}

# Private Subnet
resource "oci_core_subnet" "private_subnet" {
  compartment_id      = var.core_compartment_ocid
  vcn_id              = oci_core_vcn.mockfactory_vcn.id
  cidr_block          = var.private_subnet_cidr
  display_name        = "private-subnet"
  dns_label           = "private"
  route_table_id      = oci_core_route_table.private_route_table.id
  security_list_ids   = [oci_core_security_list.private_security_list.id]
  prohibit_public_ip_on_vnic = true

  freeform_tags = var.common_tags
}

# Object Storage Bucket (for S3/GCS/Azure emulation)
resource "oci_objectstorage_bucket" "cloud_emulation_bucket" {
  compartment_id = var.core_compartment_ocid
  namespace      = data.oci_objectstorage_namespace.namespace.namespace
  name           = var.bucket_name
  access_type    = "NoPublicAccess"
  storage_tier   = var.bucket_storage_tier

  freeform_tags = var.common_tags
}

data "oci_objectstorage_namespace" "namespace" {
  compartment_id = var.core_compartment_ocid
}

# TODO: Add OKE Cluster configuration
# TODO: Add Load Balancer configuration
# TODO: Add Database configuration (or use docker-compose on VM)
# TODO: Add Redis configuration
# TODO: Add mock-aws-compartment resources

# Outputs
output "vcn_id" {
  description = "VCN OCID"
  value       = oci_core_vcn.mockfactory_vcn.id
}

output "public_subnet_id" {
  description = "Public Subnet OCID"
  value       = oci_core_subnet.public_subnet.id
}

output "private_subnet_id" {
  description = "Private Subnet OCID"
  value       = oci_core_subnet.private_subnet.id
}

output "bucket_name" {
  description = "Object Storage Bucket Name"
  value       = oci_objectstorage_bucket.cloud_emulation_bucket.name
}

output "namespace" {
  description = "Object Storage Namespace"
  value       = data.oci_objectstorage_namespace.namespace.namespace
}
