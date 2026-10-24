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
    # "api" (default, strictest) or "worker". HTTP-only production checks (SMTP, proxy headers,
    # https origin, rate limiting) apply to the API; workers never serve HTTP or send mail.
    process_role: Literal["api", "worker"] = "api"

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
    # Database pool per API process (see docs/PERFORMANCE.md for the connection budget).
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_pool_timeout_seconds: float = 5.0
    # GET /metrics is served only with this bearer token (unset = disabled). Never routed publicly.
    metrics_token: SecretStr | None = None

    # ---------------------------------------------------------------- agent engine (Phase 3)
    # Database roles for background processes (see deploy/db/init-roles.sh). Never the owner role.
    worker_database_url: SecretStr | None = None  # steward_worker: orchestrator, tool runner, scheduler
    deletion_database_url: SecretStr | None = None  # steward_deleter: deletion service only

    # Model provider. "none" = no model: tasks wait instead of being sent anywhere.
    # "mock" = deterministic in-process planner for development and tests (refused in production).
    # "openai_compatible" = any /v1/chat/completions endpoint (OpenAI, Azure-compatible gateways,
    # or a self-hosted Ollama / vLLM / llama.cpp server).
    model_provider: Literal["none", "mock", "openai_compatible"] = "none"
    model_base_url: str | None = None  # e.g. https://api.openai.com/v1 or http://ollama:11434/v1
    model_name: str = ""
    model_api_key: SecretStr | None = None  # server-side only; never sent to the browser or the model
    # Where the model runs. "local" = on infrastructure you operate (data still leaves this API
    # process but stays on your servers). "external" = a third-party service: data leaves your servers.
    model_location: Literal["local", "external"] = "external"
    model_provider_label: str = ""  # shown to users, e.g. "OpenAI (US)" or "Ollama on this server"
    model_timeout_seconds: float = 30.0
    model_max_retries: int = 2
    model_max_input_chars: int = 24_000
    model_max_output_tokens: int = 1_500
    monthly_model_token_quota: int = 2_000_000  # per workspace, input + output tokens
    monthly_model_call_quota: int = 2_000

    # Outbound HTTP made by tools (web inspection, WordPress read). Only allowlisted domains,
    # never private/loopback/link-local addresses unless explicitly allowed (development only).
    egress_timeout_seconds: float = 10.0
    egress_max_bytes: int = 2 * 1024 * 1024
    egress_max_redirects: int = 3
    egress_allow_http: bool = False
    egress_allow_private_networks: bool = False
    egress_proxy_url: str | None = None  # optional forward proxy (e.g. a filtering proxy on the egress network)
    egress_user_agent: str = "StewardAgent/0.3 (+read-only inspection)"

    # Durable queue and workers
    queue_max_pending_per_workspace: int = 200
    queue_max_pending_total: int = 10_000
    queue_max_running_per_workspace: int = 2
    job_lease_seconds: int = 120  # a running job without a heartbeat for this long is recovered
    job_backoff_base_seconds: float = 2.0
    job_backoff_max_seconds: float = 300.0
    worker_concurrency: int = 2
    worker_poll_seconds: float = 1.0
    worker_shutdown_grace_seconds: float = 30.0

    # Sandbox for code execution (tools worker only). Fails closed when isolation is unavailable.
    sandbox_enabled: bool = True
    sandbox_timeout_seconds: float = 10.0
    sandbox_memory_mb: int = 256
    sandbox_max_output_bytes: int = 64 * 1024

    # Deleted files are kept (soft-deleted, restorable) for this many days, then purged.
    deletion_retention_days: int = 30
    max_plan_steps: int = 8

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.env != "production":
            return self
        self.cookie_secure = True
        problems = []
        if self.model_provider == "mock":
            problems.append("MODEL_PROVIDER=mock is for development and tests only")
        if self.model_provider == "openai_compatible":
            if not self.model_base_url or not self.model_name:
                problems.append("MODEL_BASE_URL and MODEL_NAME are required for the openai_compatible provider")
            elif self.model_location == "external" and not self.model_base_url.startswith("https://"):
                problems.append("an external model provider must use https://")
        if self.egress_allow_private_networks or self.egress_allow_http:
            problems.append("EGRESS_ALLOW_PRIVATE_NETWORKS and EGRESS_ALLOW_HTTP must be false in production")
        for name in ("worker_database_url", "deletion_database_url"):
            v = getattr(self, name)
            if v is not None and any(p in v.get_secret_value() for p in ("change-me", ":dev")):
                problems.append(f"{name.upper()} still contains a placeholder or development password")
        placeholders = ("change-me", "replace-me", ":devapp@", ":devowner@")
        if any(p in self.database_url.get_secret_value() for p in placeholders):
            problems.append("DATABASE_URL still contains a placeholder or development password")
        key = self.approval_signing_key.get_secret_value()
        if len(key) < 32 or any(p in key for p in placeholders):
            problems.append("APPROVAL_SIGNING_KEY must be a random secret of at least 32 characters")
        if self.process_role == "api":
            problems.extend(self._http_guards())
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self

    def _http_guards(self) -> list[str]:
        problems = []
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
        return problems

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
