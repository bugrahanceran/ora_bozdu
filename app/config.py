from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ora_bozdu"
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./data/ora_bozdu.db"
    google_maps_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="GOOGLE_MAPS_API_KEY",
    )
    apify_api_token: SecretStr | None = Field(
        default=None,
        validation_alias="APIFY_TOKEN",
    )
    venue_catalog_path: Path = Path("config/catalog.eryaman.yaml")
    data_collection_config_path: Path = Path("config/data_collection.eryaman.yaml")
    scoring_config_path: Path = Path("config/scoring.v6.toml")
    http_timeout_seconds: float = 15.0
    http_max_retries: int = 2
    app_timezone: str = "Europe/Istanbul"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
