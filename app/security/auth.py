from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/token", auto_error=False)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    return encoded_jwt


def decode_token(token: str) -> dict:
    """Decode and verify JWT token"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Get current user from JWT token (returns None if not authenticated)"""
    if not token:
        return None

    payload = decode_token(token)
    user_id: int = int(payload.get("sub"))

    if user_id is None:
        return None

    user = db.query(User).filter(User.id == user_id).first()
    return user


async def require_user(
    current_user: Optional[User] = Depends(get_current_user)
) -> User:
    """Require authenticated user"""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    return current_user


async def verify_api_key(api_key: str, db: Session) -> Optional[User]:
    """
    Verify API key and return associated user

    API keys are stored in the api_keys table with the following format:
    - key: hashed API key
    - user_id: owner of the key
    - environment_id: optional environment restriction
    """
    from app.models.api_key import APIKey
    import hashlib

    # Hash the provided API key
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    # Look up API key in database
    api_key_record = db.query(APIKey).filter(
        APIKey.key_hash == key_hash,
        APIKey.is_active == True
    ).first()

    if not api_key_record:
        return None

    # Update last used timestamp
    api_key_record.last_used_at = datetime.utcnow()
    db.commit()

    # Return associated user
    return api_key_record.user


async def get_user_from_request(
    authorization: Optional[str] = None,
    x_api_key: Optional[str] = None,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Flexible authentication supporting multiple methods:
    1. API Key via X-API-Key header
    2. API Key via Authorization: ApiKey <key>
    3. JWT Bearer token via Authorization: Bearer <token>

    Returns None if no valid authentication found
    """
    # Method 1: X-API-Key header
    if x_api_key:
        user = await verify_api_key(x_api_key, db)
        if user:
            return user

    # Method 2: Authorization header with ApiKey scheme
    if authorization and authorization.startswith("ApiKey "):
        api_key = authorization[7:]  # Remove "ApiKey " prefix
        user = await verify_api_key(api_key, db)
        if user:
            return user

    # Method 3: JWT token (existing oauth2_scheme)
    if token:
        payload = decode_token(token)
        user_id: int = int(payload.get("sub"))
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                return user

    return None


async def require_authenticated_request(
    authorization: Optional[str] = None,
    x_api_key: Optional[str] = None,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Require authentication via any supported method
    Raises 401 if no valid authentication found
    """
    user = await get_user_from_request(authorization, x_api_key, token, db)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide credentials via X-API-Key header, Authorization: ApiKey <key>, or Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer, ApiKey"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    return user
