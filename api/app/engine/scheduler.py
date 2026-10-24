"""Scheduler: due automations become tasks (one per schedule slot), deleted files past retention
get a purge job, and jobs whose worker died are recovered.

Duplicate-run protection: the automation row is locked with SKIP LOCKED, the task carries an
idempotency key per slot, and next_run_at advances in the same transaction.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import utcnow
from app.domain.enums import JobQueue, TaskStatus, WaitingFor
from app.engine import queue as Q
from app.engine.records import audit, event
from app.models import Automation, FileRecord, Task, Workspace
from app.services.usage import bump_usage, current_period, usage_value

log = logging.getLogger("steward.scheduler")
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def next_run(a: Automation, after: datetime) -> datetime | None:
    if a.trigger != "schedule" or not a.frequency:
        return None
    try:
        tz = ZoneInfo(a.timezone or "UTC")
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", a.time_of_day or "08:00")
    hh, mm = (int(m.group(1)), int(m.group(2))) if m else (8, 0)
    local = after.astimezone(tz)
    cand = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    for _ in range(400):
        ok = (
            a.frequency == "daily"
            or (a.frequency == "weekly" and DAYS[cand.weekday()] == (a.day or "monday").lower())
            or (a.frequency == "monthly" and cand.day == 1)
        )
        if ok and cand > local:
            return cand.astimezone(ZoneInfo("UTC"))
        cand = cand + timedelta(days=1)
    return None


def _create_task(db: Session, a: Automation, slot: datetime, settings: Settings) -> uuid.UUID | None:
    key = f"auto:{a.id}:{slot:%Y%m%dT%H%M}"
    existing = db.execute(
        select(Task.id).where(Task.workspace_id == a.workspace_id, Task.idempotency_key == key)
    ).scalar_one_or_none()
    if existing is not None:
        return None
    if usage_value(db, a.workspace_id, current_period(), "tasks_created") >= settings.monthly_task_quota:
        audit(
            db,
            a.workspace_id,
            "automation.skipped",
            "task",
            f'Automation "{a.name}" skipped: monthly task limit reached',
            target_type="automation",
            target_id=str(a.id),
        )
        return None
    number = int(
        db.execute(
            update(Workspace)
            .where(Workspace.id == a.workspace_id)
            .values(task_seq=Workspace.task_seq + 1)
            .returning(Workspace.task_seq)
        ).scalar_one()
    )
    t = Task(
        workspace_id=a.workspace_id,
        number=number,
        title=a.name[:200],
        prompt=f'Scheduled run of automation "{a.name}" using template {a.template}.',
        status=TaskStatus.queued.value,
        type="website" if ("WordPress" in a.template or "Plugin" in a.template) else "seo_content",
        priority="normal",
        mode="plan_only",
        waiting_for=WaitingFor.planning_service.value,
        idempotency_key=key,
        automation_id=a.id,
        created_by=a.created_by,
    )
    db.add(t)
    db.flush()
    event(db, t, "task.created", f'Created by the scheduler for automation "{a.name}" (slot {slot:%Y-%m-%d %H:%M} UTC)')
    Q.enqueue(
        db,
        workspace_id=a.workspace_id,
        kind="task.plan",
        queue=JobQueue.orchestrator,
        task_id=t.id,
        dedupe_key=f"plan:{t.id}",
        settings=settings,
    )
    bump_usage(db, a.workspace_id, "tasks_created", 1)
    audit(
        db,
        a.workspace_id,
        "automation.run",
        "task",
        f'Automation "{a.name}" queued T-{number}',
        task_id=t.id,
        target_type="automation",
        target_id=str(a.id),
    )
    return t.id


def run_due_automations(db: Session, settings: Settings, now: datetime | None = None) -> int:
    now = now or utcnow()
    rows = (
        db.execute(
            select(Automation)
            .where(
                Automation.enabled.is_(True),
                Automation.trigger == "schedule",
                Automation.next_run_at.is_not(None),
                Automation.next_run_at <= now,
            )
            .order_by(Automation.next_run_at)
            .limit(50)
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )
    created = 0
    for a in rows:
        slot = a.next_run_at or now
        try:
            with db.begin_nested():
                if _create_task(db, a, slot, settings):
                    created += 1
        except Q.QueueFull:
            log.warning("queue full; automation %s deferred", a.id)
            continue
        a.last_run_at = now
        a.next_run_at = next_run(a, max(now, slot))
        a.updated_at = now
    db.commit()
    return created


def schedule_purges(db: Session, settings: Settings, now: datetime | None = None) -> int:
    now = now or utcnow()
    ws_ids = (
        db.execute(
            select(FileRecord.workspace_id)
            .where(
                FileRecord.deleted_at.is_not(None), FileRecord.purge_after.is_not(None), FileRecord.purge_after <= now
            )
            .group_by(FileRecord.workspace_id)
        )
        .scalars()
        .all()
    )
    for ws in ws_ids:
        Q.enqueue(
            db,
            workspace_id=ws,
            kind="deletion.purge",
            queue=JobQueue.deletion,
            dedupe_key=f"purge:{now:%Y%m%d%H}",
            settings=settings,
        )
    db.commit()
    return len(ws_ids)


def tick(db: Session, settings: Settings) -> dict[str, int]:
    recovered = Q.recover_stale(db, settings)
    created = run_due_automations(db, settings)
    purges = schedule_purges(db, settings)
    return {"recovered": recovered, "automation_tasks": created, "purge_jobs": purges}


def pending_count(db: Session) -> int:
    return int(
        db.execute(select(func.count()).select_from(Automation).where(Automation.enabled.is_(True))).scalar_one()
    )
