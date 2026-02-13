import httpx
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from app.core.config import settings
from app.models.user import User, UserTier
from sqlalchemy.orm import Session


class AuthentikOAuth:
    """Authentik OAuth2/OIDC Integration"""

    def __init__(self):
        self.client_id = settings.OAUTH_CLIENT_ID
        self.client_secret = settings.OAUTH_CLIENT_SECRET
        self.authorize_url = settings.OAUTH_AUTHORIZE_URL
        self.token_url = settings.OAUTH_TOKEN_URL
        self.userinfo_url = settings.OAUTH_USERINFO_URL
        self.logout_url = settings.OAUTH_LOGOUT_URL
        self.provider_name = settings.OAUTH_PROVIDER_NAME

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """Generate OAuth2 authorization URL"""
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state
        }

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.authorize_url}?{query_string}"

    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange authorization code for access token"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret
                }
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Failed to exchange code for token"
                )

            return response.json()

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user information from After Dark Systems"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Failed to get user info"
                )

            return response.json()

    async def get_or_create_user(self, db: Session, user_info: Dict[str, Any]) -> User:
        """Get or create user from Authentik OAuth/OIDC info"""
        # Authentik provides standard OIDC claims
        email = user_info.get("email")
        oauth_user_id = user_info.get("sub")  # Standard OIDC claim

        # Authentik also provides these optional claims
        preferred_username = user_info.get("preferred_username")
        name = user_info.get("name")
        groups = user_info.get("groups", [])  # Authentik provides user groups

        if not email or not oauth_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user info from OAuth provider"
            )

        # Check if user exists by oauth_user_id
        user = db.query(User).filter(User.oauth_user_id == oauth_user_id).first()

        if user:
            # Update user info if changed
            user.email = email
            if groups:
                # Check if user is in employee group
                user.is_employee = "employees" in groups or "afterdark-employees" in groups
                user.tier = UserTier.EMPLOYEE if user.is_employee else user.tier
            db.commit()
            db.refresh(user)
            return user

        # Create new user
        # Check if user is in employee group from Authentik
        is_employee = (
            "employees" in groups or
            "afterdark-employees" in groups or
            email.endswith(settings.AFTERDARK_EMPLOYEE_DOMAIN)
        )

        # Check if student
        is_student = "students" in groups

        # Determine tier
        if is_employee:
            tier = UserTier.EMPLOYEE
        elif is_student:
            tier = UserTier.STUDENT
        else:
            tier = UserTier.BEGINNER

        user = User(
            email=email,
            oauth_user_id=oauth_user_id,
            is_employee=is_employee,
            tier=tier,
            is_active=True
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        return user


oauth_client = AuthentikOAuth()
