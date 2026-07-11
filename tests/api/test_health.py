from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import health


def test_liveness_does_not_depend_on_external_services():
    app = FastAPI()
    app.include_router(health.router)

    response = TestClient(app).get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_reports_dependency_failure_without_secrets():
    app = FastAPI()
    app.include_router(health.router)
    app.dependency_overrides[health.database_health] = lambda: False
    app.dependency_overrides[health.redis_health] = lambda: True

    response = TestClient(app).get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "dependencies": {"database": "unavailable", "redis": "ok"},
    }
