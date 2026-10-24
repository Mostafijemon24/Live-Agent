"""Usage counters and quotas."""

from __future__ import annotations

import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import schemas as S
from app.core.config import get_settings
from app.core.db import utcnow
from app.models import UsageCounter


def current_period() -> str:
    return utcnow().strftime("%Y-%m")


def bump_usage(db: Session, ws_id: uuid.UUID, metric: str, amount: int, period: str | None = None) -> None:
    db.execute(
        text(
            "INSERT INTO usage_counters (workspace_id, period, metric, used) VALUES (:w, :p, :m, :a) "
            "ON CONFLICT (workspace_id, period, metric) DO UPDATE SET used = usage_counters.used + :a"
        ),
        {"w": ws_id, "p": period or current_period(), "m": metric, "a": amount},
    )


def usage_value(db: Session, ws_id: uuid.UUID, period: str, metric: str) -> int:
    v = db.execute(
        select(UsageCounter.used).where(
            UsageCounter.workspace_id == ws_id, UsageCounter.period == period, UsageCounter.metric == metric
        )
    ).scalar_one_or_none()
    return int(v or 0)


def usage_report(db: Session, ws_id: uuid.UUID) -> S.UsageOut:
    s = get_settings()
    p = current_period()
    return S.UsageOut(
        period=p,
        tracked=True,
        items=[
            S.UsageItem(
                key="tasks_created",
                label="Tasks created this month",
                used=usage_value(db, ws_id, p, "tasks_created"),
                limit=s.monthly_task_quota,
                unit="tasks",
            ),
            S.UsageItem(
                key="storage_bytes",
                label="File storage",
                used=usage_value(db, ws_id, "all", "storage_bytes"),
                limit=s.workspace_storage_quota_bytes,
                unit="bytes",
            ),
            S.UsageItem(
                key="files_uploaded",
                label="Files uploaded this month",
                used=usage_value(db, ws_id, p, "files_uploaded"),
                limit=None,
                unit="files",
            ),
            S.UsageItem(key="ai_runs", label="AI agent runs", used=0, limit=None, unit="runs (engine not installed)"),
        ],
    )
