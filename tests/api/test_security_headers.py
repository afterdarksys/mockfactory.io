from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.security_headers import SecurityHeadersMiddleware


def test_security_headers_are_added_to_https_responses():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/")
    async def root():
        return {"ok": True}

    response = TestClient(app, base_url="https://testserver").get("/")

    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
    assert response.headers["Content-Security-Policy"].startswith("default-src 'none'")


def test_hsts_is_not_added_to_plain_http_development_responses():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/")
    async def root():
        return {"ok": True}

    response = TestClient(app, base_url="http://testserver").get("/")

    assert "Strict-Transport-Security" not in response.headers
