"""
Cloud Resource Models - AWS, GCP, Azure Mock Resources
Stores state for all emulated cloud resources
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, JSON, Enum, Boolean, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.core.database import Base


class CloudProvider(str, enum.Enum):
    """Supported cloud providers"""
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"


class ResourceStatus(str, enum.Enum):
    """Resource lifecycle states"""
    CREATING = "creating"
    RUNNING = "running"
    STOPPED = "stopped"
    TERMINATED = "terminated"
    ERROR = "error"


# ============================================================================
# AWS Resources
# ============================================================================

class MockEC2Instance(Base):
    """Mock AWS EC2 Instance"""
    __tablename__ = "mock_ec2_instances"

    id = Column(String, primary_key=True)  # i-abc123def456
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)

    # EC2 specific fields
    instance_type = Column(String, nullable=False)  # t2.micro, m5.large, etc.
    ami_id = Column(String, nullable=False)  # ami-abc123
    state = Column(Enum(ResourceStatus), default=ResourceStatus.CREATING)

    # Network
    public_ip = Column(String, nullable=True)
    private_ip = Column(String, nullable=False)
    vpc_id = Column(String, nullable=True)
    subnet_id = Column(String, nullable=True)
    security_groups = Column(JSON, default=[])

    # Metadata
    tags = Column(JSON, default={})
    user_data = Column(Text, nullable=True)

    # Docker backing
    docker_container_id = Column(String, nullable=True)

    # Timestamps
    launch_time = Column(DateTime, default=datetime.utcnow)
    terminated_time = Column(DateTime, nullable=True)

    # Relationships
    environment = relationship("Environment", foreign_keys=[environment_id])


class MockS3Bucket(Base):
    """Mock AWS S3 Bucket"""
    __tablename__ = "mock_s3_buckets"

    id = Column(Integer, primary_key=True)
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)

    # S3 specific
    bucket_name = Column(String, unique=True, nullable=False, index=True)
    region = Column(String, default="us-east-1")
    versioning_enabled = Column(Boolean, default=False)

    # Storage backing (OCI Object Storage)
    oci_bucket_name = Column(String, nullable=True)
    oci_namespace = Column(String, nullable=True)

    # Metadata
    tags = Column(JSON, default={})
    total_objects = Column(Integer, default=0)
    total_size_bytes = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    environment = relationship("Environment", foreign_keys=[environment_id])


class MockS3Object(Base):
    """Mock AWS S3 Object"""
    __tablename__ = "mock_s3_objects"

    id = Column(Integer, primary_key=True)
    bucket_id = Column(Integer, ForeignKey("mock_s3_buckets.id"), nullable=False)

    # S3 object fields
    key = Column(String, nullable=False, index=True)  # path/to/file.txt
    size_bytes = Column(Integer, nullable=False)
    etag = Column(String, nullable=False)
    storage_class = Column(String, default="STANDARD")

    # Storage backing
    oci_object_name = Column(String, nullable=True)

    # Metadata
    metadata = Column(JSON, default={})
    content_type = Column(String, nullable=True)

    # Timestamps
    last_modified = Column(DateTime, default=datetime.utcnow)

    # Relationships
    bucket = relationship("MockS3Bucket", foreign_keys=[bucket_id])


class MockLambdaFunction(Base):
    """Mock AWS Lambda Function"""
    __tablename__ = "mock_lambda_functions"

    id = Column(String, primary_key=True)
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)

    # Lambda specific
    function_name = Column(String, nullable=False, index=True)
    runtime = Column(String, nullable=False)  # python3.11, nodejs18.x
    handler = Column(String, nullable=False)  # index.handler
    memory_mb = Column(Integer, default=128)
    timeout_seconds = Column(Integer, default=3)

    # Code storage
    code_s3_bucket = Column(String, nullable=True)
    code_s3_key = Column(String, nullable=True)
    code_sha256 = Column(String, nullable=True)

    # Container backing
    docker_image = Column(String, nullable=True)

    # Environment variables
    env_vars = Column(JSON, default={})

    # Metadata
    role_arn = Column(String, nullable=True)
    last_updated = Column(DateTime, default=datetime.utcnow)

    # Relationships
    environment = relationship("Environment", foreign_keys=[environment_id])


class MockRDSInstance(Base):
    """Mock AWS RDS Instance"""
    __tablename__ = "mock_rds_instances"

    id = Column(String, primary_key=True)  # db-ABC123
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)

    # RDS specific
    db_instance_identifier = Column(String, nullable=False, unique=True, index=True)
    engine = Column(String, nullable=False)  # postgres, mysql, mariadb
    engine_version = Column(String, nullable=False)
    db_instance_class = Column(String, nullable=False)  # db.t3.micro
    allocated_storage_gb = Column(Integer, nullable=False)

    # Database
    master_username = Column(String, nullable=False)
    master_password = Column(String, nullable=False)
    database_name = Column(String, nullable=True)
    port = Column(Integer, nullable=False)

    # Connection endpoint
    endpoint_address = Column(String, nullable=True)
    endpoint_port = Column(Integer, nullable=True)

    # PostgreSQL container backing
    postgres_container_id = Column(String, nullable=True)

    # Status
    status = Column(Enum(ResourceStatus), default=ResourceStatus.CREATING)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    environment = relationship("Environment", foreign_keys=[environment_id])


# ============================================================================
# GCP Resources
# ============================================================================

class MockGCPComputeInstance(Base):
    """Mock GCP Compute Engine Instance"""
    __tablename__ = "mock_gcp_compute_instances"

    id = Column(Integer, primary_key=True)
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)

    # GCP specific
    name = Column(String, nullable=False, index=True)
    zone = Column(String, nullable=False)  # us-central1-a
    machine_type = Column(String, nullable=False)  # e2-micro, n1-standard-1

    # Network
    external_ip = Column(String, nullable=True)
    internal_ip = Column(String, nullable=False)

    # Metadata
    labels = Column(JSON, default={})
    metadata = Column(JSON, default={})

    # Status
    status = Column(Enum(ResourceStatus), default=ResourceStatus.CREATING)

    # Docker backing
    docker_container_id = Column(String, nullable=True)

    # Timestamps
    creation_timestamp = Column(DateTime, default=datetime.utcnow)

    # Relationships
    environment = relationship("Environment", foreign_keys=[environment_id])


class MockGCPStorageBucket(Base):
    """Mock GCP Cloud Storage Bucket"""
    __tablename__ = "mock_gcp_storage_buckets"

    id = Column(Integer, primary_key=True)
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)

    # GCP specific
    name = Column(String, unique=True, nullable=False, index=True)
    location = Column(String, default="US")
    storage_class = Column(String, default="STANDARD")

    # Storage backing (OCI)
    oci_bucket_name = Column(String, nullable=True)

    # Metadata
    labels = Column(JSON, default={})

    # Timestamps
    time_created = Column(DateTime, default=datetime.utcnow)

    # Relationships
    environment = relationship("Environment", foreign_keys=[environment_id])


# ============================================================================
# Azure Resources
# ============================================================================

class MockAzureVM(Base):
    """Mock Azure Virtual Machine"""
    __tablename__ = "mock_azure_vms"

    id = Column(Integer, primary_key=True)
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)

    # Azure specific
    vm_name = Column(String, nullable=False, index=True)
    resource_group = Column(String, nullable=False)
    location = Column(String, nullable=False)  # eastus, westus2
    vm_size = Column(String, nullable=False)  # Standard_B1s

    # Network
    public_ip_address = Column(String, nullable=True)
    private_ip_address = Column(String, nullable=False)

    # OS
    os_type = Column(String, nullable=False)  # Linux, Windows
    image_reference = Column(JSON, nullable=True)

    # Status
    provisioning_state = Column(String, default="Creating")
    power_state = Column(String, default="running")

    # Docker backing
    docker_container_id = Column(String, nullable=True)

    # Metadata
    tags = Column(JSON, default={})

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    environment = relationship("Environment", foreign_keys=[environment_id])


class MockAzureBlobStorage(Base):
    """Mock Azure Blob Storage Account"""
    __tablename__ = "mock_azure_blob_storage"

    id = Column(Integer, primary_key=True)
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)

    # Azure specific
    account_name = Column(String, unique=True, nullable=False, index=True)
    location = Column(String, nullable=False)
    kind = Column(String, default="StorageV2")

    # Storage backing (OCI)
    oci_bucket_name = Column(String, nullable=True)

    # Metadata
    tags = Column(JSON, default={})

    # Timestamps
    created_time = Column(DateTime, default=datetime.utcnow)

    # Relationships
    environment = relationship("Environment", foreign_keys=[environment_id])
