from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.errors import install_error_handlers
from app.middleware.request_id import RequestIDMiddleware


def build_app():
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    install_error_handlers(app)

    @app.get("/missing")
    async def missing():
        raise HTTPException(status_code=404, detail="Widget not found")

    @app.get("/widgets/{widget_id}")
    async def widget(widget_id: int):
        return {"id": widget_id}

    return app


def test_http_error_uses_standard_envelope_and_request_id():
    response = TestClient(build_app()).get(
        "/missing", headers={"X-Request-ID": "req_client_123"}
    )

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "req_client_123"
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Widget not found",
            "request_id": "req_client_123",
            "retryable": False,
            "details": [],
        }
    }


def test_validation_error_has_stable_code_and_details():
    response = TestClient(build_app()).get("/widgets/not-an-integer")

    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_failed"
    assert body["request_id"].startswith("req_")
    assert body["retryable"] is False
    assert body["details"][0]["field"] == "path.widget_id"
