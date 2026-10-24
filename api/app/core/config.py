"""Application settings, read from environment variables (see .env.example)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["development", "test", "production"] = "development"

    # Runtime connection uses the least-privileged application role.
    database_url: SecretStr = SecretStr("postgresql+psycopg://steward_app:change-me@127.0.0.1:5432/steward")
    # Migrations use the schema-owner role. Never used by the running API.
    migration_database_url: SecretStr | None = None
    db_app_role: str = "steward_app"

    app_origin: str = "http://localhost:3000"  # public origin of the web app (CSRF Origin check, email links)
    cookie_secure: bool = False  # forced True in production
    session_idle_hours: int = 12
    session_absolute_days: int = 7
    trust_proxy_headers: bool = False  # honour X-Forwarded-For only behind our own reverse proxy

    # Files
    storage_dir: Path = Path("./var/storage")
    max_upload_bytes: int = 25 * 1024 * 1024
    workspace_storage_quota_bytes: int = 1024 * 1024 * 1024
    monthly_task_quota: int = 500

    # Mail: "outbox" writes .eml files to mail_outbox_dir (development only); "smtp" sends.
    mail_backend: Literal["outbox", "smtp", "disabled"] = "outbox"
    mail_outbox_dir: Path = Path("./var/mail-outbox")
    mail_from: str = "Steward <no-reply@localhost>"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = True

    # Rate limits can be disabled only in tests that are not about rate limiting.
    rate_limit_enabled: bool = True

    request_max_body_bytes: int = Field(default=30 * 1024 * 1024)

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.env == "production":
            self.cookie_secure = True
            if self.mail_backend == "outbox":
                raise ValueError("MAIL_BACKEND=outbox is a development adapter and is not allowed in production")
            if not self.app_origin.startswith("https://"):
                raise ValueError("APP_ORIGIN must be https:// in production")
            if "change-me" in self.database_url.get_secret_value():
                raise ValueError("DATABASE_URL still contains the placeholder password")
            if not self.rate_limit_enabled:
                raise ValueError("Rate limiting cannot be disabled in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
