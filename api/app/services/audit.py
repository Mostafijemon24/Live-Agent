"""Append-only audit logging. Metadata is scrubbed so secrets never reach the log."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent
from app.ports import AuditRecord

_SECRET_KEY = re.compile(r"pass|secret|token|cookie|authorization|api[_-]?key|session|csrf|credential", re.I)


def scrub(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return "[truncated]"
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if _SECRET_KEY.search(str(k)) else scrub(v, depth + 1)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v, depth + 1) for v in value[:50]]
    if isinstance(value, str):
        return value[:500]
    return value


class DbAuditLogger:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record(self, rec: AuditRecord) -> None:
        self.db.add(
            AuditEvent(
                workspace_id=rec.workspace_id,
                actor_user_id=rec.actor_user_id,
                action=rec.action,
                category=rec.category,
                message=rec.message[:1000],
                target_type=rec.target_type,
                target_id=rec.target_id,
                task_id=rec.task_id,
                ip=rec.ip,
                request_id=rec.request_id,
                meta=scrub(rec.metadata),
            )
        )
        self.db.flush()
