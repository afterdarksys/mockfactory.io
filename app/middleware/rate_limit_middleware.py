"""
Global Rate Limiting Middleware
"""
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response
from slowapi.errors import RateLimitExceeded
import logging

from app.core.rate_limit import limiter, get_user_tier_limits

logger = logging.getLogger(__name__)


class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Apply rate limiting to all requests based on user tier

    Exemptions:
    - Health check endpoints
    - Static files
    - Documentation
    """

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks and docs
        if request.url.path in ["/health", "/", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)

        # Apply tier-based rate limiting
        try:
            # Get user tier limits
            limit_string = get_user_tier_limits(request)

            # Apply rate limit using slowapi
            await limiter.limit(limit_string)(request)

            # If rate limit passed, proceed with request
            response = await call_next(request)
            return response

        except RateLimitExceeded as e:
            # Log rate limit violations
            logger.warning(
                f"Rate limit exceeded for {request.url.path} "
                f"from {request.client.host}"
            )
            raise

        except Exception as e:
            # Log other errors but don't block requests
            logger.error(f"Error in rate limit middleware: {e}")
            return await call_next(request)
