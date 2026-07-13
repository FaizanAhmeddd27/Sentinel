from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List
import os


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "Sentinel"
    app_env: str = "development"
    app_debug: bool = False
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    allowed_origins: str = "http://localhost:3000"

    # Google OAuth2
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_key: str
    supabase_storage_bucket: str = "sentinel-files"

    # Database
    database_url: str

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_cache_ttl: int = 300

    # Groq AI
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"
    groq_fallback_model: str = "llama-3.1-8b-instant"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Correlation Engine
    correlation_time_tolerance_seconds: float = 2.0
    correlation_amount_tolerance_pkr: float = 0.01
    correlation_fuzzy_threshold: int = 85

    # File Upload
    max_upload_size_mb: int = 50
    allowed_file_types: str = "csv,xml,xlsx,log,txt"

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",")]

    @property
    def allowed_file_types_list(self) -> List[str]:
        return [ft.strip() for ft in self.allowed_file_types.split(",")]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()