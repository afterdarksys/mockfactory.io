"""
API Key Management Endpoints

Allows users to create, list, and manage API keys for programmatic access.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
import secrets
import hashlib

from app.core.database import get_db
from app.models.user import User
from app.models.api_key import APIKey
from app.security.auth import get_current_user

router = APIRouter()


class CreateAPIKeyRequest(BaseModel):
    name: str
    expires_in_days: Optional[int] = None  # None = no expiration


class APIKeyResponse(BaseModel):
    id: int
    name: str
    prefix: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime]
    expires_at: Optional[datetime]

    class Config:
        from_attributes = True


class CreateAPIKeyResponse(BaseModel):
    """Response when creating a new API key - includes the full key"""
    id: int
    name: str
    api_key: str  # Full key - only shown once!
    prefix: str
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime]


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate an API key with format: mf_<random_40_chars>

    Returns:
        (full_key, key_hash, prefix)
    """
    # Generate random key
    random_part = secrets.token_urlsafe(32)[:40]  # 40 chars
    full_key = f"mf_{random_part}"

    # Create hash for storage
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()

    # Prefix for identification (first 12 chars)
    prefix = full_key[:12]

    return (full_key, key_hash, prefix)


@router.post("/", response_model=CreateAPIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    request: CreateAPIKeyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new API key for the current user.

    The full API key is only returned once - it cannot be retrieved later!
    """
    # Generate API key
    full_key, key_hash, prefix = generate_api_key()

    # Calculate expiration
    expires_at = None
    if request.expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=request.expires_in_days)

    # Create API key record
    api_key = APIKey(
        user_id=current_user.id,
        name=request.name,
        key_hash=key_hash,
        prefix=prefix,
        is_active=True,
        expires_at=expires_at
    )

    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return CreateAPIKeyResponse(
        id=api_key.id,
        name=api_key.name,
        api_key=full_key,  # Only time the full key is shown!
        prefix=api_key.prefix,
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        expires_at=api_key.expires_at
    )


@router.get("/", response_model=List[APIKeyResponse])
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all API keys for the current user"""

    api_keys = db.query(APIKey).filter(
        APIKey.user_id == current_user.id
    ).order_by(APIKey.created_at.desc()).all()

    return api_keys


@router.get("/{key_id}", response_model=APIKeyResponse)
async def get_api_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get details of a specific API key"""

    api_key = db.query(APIKey).filter(
        APIKey.id == key_id,
        APIKey.user_id == current_user.id
    ).first()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    return api_key


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete (revoke) an API key"""

    api_key = db.query(APIKey).filter(
        APIKey.id == key_id,
        APIKey.user_id == current_user.id
    ).first()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    db.delete(api_key)
    db.commit()

    return None


@router.patch("/{key_id}/deactivate", response_model=APIKeyResponse)
async def deactivate_api_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Deactivate an API key (can be reactivated later)"""

    api_key = db.query(APIKey).filter(
        APIKey.id == key_id,
        APIKey.user_id == current_user.id
    ).first()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    api_key.is_active = False
    db.commit()
    db.refresh(api_key)

    return api_key


@router.patch("/{key_id}/activate", response_model=APIKeyResponse)
async def activate_api_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reactivate a deactivated API key"""

    api_key = db.query(APIKey).filter(
        APIKey.id == key_id,
        APIKey.user_id == current_user.id
    ).first()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    api_key.is_active = True
    db.commit()
    db.refresh(api_key)

    return api_key
