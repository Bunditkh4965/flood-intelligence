from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded exclusively from environment variables."""

    database_url: str = "postgresql+psycopg://flood:flood@localhost:5432/flood_intelligence"
    reporter_gps_verify_radius_m: float = 300.0
    gistda_api_key: str = ""
    gistda_api_base_url: str = "https://api-gateway.gistda.or.th/api/2.0/resources"
    gistda_connect_timeout_seconds: float = 5.0
    gistda_read_timeout_seconds: float = 30.0
    photo_storage_directory: str = "./var/flood-report-photos"
    photo_max_bytes: int = 8 * 1024 * 1024
    cors_allowed_origins: str = "http://localhost:3000"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
