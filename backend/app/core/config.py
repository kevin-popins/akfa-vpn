from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AKFA"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://akfa:akfa@postgres:5432/akfa"
    session_secret: str = Field("change-me-session-secret", min_length=16)
    encryption_key: str = Field(
        "MDEyMzQ1Njc4OUFCQ0RFRjAxMjM0NTY3ODlBQkNERUY=",
        description="Fernet key used for stored SSH credentials",
    )
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8080"]
    secure_cookies: bool = False
    access_cookie_name: str = "akfa_session"
    csrf_cookie_name: str = "akfa_csrf"
    subscription_base_url: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
