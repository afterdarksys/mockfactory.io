import os


TEST_ENV = {
    "DATABASE_URL": "sqlite+pysqlite:///:memory:",
    "REDIS_URL": "redis://localhost:6379/15",
    "SECRET_KEY": "test-secret-key-that-is-long-enough",
    "OAUTH_CLIENT_ID": "test-client",
    "OAUTH_CLIENT_SECRET": "test-client-secret",
    "OAUTH_AUTHORIZE_URL": "https://auth.test/authorize",
    "OAUTH_TOKEN_URL": "https://auth.test/token",
    "OAUTH_USERINFO_URL": "https://auth.test/userinfo",
    "STRIPE_SECRET_KEY": "sk_test_mockfactory",
    "STRIPE_PUBLISHABLE_KEY": "pk_test_mockfactory",
    "STRIPE_WEBHOOK_SECRET": "whsec_test_mockfactory",
}

for key, value in TEST_ENV.items():
    os.environ.setdefault(key, value)
