"""
Root conftest — set env vars before any app module is imported so that
pydantic-settings can instantiate Settings() successfully.
"""
import os

import pytest
from cryptography.fernet import Fernet

TEST_ENCRYPTION_KEY: str = Fernet.generate_key().decode()

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("DATABASE_URL_POOLED", "postgresql://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
os.environ.setdefault("HUNTER_API_KEY", "test-hunter-key")
os.environ.setdefault("APOLLO_API_KEY", "test-apollo-key")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "test-google-client-id")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_SECRET", "test-google-client-secret")


@pytest.fixture(autouse=True)
def patch_settings_encryption_key(monkeypatch):
    """Ensure every test uses the same Fernet key regardless of .env files."""
    from app.config import settings
    monkeypatch.setattr(settings, "ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
