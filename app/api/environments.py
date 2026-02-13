from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel, Field, field_serializer
from datetime import datetime
import secrets
import re

from app.core.database import get_db
from app.models.user import User
from app.models.environment import Environment, EnvironmentStatus, ServiceType, EnvironmentUsageLog
from app.security.auth import get_current_user
from app.services.environment_provisioner import EnvironmentProvisioner

router = APIRouter()


def sanitize_connection_string(connection_string: str) -> str:
    """
    Sanitize connection string by masking passwords

    Examples:
        redis://:password123@localhost:6379 -> redis://:*****@localhost:6379
        postgresql://user:pass@host:5432/db -> postgresql://user:*****@host:5432/db
        http://localhost:9324 -> http://localhost:9324 (no password)
    """
    # Pattern to match password in connection strings
    # Matches: ://user:password@ or //:password@
    patterns = [
        (r'(:\/\/[^:]+:)[^@]+(@)', r'\1*****\2'),  # user:password@
        (r'(:\/\/:)[^@]+(@)', r'\1*****\2'),       # :password@
    ]

    sanitized = connection_string
    for pattern, replacement in patterns:
        sanitized = re.sub(pattern, replacement, sanitized)

    return sanitized


def sanitize_endpoints(endpoints: dict | None) -> dict | None:
    """Sanitize all connection strings in endpoints dictionary"""
    if not endpoints:
        return endpoints

    return {
        service: sanitize_connection_string(connection_string)
        for service, connection_string in endpoints.items()
    }


# Pydantic schemas
class ServiceConfig(BaseModel):
    """Configuration for a single service"""
    type: ServiceType
    version: str = "latest"
    config: dict = Field(default_factory=dict)


class EnvironmentCreate(BaseModel):
    """Request to create a new environment"""
    name: str | None = None
    services: List[ServiceConfig]
    auto_shutdown_hours: int = Field(default=4, ge=1, le=48)


class EnvironmentResponse(BaseModel):
    """Environment details response"""
    id: str
    name: str | None
    status: EnvironmentStatus
    services: dict
    endpoints: dict | None
    hourly_rate: float
    total_cost: float
    created_at: datetime
    started_at: datetime | None
    last_activity: datetime
    auto_shutdown_hours: int

    @field_serializer('endpoints')
    def serialize_endpoints(self, endpoints: dict | None, _info) -> dict | None:
        """
        Sanitize connection strings before returning in API response
        Masks passwords for security
        """
        return sanitize_endpoints(endpoints)

    class Config:
        from_attributes = True


class EnvironmentListResponse(BaseModel):
    """List of environments"""
    environments: List[EnvironmentResponse]
    total_running_cost: float


# Service pricing (per hour)
SERVICE_PRICING = {
    ServiceType.REDIS: 0.10,
    ServiceType.POSTGRESQL: 0.10,
    ServiceType.POSTGRESQL_SUPABASE: 0.15,  # PG + PostgREST
    ServiceType.POSTGRESQL_PGVECTOR: 0.12,  # PG with AI extensions
    ServiceType.POSTGRESQL_POSTGIS: 0.12,   # PG with GIS extensions
    ServiceType.AWS_S3: 0.05,
    ServiceType.AWS_SQS: 0.03,
    ServiceType.AWS_SNS: 0.03,
    ServiceType.GCP_STORAGE: 0.05,
    ServiceType.AZURE_BLOB: 0.05,
}


def calculate_hourly_rate(services: List[ServiceConfig]) -> float:
    """Calculate total hourly rate for requested services"""
    total = 0.0
    for service in services:
        total += SERVICE_PRICING.get(service.type, 0.0)
    return round(total, 2)


def generate_environment_id() -> str:
    """Generate unique environment ID"""
    return f"env-{secrets.token_urlsafe(8)}"


