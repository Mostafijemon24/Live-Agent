"""Fixed-window rate limiting stored in PostgreSQL (works across several API processes).

Each hit is an atomic `INSERT … ON CONFLICT DO UPDATE … RETURNING count`. The
counter runs in its own short transaction so a later rollback of the request
(e.g. failed login) never undoes the count.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, text

from app.core.config import get_settings
from app.core.db import session_factory
from app.core.errors import ApiError
from app.models import RateLimitBucket


@dataclass(frozen=True)
class Limit:
    name: str
    max_hits: int
    window_seconds: int


# Named limits (documented in API_CONTRACT.md).
LOGIN_IP = Limit("login_ip", 20, 900)
LOGIN_EMAIL = Limit("login_email", 10, 900)
REGISTER_IP = Limit("register_ip", 5, 3600)
REGISTER_EMAIL = Limit("register_email", 3, 3600)
FORGOT_IP = Limit("forgot_ip", 5, 3600)
FORGOT_EMAIL = Limit("forgot_email", 3, 3600)
RESEND_IP = Limit("resend_ip", 5, 3600)
RESEND_EMAIL = Limit("resend_email", 3, 3600)
RESET_IP = Limit("reset_ip", 10, 3600)
VERIFY_IP = Limit("verify_ip", 20, 3600)
TASK_CREATE_USER = Limit("task_create_user", 30, 60)
UPLOAD_USER = Limit("upload_user", 30, 600)
WRITE_USER = Limit("write_user", 120, 60)
ACCOUNT_REQUEST_USER = Limit("account_request_user", 3, 3600)
# Cross-workspace / unknown-ID probes. Each one writes an audit row, so they are capped.
DENIED_USER = Limit("denied_user", 30, 600)


def _key(limit: Limit, subject: str) -> str:
    # Subjects (emails, IPs) are hashed so the table holds no personal data in clear text.
    digest = hashlib.sha256(subject.lower().encode("utf-8")).hexdigest()[:40]
    return f"{limit.name}:{digest}"


def hit(limit: Limit, subject: str) -> None:
    """Count one attempt; raise 429 when the window is exhausted."""
    if not get_settings().rate_limit_enabled:
        return
    now = datetime.now(UTC)
    epoch = int(now.timestamp())
    window_start = datetime.fromtimestamp(epoch - epoch % limit.window_seconds, UTC)
    key = _key(limit, subject)
    with session_factory()() as db:
        count = db.execute(
            text(
                "INSERT INTO rate_limit_buckets (key, window_start, count) VALUES (:k, :w, 1) "
                "ON CONFLICT (key, window_start) DO UPDATE SET count = rate_limit_buckets.count + 1 "
                "RETURNING count"
            ),
            {"k": key, "w": window_start},
        ).scalar_one()
        # Opportunistic cleanup of old windows (the only table the app role may DELETE from).
        if count == 1:
            db.execute(delete(RateLimitBucket).where(RateLimitBucket.window_start < now - timedelta(days=1)))
        db.commit()
    if count > limit.max_hits:
        retry = int((window_start + timedelta(seconds=limit.window_seconds) - now).total_seconds()) + 1
        raise ApiError(
            429,
            "rate_limited",
            "Too many attempts. Please wait a few minutes and try again.",
            details={"retry_after_seconds": retry},
            headers={"Retry-After": str(retry)},
        )
