"""Application configuration via environment variables."""

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All config sourced from env vars / .env file."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://openfmis:openfmis@localhost:5432/openfmis"

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # App
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_LOG_LEVEL: str = "INFO"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            import json

            return json.loads(v)
        return v

    @property
    def database_url_sync(self) -> str:
        """Sync URL for Alembic (replaces asyncpg with psycopg2)."""
        return self.DATABASE_URL.replace("+asyncpg", "")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
