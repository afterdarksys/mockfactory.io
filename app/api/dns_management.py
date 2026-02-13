"""
DNS Management API - Manage DNS records for fake authoritative DNS
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, validator
from typing import List, Optional
import re

from app.core.database import get_db
from app.models.user import User
from app.models.environment import Environment, EnvironmentStatus
from app.models.dns_record import DNSRecord, DNSRecordType
from app.security.auth import get_current_user

router = APIRouter()


class DNSRecordCreate(BaseModel):
    """Create DNS record request"""
    name: str = Field(..., description="Fully qualified domain name (e.g., api.myapp.dev)")
    record_type: DNSRecordType = Field(..., description="DNS record type")
    value: str = Field(..., description="Record value (IP, hostname, text, etc.)")
    ttl: int = Field(300, ge=60, le=86400, description="Time to live in seconds (60-86400)")
    priority: Optional[int] = Field(None, ge=0, le=65535, description="Priority for MX/SRV records")
    weight: Optional[int] = Field(None, ge=0, le=65535, description="Weight for SRV records")
    port: Optional[int] = Field(None, ge=1, le=65535, description="Port for SRV records")

    @validator('name')
    def validate_hostname(cls, v):
        """Validate hostname format"""
        # Allow alphanumeric, hyphens, dots, and underscores
        if not re.match(r'^[a-zA-Z0-9._-]+$', v):
            raise ValueError('Invalid hostname format')

        # Must not start or end with dot or hyphen
        if v.startswith('.') or v.startswith('-') or v.endswith('.') or v.endswith('-'):
            raise ValueError('Hostname cannot start or end with dot or hyphen')

        # Maximum 253 characters
        if len(v) > 253:
            raise ValueError('Hostname too long (max 253 characters)')

        return v.lower()

    @validator('value')
    def validate_value(cls, v, values):
        """Validate record value based on type"""
        record_type = values.get('record_type')

        if record_type == DNSRecordType.A:
            # Validate IPv4
            parts = v.split('.')
            if len(parts) != 4:
                raise ValueError('Invalid IPv4 address')
            try:
                for part in parts:
                    num = int(part)
                    if num < 0 or num > 255:
                        raise ValueError('Invalid IPv4 address')
            except ValueError:
                raise ValueError('Invalid IPv4 address')

        elif record_type == DNSRecordType.AAAA:
            # Validate IPv6 (simplified)
            if ':' not in v:
                raise ValueError('Invalid IPv6 address')

        elif record_type in [DNSRecordType.CNAME, DNSRecordType.NS, DNSRecordType.MX]:
            # Validate hostname
            if not re.match(r'^[a-zA-Z0-9._-]+$', v):
                raise ValueError('Invalid hostname format')

        return v


class DNSRecordUpdate(BaseModel):
    """Update DNS record request"""
    value: Optional[str] = None
    ttl: Optional[int] = Field(None, ge=60, le=86400)
    priority: Optional[int] = Field(None, ge=0, le=65535)
    weight: Optional[int] = Field(None, ge=0, le=65535)
    port: Optional[int] = Field(None, ge=1, le=65535)


class DNSRecordResponse(BaseModel):
    """DNS record response"""
    id: int
    name: str
    record_type: DNSRecordType
    value: str
    ttl: int
    priority: Optional[int]
    weight: Optional[int]
    port: Optional[int]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class EnvironmentHostnameUpdate(BaseModel):
    """Update environment hostname"""
    hostname: str = Field(..., description="Custom hostname for environment (e.g., myapp.dev)")

    @validator('hostname')
    def validate_hostname(cls, v):
        """Validate hostname format"""
        if not re.match(r'^[a-zA-Z0-9.-]+$', v):
            raise ValueError('Invalid hostname format')

        if v.startswith('.') or v.startswith('-') or v.endswith('.') or v.endswith('-'):
            raise ValueError('Hostname cannot start or end with dot or hyphen')

        if len(v) > 253:
            raise ValueError('Hostname too long (max 253 characters)')

        return v.lower()


@router.patch("/{environment_id}/hostname")
async def update_environment_hostname(
    environment_id: str,
    request: EnvironmentHostnameUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Set custom hostname for environment

    This hostname will be used as the base domain for the environment.
    All services will be accessible under this domain.

    Example:
    - Set hostname to "myapp.dev"
    - PostgreSQL: postgresql://...@postgres.myapp.dev:5432/testdb
    - S3: https://s3.myapp.dev
    - Redis: redis://redis.myapp.dev:6379
    """
    environment = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.user_id == current_user.id
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found")

    # Check if hostname already in use
    existing = db.query(Environment).filter(
        Environment.hostname == request.hostname,
        Environment.id != environment_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Hostname '{request.hostname}' already in use by another environment"
        )

    environment.hostname = request.hostname
    db.commit()

    return {
        "environment_id": environment.id,
        "hostname": environment.hostname,
        "message": f"Hostname set to {request.hostname}. Use this as the base domain for DNS records."
    }


