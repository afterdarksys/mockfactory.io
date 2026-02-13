"""
Rate Limiting Configuration - Protect against abuse and DoS attacks
"""
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from typing import Optional
import redis

from app.core.config import settings


def get_rate_limit_key(request: Request) -> str:
    """
    Determine rate limit key based on authentication

    Priority:
    1. API Key (from X-API-Key header or Authorization)
    2. User ID (from JWT token)
    3. IP Address (fallback for unauthenticated requests)
    """
    # Check for API key in headers
    api_key = request.headers.get("x-api-key")
    if api_key:
        return f"apikey:{api_key[:16]}"  # Use first 16 chars as identifier

    # Check Authorization header for ApiKey or Bearer token
    auth = request.headers.get("authorization", "")
    if auth.startswith("ApiKey "):
        api_key = auth[7:]
        return f"apikey:{api_key[:16]}"

    # Check for user in request state (set by auth middleware)
    if hasattr(request.state, "user") and request.state.user:
        return f"user:{request.state.user.id}"

    # Fallback to IP address
    return f"ip:{get_remote_address(request)}"


def get_user_tier_limits(request: Request) -> str:
    """
    Get rate limit string based on user tier

    Tiers (from PRICING_TIERS.md):
    - FREE: 1,000 requests/hour
    - STARTER: 2,000 requests/hour
    - DEVELOPER: 5,000 requests/hour
    - TEAM: 7,500 requests/hour
    - BUSINESS: 10,000 requests/hour
    - ENTERPRISE: Unlimited

    Returns: slowapi limit string (e.g., "1000/hour")
    """
    if hasattr(request.state, "user") and request.state.user:
        user = request.state.user
        tier = user.tier.value if hasattr(user.tier, 'value') else str(user.tier)

        tier_limits = {
            "anonymous": "100/hour",     # Very restrictive for anonymous
            "beginner": "1000/hour",     # FREE tier
            "student": "2000/hour",      # STARTER tier
            "professional": "5000/hour", # DEVELOPER tier
            "government": "7500/hour",   # TEAM tier
            "enterprise": "10000/hour",  # BUSINESS tier
            "custom": "50000/hour",      # ENTERPRISE tier
            "employee": "100000/hour"    # Internal use
        }

        return tier_limits.get(tier, "1000/hour")

    # Unauthenticated requests - very restrictive
    return "100/hour"


# Initialize rate limiter with Redis backend for distributed rate limiting
try:
    redis_client = redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True
    )
    limiter = Limiter(
        key_func=get_rate_limit_key,
        storage_uri=settings.REDIS_URL,
        strategy="fixed-window"
    )
except Exception as e:
    # Fallback to in-memory rate limiting if Redis unavailable
    print(f"Warning: Redis unavailable for rate limiting, using in-memory: {e}")
    limiter = Limiter(
        key_func=get_rate_limit_key,
        strategy="fixed-window"
    )


# Rate limit decorators for different endpoint types

# General API endpoints - tier-based limits
general_api_limit = limiter.limit(get_user_tier_limits)

# Cloud emulation endpoints - higher limits for S3/GCS/Azure operations
cloud_api_limit = limiter.limit(lambda request: f"{int(get_user_tier_limits(request).split('/')[0]) * 2}/hour")

# Authentication endpoints - prevent brute force
auth_limit = limiter.limit("10/minute")

# Data generation endpoints - prevent resource exhaustion
data_gen_limit = limiter.limit("50/hour")

# Environment provisioning - prevent resource exhaustion
provision_limit = limiter.limit("20/hour")
