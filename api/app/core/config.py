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
    # True only behind deploy/Caddyfile, which overwrites X-Real-IP with the real client address.
    trust_proxy_headers: bool = False

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

    # Register / forgot-password / resend-verification always take at least this long, so response
    # time does not reveal whether an account exists. Must exceed the slowest path (Argon2 + DB).
    auth_response_floor_ms: int = 400

    # Signs approval requests (HMAC). Keep it out of the database; rotate by re-requesting pending approvals.
    approval_signing_key: SecretStr = SecretStr("dev-only-approval-signing-key-change-me")

    # Rate limits can be disabled only in tests that are not about rate limiting.
    rate_limit_enabled: bool = True

    request_max_body_bytes: int = Field(default=30 * 1024 * 1024)

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.env != "production":
            return self
        self.cookie_secure = True
        problems = []
        placeholders = ("change-me", "replace-me", ":devapp@", ":devowner@")
        if any(p in self.database_url.get_secret_value() for p in placeholders):
            problems.append("DATABASE_URL still contains a placeholder or development password")
        key = self.approval_signing_key.get_secret_value()
        if len(key) < 32 or any(p in key for p in placeholders):
            problems.append("APPROVAL_SIGNING_KEY must be a random secret of at least 32 characters")
        if self.mail_backend != "smtp":
            problems.append("MAIL_BACKEND must be smtp (users cannot verify or recover accounts otherwise)")
        elif not self.smtp_host or not self.smtp_starttls:
            problems.append("SMTP_HOST is required and SMTP_STARTTLS must stay enabled")
        if not self.app_origin.startswith("https://"):
            problems.append("APP_ORIGIN must be https://")
        if not self.rate_limit_enabled:
            problems.append("rate limiting cannot be disabled")
        if not self.trust_proxy_headers:
            problems.append(
                "TRUST_PROXY_HEADERS must be true behind the Caddy proxy (otherwise every user shares one rate-limit bucket)"
            )
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