@router.post("/{environment_id}/dns", response_model=DNSRecordResponse, status_code=201)
async def create_dns_record(
    environment_id: str,
    request: DNSRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create DNS record for environment

    Allows creating fake DNS records that can be queried by applications
    during testing. Useful for testing DNS-dependent applications.

    Examples:
    - A record: {"name": "api.myapp.dev", "type": "A", "value": "192.168.1.100"}
    - CNAME: {"name": "www.myapp.dev", "type": "CNAME", "value": "myapp.dev"}
    - MX: {"name": "myapp.dev", "type": "MX", "value": "mail.myapp.dev", "priority": 10}
    - TXT: {"name": "_dmarc.myapp.dev", "type": "TXT", "value": "v=DMARC1; p=reject"}
    """
    environment = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.user_id == current_user.id
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found")

    # Check for duplicate record
    existing = db.query(DNSRecord).filter(
        DNSRecord.environment_id == environment_id,
        DNSRecord.name == request.name,
        DNSRecord.record_type == request.record_type
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"DNS record already exists: {request.name} {request.record_type.value}"
        )

    # Create DNS record
    dns_record = DNSRecord(
        environment_id=environment_id,
        name=request.name,
        record_type=request.record_type,
        value=request.value,
        ttl=request.ttl,
        priority=request.priority,
        weight=request.weight,
        port=request.port
    )

    db.add(dns_record)
    db.commit()
    db.refresh(dns_record)

    return DNSRecordResponse(
        id=dns_record.id,
        name=dns_record.name,
        record_type=dns_record.record_type,
        value=dns_record.value,
        ttl=dns_record.ttl,
        priority=dns_record.priority,
        weight=dns_record.weight,
        port=dns_record.port,
        created_at=dns_record.created_at.isoformat(),
        updated_at=dns_record.updated_at.isoformat()
    )


@router.get("/{environment_id}/dns", response_model=List[DNSRecordResponse])
async def list_dns_records(
    environment_id: str,
    record_type: Optional[DNSRecordType] = None,
    name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all DNS records for environment

    Optional filters:
    - record_type: Filter by DNS record type (A, AAAA, CNAME, etc.)
    - name: Filter by hostname (exact match)
    """
    environment = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.user_id == current_user.id
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found")

    query = db.query(DNSRecord).filter(DNSRecord.environment_id == environment_id)

    if record_type:
        query = query.filter(DNSRecord.record_type == record_type)

    if name:
        query = query.filter(DNSRecord.name == name.lower())

    records = query.order_by(DNSRecord.name).all()

    return [
        DNSRecordResponse(
            id=r.id,
            name=r.name,
            record_type=r.record_type,
            value=r.value,
            ttl=r.ttl,
            priority=r.priority,
            weight=r.weight,
            port=r.port,
            created_at=r.created_at.isoformat(),
            updated_at=r.updated_at.isoformat()
        )
        for r in records
    ]


@router.get("/{environment_id}/dns/{record_id}", response_model=DNSRecordResponse)
async def get_dns_record(
    environment_id: str,
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific DNS record by ID"""
    environment = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.user_id == current_user.id
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found")

    record = db.query(DNSRecord).filter(
        DNSRecord.id == record_id,
        DNSRecord.environment_id == environment_id
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="DNS record not found")

    return DNSRecordResponse(
        id=record.id,
        name=record.name,
        record_type=record.record_type,
        value=record.value,
        ttl=record.ttl,
        priority=record.priority,
        weight=record.weight,
        port=record.port,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat()
    )


@router.patch("/{environment_id}/dns/{record_id}", response_model=DNSRecordResponse)
async def update_dns_record(
    environment_id: str,
    record_id: int,
    request: DNSRecordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update DNS record

    Can update value, TTL, priority, weight, port
    Cannot update name or record_type (delete and recreate instead)
    """
    environment = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.user_id == current_user.id
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found")

    record = db.query(DNSRecord).filter(
        DNSRecord.id == record_id,
        DNSRecord.environment_id == environment_id
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="DNS record not found")

    # Update fields if provided
    if request.value is not None:
        record.value = request.value
    if request.ttl is not None:
        record.ttl = request.ttl
    if request.priority is not None:
        record.priority = request.priority
    if request.weight is not None:
        record.weight = request.weight
    if request.port is not None:
        record.port = request.port

    db.commit()
    db.refresh(record)

    return DNSRecordResponse(
        id=record.id,
        name=record.name,
        record_type=record.record_type,
        value=record.value,
        ttl=record.ttl,
        priority=record.priority,
        weight=record.weight,
        port=record.port,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat()
    )


@router.delete("/{environment_id}/dns/{record_id}", status_code=204)
async def delete_dns_record(
    environment_id: str,
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete DNS record"""
    environment = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.user_id == current_user.id
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found")

    record = db.query(DNSRecord).filter(
        DNSRecord.id == record_id,
        DNSRecord.environment_id == environment_id
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="DNS record not found")

    db.delete(record)
    db.commit()

    return None


@router.post("/{environment_id}/dns/bulk", status_code=201)
async def bulk_create_dns_records(
    environment_id: str,
    requests: List[DNSRecordCreate],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Bulk create DNS records

    Useful for importing a zone file or setting up multiple records at once.
    Maximum 100 records per request.
    """
    if len(requests) > 100:
        raise HTTPException(
            status_code=400,
            detail="Maximum 100 records per bulk request"
        )

    environment = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.user_id == current_user.id
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found")

    created_records = []
    errors = []

    for idx, request in enumerate(requests):
        try:
            # Check for duplicate
            existing = db.query(DNSRecord).filter(
                DNSRecord.environment_id == environment_id,
                DNSRecord.name == request.name,
                DNSRecord.record_type == request.record_type
            ).first()

            if existing:
                errors.append({
                    "index": idx,
                    "name": request.name,
                    "type": request.record_type.value,
                    "error": "Record already exists"
                })
                continue

            # Create record
            dns_record = DNSRecord(
                environment_id=environment_id,
                name=request.name,
                record_type=request.record_type,
                value=request.value,
                ttl=request.ttl,
                priority=request.priority,
                weight=request.weight,
                port=request.port
            )

            db.add(dns_record)
            created_records.append(dns_record)

        except Exception as e:
            errors.append({
                "index": idx,
                "name": request.name,
                "type": request.record_type.value,
                "error": str(e)
            })

    db.commit()

    return {
        "created": len(created_records),
        "errors": len(errors),
        "error_details": errors if errors else None
    }
