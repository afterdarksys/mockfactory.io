"""
VPC/Networking Resources - AWS VPC backed by real OCI VCNs
Isolated from core infrastructure in separate compartment
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, JSON, Enum, Boolean, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.core.database import Base


class VPCState(str, enum.Enum):
    """VPC lifecycle states"""
    PENDING = "pending"
    AVAILABLE = "available"
    DELETING = "deleting"
    DELETED = "deleted"


class MockVPC(Base):
    """
    Mock AWS VPC backed by REAL OCI VCN
    Isolated in dedicated 'mock-aws-compartment'
    """
    __tablename__ = "mock_vpcs"

    id = Column(String, primary_key=True)  # vpc-abc123
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)

    # AWS VPC fields
    cidr_block = Column(String, nullable=False)  # 10.0.0.0/16
    instance_tenancy = Column(String, default="default")
    state = Column(Enum(VPCState), default=VPCState.PENDING)
    is_default = Column(Boolean, default=False)
    enable_dns_support = Column(Boolean, default=True)
    enable_dns_hostnames = Column(Boolean, default=False)

    # Tags
    tags = Column(JSON, default={})

    # OCI backing - REAL VCN!
    oci_vcn_id = Column(String, nullable=True)  # ocid1.vcn.oc1...
    oci_compartment_id = Column(String, nullable=True)  # Isolated compartment
    oci_internet_gateway_id = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    environment = relationship("Environment", foreign_keys=[environment_id])
    subnets = relationship("MockSubnet", back_populates="vpc", cascade="all, delete-orphan")
    security_groups = relationship("MockSecurityGroup", back_populates="vpc", cascade="all, delete-orphan")


class MockSubnet(Base):
    """
    Mock AWS Subnet backed by REAL OCI Subnet
    """
    __tablename__ = "mock_subnets"

    id = Column(String, primary_key=True)  # subnet-abc123
    vpc_id = Column(String, ForeignKey("mock_vpcs.id"), nullable=False)
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)

    # AWS Subnet fields
    cidr_block = Column(String, nullable=False)  # 10.0.1.0/24
    availability_zone = Column(String, nullable=False)  # us-east-1a
    map_public_ip_on_launch = Column(Boolean, default=False)
    state = Column(Enum(VPCState), default=VPCState.PENDING)

    # Available IP tracking
    available_ip_address_count = Column(Integer, default=251)  # /24 = 256 - 5 reserved

    # Tags
    tags = Column(JSON, default={})

    # OCI backing - REAL Subnet!
    oci_subnet_id = Column(String, nullable=True)  # ocid1.subnet.oc1...
    oci_route_table_id = Column(String, nullable=True)
    oci_security_list_id = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    vpc = relationship("MockVPC", back_populates="subnets")
    environment = relationship("Environment", foreign_keys=[environment_id])


class MockSecurityGroup(Base):
    """
    Mock AWS Security Group backed by OCI Network Security Group
    """
    __tablename__ = "mock_security_groups"

    id = Column(String, primary_key=True)  # sg-abc123
    vpc_id = Column(String, ForeignKey("mock_vpcs.id"), nullable=False)
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)

    # AWS Security Group fields
    group_name = Column(String, nullable=False)
    description = Column(String, nullable=False)

    # Tags
    tags = Column(JSON, default={})

    # OCI backing - Network Security Group
    oci_nsg_id = Column(String, nullable=True)  # ocid1.networksecuritygroup.oc1...

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    vpc = relationship("MockVPC", back_populates="security_groups")
    environment = relationship("Environment", foreign_keys=[environment_id])
    rules = relationship("MockSecurityGroupRule", back_populates="security_group", cascade="all, delete-orphan")


class MockSecurityGroupRule(Base):
    """
    Mock AWS Security Group Rule
    """
    __tablename__ = "mock_security_group_rules"

    id = Column(Integer, primary_key=True)
    security_group_id = Column(String, ForeignKey("mock_security_groups.id"), nullable=False)

    # Rule type
    rule_type = Column(String, nullable=False)  # ingress or egress

    # Protocol and ports
    ip_protocol = Column(String, nullable=False)  # tcp, udp, icmp, -1 (all)
    from_port = Column(Integer, nullable=True)
    to_port = Column(Integer, nullable=True)

    # Source/Destination
    cidr_ipv4 = Column(String, nullable=True)  # 0.0.0.0/0
    source_security_group_id = Column(String, nullable=True)  # sg-xyz789

    # Description
    description = Column(String, nullable=True)

    # Relationships
    security_group = relationship("MockSecurityGroup", back_populates="rules")


class MockInternetGateway(Base):
    """
    Mock AWS Internet Gateway
    """
    __tablename__ = "mock_internet_gateways"

    id = Column(String, primary_key=True)  # igw-abc123
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)

    # Attached VPC
    vpc_id = Column(String, ForeignKey("mock_vpcs.id"), nullable=True)
    state = Column(String, default="available")  # available, attached, detaching, detached

    # Tags
    tags = Column(JSON, default={})

    # OCI backing
    oci_internet_gateway_id = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    environment = relationship("Environment", foreign_keys=[environment_id])


class MockRouteTable(Base):
    """
    Mock AWS Route Table
    """
    __tablename__ = "mock_route_tables"

    id = Column(String, primary_key=True)  # rtb-abc123
    vpc_id = Column(String, ForeignKey("mock_vpcs.id"), nullable=False)
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)

    # Is this the main route table?
    is_main = Column(Boolean, default=False)

    # Routes stored as JSON array
    routes = Column(JSON, default=[])
    # Example: [{"destination": "0.0.0.0/0", "gateway_id": "igw-abc123"}]

    # Tags
    tags = Column(JSON, default={})

    # OCI backing
    oci_route_table_id = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    environment = relationship("Environment", foreign_keys=[environment_id])


class MockNATGateway(Base):
    """
    Mock AWS NAT Gateway
    """
    __tablename__ = "mock_nat_gateways"

    id = Column(String, primary_key=True)  # nat-abc123
    subnet_id = Column(String, ForeignKey("mock_subnets.id"), nullable=False)
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)

    # NAT Gateway fields
    state = Column(String, default="pending")  # pending, available, deleting, deleted
    public_ip = Column(String, nullable=True)
    private_ip = Column(String, nullable=True)

    # Tags
    tags = Column(JSON, default={})

    # OCI backing
    oci_nat_gateway_id = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    environment = relationship("Environment", foreign_keys=[environment_id])


# ============================================================================
# Lambda Resources
# ============================================================================

class MockLambdaFunction(Base):
    """
    Mock AWS Lambda Function - runs REAL Docker containers
    """
    __tablename__ = "mock_lambda_functions_v2"

    id = Column(String, primary_key=True)
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)

    # Lambda function details
    function_name = Column(String, nullable=False, unique=True, index=True)
    function_arn = Column(String, nullable=False)
    runtime = Column(String, nullable=False)  # python3.11, nodejs18.x, etc.
    handler = Column(String, nullable=False)  # index.handler
    role = Column(String, nullable=False)  # IAM role ARN

    # Code
    code_size = Column(Integer, default=0)
    code_sha256 = Column(String, nullable=True)
    code_s3_bucket = Column(String, nullable=True)
    code_s3_key = Column(String, nullable=True)
    code_zip_base64 = Column(Text, nullable=True)  # Small functions stored directly

    # Configuration
    memory_size = Column(Integer, default=128)  # MB
    timeout = Column(Integer, default=3)  # seconds
    environment_variables = Column(JSON, default={})

    # VPC configuration (if function runs in VPC)
    vpc_id = Column(String, ForeignKey("mock_vpcs.id"), nullable=True)
    subnet_ids = Column(JSON, default=[])
    security_group_ids = Column(JSON, default=[])

    # State
    state = Column(String, default="Active")  # Active, Pending, Inactive, Failed
    last_update_status = Column(String, default="Successful")

    # Docker backing - REAL container execution!
    docker_image = Column(String, nullable=True)  # Custom Docker image for this runtime
    docker_container_id = Column(String, nullable=True)  # Running container ID

    # Tags and description
    description = Column(String, nullable=True)
    tags = Column(JSON, default={})

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    last_modified = Column(DateTime, default=datetime.utcnow)

    # Relationships
    environment = relationship("Environment", foreign_keys=[environment_id])
    invocations = relationship("MockLambdaInvocation", back_populates="function", cascade="all, delete-orphan")


class MockLambdaInvocation(Base):
    """
    Track Lambda function invocations
    """
    __tablename__ = "mock_lambda_invocations"

    id = Column(String, primary_key=True)  # UUID
    function_id = Column(String, ForeignKey("mock_lambda_functions_v2.id"), nullable=False)

    # Invocation details
    request_id = Column(String, nullable=False)  # AWS request ID
    invocation_type = Column(String, nullable=False)  # RequestResponse, Event, DryRun
    payload = Column(Text, nullable=True)  # Input JSON
    response = Column(Text, nullable=True)  # Output JSON
    status_code = Column(Integer, nullable=True)  # 200, 500, etc.

    # Execution metrics
    duration_ms = Column(Integer, nullable=True)
    billed_duration_ms = Column(Integer, nullable=True)
    memory_used_mb = Column(Integer, nullable=True)

    # Errors
    function_error = Column(String, nullable=True)  # Unhandled, Handled
    error_message = Column(Text, nullable=True)

    # Timestamp
    invoked_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    function = relationship("MockLambdaFunction", back_populates="invocations")


# ============================================================================
# DynamoDB Resources
# ============================================================================

class MockDynamoDBTable(Base):
    """
    Mock AWS DynamoDB Table backed by PostgreSQL JSONB
    """
    __tablename__ = "mock_dynamodb_tables"

    id = Column(String, primary_key=True)
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)

    # Table details
    table_name = Column(String, nullable=False, unique=True, index=True)
    table_arn = Column(String, nullable=False)
    table_status = Column(String, default="CREATING")  # CREATING, ACTIVE, DELETING, DELETED

    # Key schema
    partition_key_name = Column(String, nullable=False)
    partition_key_type = Column(String, nullable=False)  # S, N, B
    sort_key_name = Column(String, nullable=True)
    sort_key_type = Column(String, nullable=True)

    # Billing mode
    billing_mode = Column(String, default="PAY_PER_REQUEST")  # PAY_PER_REQUEST or PROVISIONED
    read_capacity_units = Column(Integer, nullable=True)
    write_capacity_units = Column(Integer, nullable=True)

    # Item count and size
    item_count = Column(Integer, default=0)
    table_size_bytes = Column(Integer, default=0)

    # Tags
    tags = Column(JSON, default={})

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    environment = relationship("Environment", foreign_keys=[environment_id])
    items = relationship("MockDynamoDBItem", back_populates="table", cascade="all, delete-orphan")


class MockDynamoDBItem(Base):
    """
    DynamoDB items stored as JSONB in PostgreSQL
    """
    __tablename__ = "mock_dynamodb_items"

    id = Column(Integer, primary_key=True)
    table_id = Column(String, ForeignKey("mock_dynamodb_tables.id"), nullable=False)

    # Primary key values (for quick lookup)
    partition_key_value = Column(String, nullable=False, index=True)
    sort_key_value = Column(String, nullable=True, index=True)

    # The actual DynamoDB item as JSONB
    item_data = Column(JSON, nullable=False)
    # Example: {"user_id": {"S": "123"}, "name": {"S": "John"}, "age": {"N": "30"}}

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    table = relationship("MockDynamoDBTable", back_populates="items")


# ============================================================================
# SQS Resources
# ============================================================================

class MockSQSQueue(Base):
    """
    Mock AWS SQS Queue backed by Redis lists
    """
    __tablename__ = "mock_sqs_queues"

    id = Column(String, primary_key=True)
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)

    # Queue details
    queue_name = Column(String, nullable=False, unique=True, index=True)
    queue_url = Column(String, nullable=False)
    queue_arn = Column(String, nullable=False)

    # Queue type
    fifo_queue = Column(Boolean, default=False)

    # Configuration
    visibility_timeout = Column(Integer, default=30)  # seconds
    message_retention_period = Column(Integer, default=345600)  # 4 days
    delay_seconds = Column(Integer, default=0)
    max_message_size = Column(Integer, default=262144)  # 256 KB
    receive_message_wait_time = Column(Integer, default=0)  # Long polling

    # Dead letter queue
    dead_letter_target_arn = Column(String, nullable=True)
    max_receive_count = Column(Integer, nullable=True)

    # Redis backing - REAL message queue!
    redis_list_key = Column(String, nullable=True)  # Key in Redis

    # Stats
    approximate_number_of_messages = Column(Integer, default=0)
    approximate_number_of_messages_not_visible = Column(Integer, default=0)

    # Tags
    tags = Column(JSON, default={})

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    environment = relationship("Environment", foreign_keys=[environment_id])
