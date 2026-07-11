from app.main import app


def test_openapi_operation_ids_are_unique():
    schema = app.openapi()
    operation_ids = [
        operation["operationId"]
        for path in schema["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]

    assert len(operation_ids) == len(set(operation_ids))


def test_openapi_documents_distinct_jwt_and_api_key_schemes():
    schemes = app.openapi()["components"]["securitySchemes"]

    assert schemes["OAuth2PasswordBearer"]["type"] == "oauth2"
    assert schemes["ApiKeyAuth"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
    }
