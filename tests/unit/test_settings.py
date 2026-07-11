from app.core.config import Settings


def test_settings_can_be_created_from_explicit_test_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")

    configured = Settings()

    assert configured.DATABASE_URL == "sqlite+pysqlite:///:memory:"
    assert configured.REDIS_URL.endswith("/15")
    assert configured.SECRET_KEY == "test-secret-key-that-is-long-enough"