@router.post("/", response_model=EnvironmentResponse, status_code=status.HTTP_201_CREATED)
async def create_environment(
    request: EnvironmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new mock environment with requested services

    Services will be provisioned and started immediately
    Billing starts when environment enters RUNNING state
    """
    # Calculate pricing
    hourly_rate = calculate_hourly_rate(request.services)

    if hourly_rate == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid services requested"
        )

    # Create environment record
    env_id = generate_environment_id()
    services_dict = {svc.type.value: {"version": svc.version, "config": svc.config} for svc in request.services}

    environment = Environment(
        id=env_id,
        user_id=current_user.id,
        name=request.name or f"Environment {env_id}",
        status=EnvironmentStatus.PROVISIONING,
        services=services_dict,
        hourly_rate=hourly_rate,
        auto_shutdown_hours=request.auto_shutdown_hours
    )

    db.add(environment)
    db.commit()
    db.refresh(environment)

    # Start provisioning (async in background)
    try:
        provisioner = EnvironmentProvisioner(db)
        await provisioner.provision(environment)
        db.refresh(environment)
    except Exception as e:
        environment.status = EnvironmentStatus.ERROR
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to provision environment: {str(e)}"
        )

    return environment


@router.get("/", response_model=EnvironmentListResponse)
async def list_environments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status_filter: EnvironmentStatus | None = None
):
    """
    List all environments for the current user

    Optionally filter by status
    """
    query = db.query(Environment).filter(Environment.user_id == current_user.id)

    if status_filter:
        query = query.filter(Environment.status == status_filter)

    environments = query.order_by(Environment.created_at.desc()).all()

    # Calculate total running cost
    total_cost = sum(env.hourly_rate for env in environments if env.status == EnvironmentStatus.RUNNING)

    return {
        "environments": environments,
        "total_running_cost": total_cost
    }


@router.get("/{environment_id}", response_model=EnvironmentResponse)
async def get_environment(
    environment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get details of a specific environment"""
    environment = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.user_id == current_user.id
    ).first()

    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found"
        )

    return environment


@router.delete("/{environment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def destroy_environment(
    environment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Destroy an environment and all its resources

    - Stops all containers
    - Deletes OCI resources
    - Calculates final bill
    - Marks environment as DESTROYED
    """
    environment = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.user_id == current_user.id
    ).first()

    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found"
        )

    if environment.status == EnvironmentStatus.DESTROYED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Environment already destroyed"
        )

    # Mark as destroying
    environment.status = EnvironmentStatus.DESTROYING
    db.commit()

    try:
        # Tear down resources
        provisioner = EnvironmentProvisioner(db)
        await provisioner.destroy(environment)

        # Update status
        environment.status = EnvironmentStatus.DESTROYED
        environment.stopped_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        environment.status = EnvironmentStatus.ERROR
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to destroy environment: {str(e)}"
        )


@router.post("/{environment_id}/stop", response_model=EnvironmentResponse)
async def stop_environment(
    environment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Stop (pause) an environment

    Containers are stopped but not deleted
    Billing pauses while stopped
    """
    environment = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.user_id == current_user.id
    ).first()

    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found"
        )

    if environment.status != EnvironmentStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot stop environment in {environment.status} state"
        )

    try:
        provisioner = EnvironmentProvisioner(db)
        await provisioner.stop(environment)

        environment.status = EnvironmentStatus.STOPPED
        environment.stopped_at = datetime.utcnow()
        db.commit()
        db.refresh(environment)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop environment: {str(e)}"
        )

    return environment


@router.post("/{environment_id}/start", response_model=EnvironmentResponse)
async def start_environment(
    environment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Start (resume) a stopped environment

    Billing resumes when started
    """
    environment = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.user_id == current_user.id
    ).first()

    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found"
        )

    if environment.status != EnvironmentStatus.STOPPED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot start environment in {environment.status} state"
        )

    try:
        provisioner = EnvironmentProvisioner(db)
        await provisioner.start(environment)

        environment.status = EnvironmentStatus.RUNNING
        environment.started_at = datetime.utcnow()
        db.commit()
        db.refresh(environment)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start environment: {str(e)}"
        )

    return environment
