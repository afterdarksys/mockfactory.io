from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, JSON, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.core.database import Base


class EnvironmentStatus(str, enum.Enum):
    """Environment lifecycle states"""
    PROVISIONING = "provisioning"
    RUNNING = "running"
    STOPPED = "stopped"
    DESTROYING = "destroying"
    DESTROYED = "destroyed"
    ERROR = "error"


class ServiceType(str, enum.Enum):
    """Available services in an environment"""
    REDIS = "redis"
    POSTGRESQL = "postgresql"
    POSTGRESQL_SUPABASE = "postgresql_supabase"  # PG + PostgREST + Auth
    POSTGRESQL_PGVECTOR = "postgresql_pgvector"  # PG with pgvector extension
    POSTGRESQL_POSTGIS = "postgresql_postgis"    # PG with PostGIS extension
    AWS_S3 = "aws_s3"
    AWS_SQS = "aws_sqs"
    AWS_SNS = "aws_sns"
    GCP_STORAGE = "gcp_storage"
    AZURE_BLOB = "azure_blob"


class Environment(Base):
    """
    Mock environment containing multiple services (Redis, MySQL, S3, etc.)
    Each environment is isolated and billed hourly
    """
    __tablename__ = "environments"

    id = Column(String, primary_key=True, index=True)  # env-abc123
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=True)  # Optional friendly name
    hostname = Column(String, nullable=True, unique=True, index=True)  # Custom hostname (e.g., "myapp.dev")
    status = Column(Enum(EnvironmentStatus), default=EnvironmentStatus.PROVISIONING)

    # Services configuration
    services = Column(JSON, nullable=False)  # {"redis": {...}, "mysql": {...}}

    # Connection details
    endpoints = Column(JSON, nullable=True)  # {"redis": "redis://...", "mysql": "mysql://..."}

    # Billing
    hourly_rate = Column(Float, nullable=False)  # Total cost per hour
    total_cost = Column(Float, default=0.0)  # Running total

    # Lifecycle
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    stopped_at = Column(DateTime, nullable=True)
    last_activity = Column(DateTime, default=datetime.utcnow)
    auto_shutdown_hours = Column(Integer, default=4)  # Auto-kill after N hours inactive

    # OCI resource tracking
    oci_resources = Column(JSON, nullable=True)  # {"bucket": "...", "compartment": "..."}
    docker_containers = Column(JSON, nullable=True)  # {"redis": "container_id", ...}

    # Relationships
    user = relationship("User", back_populates="environments")
    usage_logs = relationship("EnvironmentUsageLog", back_populates="environment", cascade="all, delete-orphan")
    api_keys = relationship("APIKey", back_populates="environment")
    dns_records = relationship("DNSRecord", back_populates="environment", cascade="all, delete-orphan")


class EnvironmentUsageLog(Base):
    """
    Hourly usage tracking for billing
    One record per hour the environment is running
    """
    __tablename__ = "environment_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Time tracking
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=True)  # Null if still running

    # Billing
    hourly_rate = Column(Float, nullable=False)
    cost = Column(Float, default=0.0)  # Calculated when period ends

    # Status
    billed = Column(Integer, default=0)  # 0 = not billed, 1 = billed to Stripe
    stripe_charge_id = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    environment = relationship("Environment", back_populates="usage_logs")
    user = relationship("User")
