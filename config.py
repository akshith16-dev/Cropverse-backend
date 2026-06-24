from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./cropverse.db"
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    GEMINI_API_KEY: str = ""
    GEMINI_TIMEOUT_SECONDS: int = 12
    REDIS_URL: str = ""
    APP_NAME: str = "Cropverse"
    DEBUG: bool = True
    CORS_ORIGINS: str = "http://localhost:5173,https://cropverse-frontend.vercel.app"
    RATE_LIMIT_DEFAULT: str = "120/minute"
    MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024

    S3_BUCKET: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_REGION: str = "us-east-1"
    S3_ENDPOINT_URL: str = ""
    S3_PUBLIC_BASE_URL: str = ""

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "production", "prod"}:
                return False
            if normalized in {"debug", "development", "dev"}:
                return True
        return value

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, value: str) -> str:
        if not value or len(value) < 16:
            raise ValueError("SECRET_KEY must be at least 16 characters")
        return value

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    class Config:
        env_file = ".env"

settings = Settings()
