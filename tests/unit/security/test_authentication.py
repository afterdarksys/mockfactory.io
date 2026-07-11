from types import SimpleNamespace
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app.core.database import get_db
from app.security import auth


class FakeQuery:
    def __init__(self, result):
        self.result = result

    def filter(self, *args):
        return self

    def first(self):
        return self.result


class FakeDB:
    def __init__(self, result):
        self.result = result
        self.commits = 0

    def query(self, model):
        return FakeQuery(self.result)

    def commit(self):
        self.commits += 1


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


@pytest.mark.anyio
async def test_expired_api_key_is_rejected_without_updating_last_used():
    user = SimpleNamespace(id=7, is_active=True)
    record = SimpleNamespace(
        is_active=True,
        expires_at=datetime.utcnow() - timedelta(seconds=1),
        last_used_at=None,
        user=user,
        is_valid=lambda: False,
    )
    db = FakeDB(record)

    assert await auth.verify_api_key("mf_expired", db) is None
    assert record.last_used_at is None
    assert db.commits == 0


@pytest.mark.anyio
async def test_api_key_for_inactive_user_is_rejected():
    user = SimpleNamespace(id=7, is_active=False)
    record = SimpleNamespace(
        is_active=True,
        expires_at=None,
        last_used_at=None,
        user=user,
        is_valid=lambda: True,
    )

    assert await auth.verify_api_key("mf_inactive_user", FakeDB(record)) is None


@pytest.mark.anyio
async def test_jwt_with_non_numeric_subject_returns_401():
    token = auth.create_access_token({"sub": "not-a-user-id"})

    with pytest.raises(HTTPException) as error:
        await auth.get_current_user(token=token, db=FakeDB(None))

    assert error.value.status_code == 401
