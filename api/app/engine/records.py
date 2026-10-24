"""Task events, audit records, notifications and state transitions written by workers.

Workers act as the system: audit rows have no actor user (shown as "Agent") and carry the
job id for correlation.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.domain.enums import TaskStatus, WaitingFor
from app.domain.task_states import assert_transition
from app.models import AuditEvent, Notification, Task, TaskEvent
from app.services.audit import scrub

log = logging.getLogger("steward.engine")


def event(
    db: Session,
    task: Task,
    kind: str,
    message: str,
    level: str = "info",
    from_status: str | None = None,
    to_status: str | None = None,
) -> None:
    db.add(
        TaskEvent(
            workspace_id=task.workspace_id,
            task_id=task.id,
            kind=kind,
            message=message[:2000],
            level=level,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=None,
        )
    )


def audit(
    db: Session,
    workspace_id: uuid.UUID,
    action: str,
    category: str,
    message: str,
    *,
    task_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    job_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    meta = dict(metadata or {})
    if job_id:
        meta["job_id"] = str(job_id)
    # Core INSERT without RETURNING: the deletion service may write audit rows but not read them.
    db.flush()
    db.execute(
        insert(AuditEvent).values(
            id=uuid.uuid4(),  # client-side id: no RETURNING (and so no SELECT privilege) needed
            workspace_id=workspace_id,
            actor_user_id=None,
            action=action,
            category=category,
            message=message[:1000],
            target_type=target_type,
            target_id=target_id,
            task_id=task_id,
            request_id=f"job:{job_id}" if job_id else None,
            meta=scrub(meta),
        )
    )
    log.info("%s workspace=%s task=%s job=%s", action, workspace_id, task_id, job_id)


def notify(
    db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID, type_: str, icon: str, text: str, route: str
) -> None:
    db.flush()
    db.execute(
        insert(Notification).values(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            user_id=user_id,
            type=type_,
            icon=icon,
            text=text[:300],
            target={"route": route},
        )
    )


def transition(db: Session, task: Task, dst: TaskStatus, reason: str, waiting_for: WaitingFor | None = None) -> None:
    src = TaskStatus(task.status)
    if src == dst:
        task.waiting_for = waiting_for.value if waiting_for else None
        return
    assert_transition(src, dst)
    task.status = dst.value
    task.waiting_for = waiting_for.value if waiting_for else None
    task.updated_at = utcnow()
    if dst == TaskStatus.running and task.started_at is None:
        task.started_at = utcnow()
    if dst in (TaskStatus.completed, TaskStatus.partially_completed, TaskStatus.failed, TaskStatus.cancelled):
        task.finished_at = utcnow()
    event(db, task, "task.status_changed", reason, "info", src.value, dst.value)
    audit(
        db,
        task.workspace_id,
        "task.status_changed",
        "task",
        f"T-{task.number}: {reason}",
        task_id=task.id,
        target_type="task",
        target_id=str(task.id),
        metadata={"from": src.value, "to": dst.value},
    )
