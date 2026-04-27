from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWT_SECRET: str
    DATABASE_URL: str
    DATABASE_URL_POOLED: str
    REDIS_URL: str
    ANTHROPIC_API_KEY: str
    OPENAI_API_KEY: str
    HUNTER_API_KEY: str = ""
    APOLLO_API_KEY: str = ""
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    ENCRYPTION_KEY: str
    CACHE_SIMILARITY_THRESHOLD: float = 0.88
    ENVIRONMENT: Literal["development", "production"] = "development"
    FRONTEND_URL: str = "http://localhost:3000"


settings = Settings()
