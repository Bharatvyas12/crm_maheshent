"""Technical configuration (docs/01_ARCHITECTURE.md section 23).

Business rules are NEVER read from here; they live in `business_settings`.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    database_url: str = "postgresql+psycopg://postgres@127.0.0.1:55432/crm"
    environment: str = "development"
    log_level: str = "INFO"
    signing_key: str = "dev-insecure-signing-key-change-me"

    session_cookie_name: str = "wcrm_session"
    csrf_cookie_name: str = "wcrm_csrf"
    cookie_secure: bool = False
    cookie_domain: str | None = None
    cors_origins: str = "http://localhost:3000"

    storage_backend: str = "local"
    storage_local_root: str = "backend/var/storage"

    scheduler_enabled: bool = False
    expected_migration_head: str | None = None

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod", "staging"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_config() -> Settings:
    return Settings()