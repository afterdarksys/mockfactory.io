from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import asyncio
import logging
from app.core.config import settings
from app.api import execute, auth, payments, environments, cloud_emulation, container_registry_emulation, aws_services_emulation, data_generation, dns_management, aws_vpc_emulator, aws_lambda_emulator, aws_dynamodb_emulator, aws_sqs_emulator, api_keys
from app.core.database import engine, Base
from app.services.background_tasks import start_background_tasks
from app.core.rate_limit import limiter
from app.middleware.rate_limit_middleware import GlobalRateLimitMiddleware

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# NOTE: Database tables are managed by Alembic migrations
# Run: alembic upgrade head
# DO NOT use Base.metadata.create_all() - it doesn't support migrations


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect HTTP to HTTPS in production"""
    async def dispatch(self, request: Request, call_next):
        # Check if request is HTTP and should be redirected
        # Skip redirect for local development
        if (
            request.url.scheme == "http" and
            request.headers.get("host", "").startswith("mockfactory.io")
        ):
            # Redirect to HTTPS
            url = request.url.replace(scheme="https")
            return RedirectResponse(url, status_code=301)

        # Also check X-Forwarded-Proto header (for load balancers)
        forwarded_proto = request.headers.get("x-forwarded-proto")
        if (
            forwarded_proto == "http" and
            request.headers.get("host", "").startswith("mockfactory.io")
        ):
            url = request.url.replace(scheme="https")
            return RedirectResponse(url, status_code=301)

        return await call_next(request)


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="PostgreSQL-first testing platform with cloud emulation and auto-shutdown"
)

# Add rate limiter state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# HTTPS redirect middleware (must be first)
app.add_middleware(HTTPSRedirectMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global rate limiting middleware (tier-based limits)
app.add_middleware(GlobalRateLimitMiddleware)

# Include routers with rate limiting
app.include_router(
    execute.router,
    prefix=f"{settings.API_V1_PREFIX}/code",
    tags=["code-execution"]
)

app.include_router(
    auth.router,
    prefix=f"{settings.API_V1_PREFIX}/auth",
    tags=["authentication"]
)

app.include_router(
    api_keys.router,
    prefix=f"{settings.API_V1_PREFIX}/api-keys",
    tags=["api-keys"]
)

app.include_router(
    payments.router,
    prefix=f"{settings.API_V1_PREFIX}/payments",
    tags=["payments"]
)

app.include_router(
    environments.router,
    prefix=f"{settings.API_V1_PREFIX}/environments",
    tags=["environments"]
)

# Cloud emulation endpoints (subdomain-based routing)
# Rate limited to prevent abuse of storage operations
app.include_router(
    cloud_emulation.router,
    tags=["cloud-emulation"]
)

# Container registry emulation (ECR, GCR backed by OCIR)
app.include_router(
    container_registry_emulation.router,
    tags=["container-registry"]
)

# AWS services emulation (Route53, IAM, Lambda, etc.)
app.include_router(
    aws_services_emulation.router,
    tags=["aws-services"]
)

# AWS VPC emulation (backed by REAL OCI VCNs in isolated compartment)
app.include_router(
    aws_vpc_emulator.router,
    tags=["aws-vpc"]
)

# AWS Lambda emulation (REAL Docker containers - pay-per-execution)
app.include_router(
    aws_lambda_emulator.router,
    tags=["aws-lambda"]
)

# AWS DynamoDB emulation (PostgreSQL JSONB - pay-per-request)
app.include_router(
    aws_dynamodb_emulator.router,
    tags=["aws-dynamodb"]
)

# AWS SQS emulation (REAL Redis queues - pay-per-request)
app.include_router(
    aws_sqs_emulator.router,
    tags=["aws-sqs"]
)

# Data generation (fake data templates)
# Stricter rate limits to prevent resource exhaustion
app.include_router(
    data_generation.router,
    prefix=f"{settings.API_V1_PREFIX}/data",
    tags=["data-generation"]
)

# DNS management (fake authoritative DNS)
app.include_router(
    dns_management.router,
    prefix=f"{settings.API_V1_PREFIX}/environments",
    tags=["dns-management"]
)

# AI Assistant removed - needs anthropic SDK
# app.include_router(
#     ai_assistant.router,
#     prefix=f"{settings.API_V1_PREFIX}/ai",
#     tags=["ai-assistant"]
# )


@app.on_event("startup")
async def startup_event():
    """
    Application startup - launch background tasks
    """
    logger.info("MockFactory.io starting up...")

    # Start background tasks (auto-shutdown, billing, cleanup)
    # Run in a separate task to avoid blocking startup
    asyncio.create_task(start_background_tasks())

    logger.info("Background tasks started successfully")

    # Optional: Start DNS server (requires elevated privileges or port 5353)
    # Uncomment to enable fake authoritative DNS server:
    # from app.services.dns_server import start_dns_server
    # asyncio.create_task(start_dns_server(port=5353))
    # logger.info("DNS server started on UDP port 5353")


@app.get("/")
async def root():
    return {
        "name": "MockFactory API",
        "version": settings.VERSION,
        "description": "PostgreSQL-first testing platform with cloud emulation",
        "docs": "/docs",
        "features": [
            "PostgreSQL variants: Standard, Supabase, pgvector, PostGIS",
            "Redis for caching and queues",
            "AWS S3/SQS/SNS emulation backed by OCI",
            "GCP Cloud Storage emulation",
            "Azure Blob Storage emulation",
            "Industry-specific mock data generation",
            "Auto-shutdown to prevent runaway costs",
            "Secure Docker-based sandboxing",
            "Authentik SSO integration",
            "Stripe payment processing"
        ]
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
