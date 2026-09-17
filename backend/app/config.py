from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mock_azure: bool = True
    azure_maps_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./data/leavenow.db"
    cache_ttl_hours: int = Field(default=6, ge=1)
    stale_max_hours: int = Field(default=24, ge=1)
    cache_bucket_minutes: int = Field(default=15, ge=5)
    max_azure_concurrency: int = Field(default=5, ge=1, le=10)
    app_timezone: str = "Asia/Kolkata"


@lru_cache
def get_settings() -> Settings:
    return Settings()
