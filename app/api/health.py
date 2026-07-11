from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine


router = APIRouter(prefix="/health", tags=["health"])


def database_health() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def redis_health() -> bool:
    try:
        return bool(Redis.from_url(settings.REDIS_URL).ping())
    except Exception:
        return False


@router.get("/live", operation_id="health_liveness")
async def liveness():
    return {"status": "alive"}


@router.get("/ready", operation_id="health_readiness")
async def readiness(
    database_ready: bool = Depends(database_health),
    redis_ready: bool = Depends(redis_health),
):
    dependencies = {
        "database": "ok" if database_ready else "unavailable",
        "redis": "ok" if redis_ready else "unavailable",
    }
    ready = database_ready and redis_ready
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "dependencies": dependencies},
    )
