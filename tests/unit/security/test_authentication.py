from types import SimpleNamespace

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.security import auth


def test_x_api_key_header_authenticates_automation(monkeypatch):
    app = FastAPI()
    active_user = SimpleNamespace(id=7, is_active=True)

    async def fake_verify_api_key(api_key, db):
        return active_user if api_key == "mf_valid" else None

    monkeypatch.setattr(auth, "verify_api_key", fake_verify_api_key)
    app.dependency_overrides[get_db] = lambda: object()

    @app.get("/protected")
    async def protected(user=Depends(auth.require_authenticated_request)):
        return {"user_id": user.id}

    response = TestClient(app).get("/protected", headers={"X-API-Key": "mf_valid"})

    assert response.status_code == 200
    assert response.json() == {"user_id": 7}


def test_missing_credentials_returns_401():
    app = FastAPI()
    app.dependency_overrides[get_db] = lambda: object()

    @app.get("/protected")
    async def protected(user=Depends(auth.require_authenticated_request)):
        return {"user_id": user.id}

    response = TestClient(app).get("/protected")

    assert response.status_code == 401
