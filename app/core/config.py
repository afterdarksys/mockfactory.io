from pydantic_settings import BaseSettings
from typing import List
import secrets


class Settings(BaseSettings):
    PROJECT_NAME: str = "MockFactory"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str
    REDIS_URL: str

    # Security
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # OAuth2/OIDC (Authentik)
    OAUTH_CLIENT_ID: str
    OAUTH_CLIENT_SECRET: str
    OAUTH_AUTHORIZE_URL: str
    OAUTH_TOKEN_URL: str
    OAUTH_USERINFO_URL: str
    OAUTH_LOGOUT_URL: str = ""
    OAUTH_PROVIDER_NAME: str = "Authentik"

    # Stripe
    STRIPE_SECRET_KEY: str
    STRIPE_PUBLISHABLE_KEY: str
    STRIPE_WEBHOOK_SECRET: str

    # Docker Security
    DOCKER_SOCKET: str = "/var/run/docker.sock"
    MAX_EXECUTION_TIME: int = 30
    MAX_MEMORY_MB: int = 256
    MAX_CPU_QUOTA: int = 50000

    # Usage Limits (executions per month)
    RUNS_ANONYMOUS: int = 5
    RUNS_BEGINNER: int = 10
    RUNS_STUDENT: int = 25
    RUNS_PROFESSIONAL: int = 100
    RUNS_GOVERNMENT: int = 500
    RUNS_ENTERPRISE: int = -1  # Unlimited
    RUNS_CUSTOM: int = -1  # Unlimited
    RUNS_EMPLOYEE: int = -1  # Unlimited

    AFTERDARK_EMPLOYEE_DOMAIN: str = "@afterdarksystems.com"

    # Stripe Product IDs (set these after running stripe_setup.py)
    STRIPE_PRODUCT_PROFESSIONAL: str = ""
    STRIPE_PRICE_PROFESSIONAL: str = ""
    STRIPE_PRODUCT_GOVERNMENT: str = ""
    STRIPE_PRICE_GOVERNMENT: str = ""
    STRIPE_PRODUCT_ENTERPRISE: str = ""
    STRIPE_PRICE_ENTERPRISE: str = ""

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "https://mockfactory.io"]

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields in .env file


settings = Settings()
