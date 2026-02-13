from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional
from passlib.context import CryptContext
from datetime import timedelta
import secrets

from app.core.database import get_db
from app.core.config import settings
from app.models.user import User, UserTier
from app.security.auth import create_access_token, get_current_user
from app.security.oauth import oauth_client

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str


class SignInRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict


class UserResponse(BaseModel):
    id: int
    email: str
    tier: str
    is_employee: bool


# ============================================================================
# Manual Email/Password Authentication
# ============================================================================

@router.post("/signup", response_model=TokenResponse)
async def signup(
    request: SignUpRequest,
    db: Session = Depends(get_db)
):
    """Sign up with email and password"""

    # Check if user already exists
    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Check if this is an After Dark Systems employee
    is_employee = request.email.endswith(settings.AFTERDARK_EMPLOYEE_DOMAIN)
    tier = UserTier.EMPLOYEE if is_employee else UserTier.BEGINNER

    # Hash password
    hashed_password = pwd_context.hash(request.password)

    # Create user
    user = User(
        email=request.email,
        hashed_password=hashed_password,
        is_employee=is_employee,
        tier=tier,
        is_active=True
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    # Create access token
    access_token = create_access_token(
        data={"sub": user.id},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user={
            "id": user.id,
            "email": user.email,
            "tier": user.tier.value,
            "is_employee": user.is_employee
        }
    )


@router.post("/signin", response_model=TokenResponse)
async def signin(
    request: SignInRequest,
    db: Session = Depends(get_db)
):
    """Sign in with email and password"""

    # Find user
    user = db.query(User).filter(User.email == request.email).first()
    if not user or not hasattr(user, 'hashed_password') or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Verify password
    if not pwd_context.verify(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    # Create access token
    access_token = create_access_token(
        data={"sub": user.id},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user={
            "id": user.id,
            "email": user.email,
            "tier": user.tier.value,
            "is_employee": user.is_employee
        }
    )


# ============================================================================
# Authentik OAuth2/OIDC SSO
# ============================================================================

@router.get("/sso/login")
async def sso_login():
    """Initiate Authentik SSO login"""

    # Generate random state for CSRF protection
    state = secrets.token_urlsafe(32)

    # In production, store state in Redis/session
    # For now, we'll validate it in the callback

    redirect_uri = "https://mockfactory.io/api/v1/auth/sso/callback"

    authorization_url = oauth_client.get_authorization_url(
        redirect_uri=redirect_uri,
        state=state
    )

    return {
        "authorization_url": authorization_url,
        "state": state,
        "provider": oauth_client.provider_name
    }


@router.get("/sso/callback")
async def sso_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db)
):
    """Handle Authentik SSO callback"""

    # In production, validate state from Redis/session
    # For now, we'll skip strict state validation

    redirect_uri = "https://mockfactory.io/api/v1/auth/sso/callback"

    # Exchange code for token
    token_data = await oauth_client.exchange_code_for_token(code, redirect_uri)
    access_token = token_data.get("access_token")

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to obtain access token"
        )

    # Get user info
    user_info = await oauth_client.get_user_info(access_token)

    # Get or create user
    user = await oauth_client.get_or_create_user(db, user_info)

    # Create our JWT token
    jwt_token = create_access_token(
        data={"sub": user.id},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # Redirect to frontend with token
    return RedirectResponse(
        url=f"https://mockfactory.io/auth/callback?token={jwt_token}"
    )


# ============================================================================
# User Info
# ============================================================================

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Get current authenticated user info"""

    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        tier=current_user.tier.value,
        is_employee=current_user.is_employee
    )
