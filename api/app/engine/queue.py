"""Durable job queue in PostgreSQL (the `jobs` table).

- enqueue: idempotent through (workspace_id, dedupe_key); refuses new work when a workspace or
  the whole queue is over its pending limit (backpressure).
- claim: `FOR UPDATE SKIP LOCKED`, ordered by priority then run_after; skips workspaces that
  already have `queue_max_running_per_workspace` running jobs (fair share).
- heartbeat while running; a job whose heartbeat is older than the lease is recovered by
  `recover_stale` (re-queued with backoff, or dead-lettered when attempts are used up).
- retry: exponential backoff with full jitter, bounded by max_attempts → `dead` (dead letter).
- cancel: pending jobs of a task are cancelled; running jobs see the task status and stop.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import utcnow
from app.core.errors import ApiError
from app.domain.enums import JobQueue, JobStatus
from app.models import Job


class QueueFull(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(503, "queue_full", message)


@dataclass(frozen=True)
class ClaimedJob:
    id: uuid.UUID
    workspace_id: uuid.UUID
    kind: str
    queue: str
    task_id: uuid.UUID | None
    step_id: uuid.UUID | None
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    locked_by: str = ""


def enqueue(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    kind: str,
    queue: JobQueue,
    payload: dict[str, Any] | None = None,
    task_id: uuid.UUID | None = None,
    step_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
    priority: int = 100,
    max_attempts: int = 3,
    delay_seconds: float = 0,
    settings: Settings | None = None,
    internal: bool = False,
) -> uuid.UUID | None:
    """`internal=True` for follow-up jobs of work already admitted (continuations): they bypass
    backpressure so a full queue can never force an already-run step to run again."""
    s = settings or get_settings()
    if internal:
        return _insert(
            db, workspace_id, kind, queue, payload, task_id, step_id, dedupe_key, priority, max_attempts, delay_seconds
        )
    pending_ws = db.execute(
        select(func.count())
        .select_from(Job)
        .where(Job.workspace_id == workspace_id, Job.status == JobStatus.pending.value)
    ).scalar_one()
    if pending_ws >= s.queue_max_pending_per_workspace:
        raise QueueFull("This workspace has too much queued work right now. Try again in a few minutes.")
    pending_all = db.execute(
        select(func.count()).select_from(Job).where(Job.status == JobStatus.pending.value)
    ).scalar_one()
    if pending_all >= s.queue_max_pending_total:
        raise QueueFull("The agent is busy right now. Try again in a few minutes.")
    return _insert(
        db, workspace_id, kind, queue, payload, task_id, step_id, dedupe_key, priority, max_attempts, delay_seconds
    )


def _insert(
    db: Session,
    workspace_id: uuid.UUID,
    kind: str,
    queue: JobQueue,
    payload: dict[str, Any] | None,
    task_id: uuid.UUID | None,
    step_id: uuid.UUID | None,
    dedupe_key: str | None,
    priority: int,
    max_attempts: int,
    delay_seconds: float,
) -> uuid.UUID | None:
    stmt = (
        insert(Job)
        .values(
            workspace_id=workspace_id,
            kind=kind,
            queue=queue.value,
            payload=payload or {},
            task_id=task_id,
            step_id=step_id,
            dedupe_key=dedupe_key,
            priority=priority,
            max_attempts=max_attempts,
            run_after=utcnow() + timedelta(seconds=delay_seconds),
        )
        .on_conflict_do_nothing(constraint="uq_jobs_workspace_dedupe")
        .returning(Job.id)
    )
    job_id = db.execute(stmt).scalar_one_or_none()
    if job_id is None and dedupe_key is not None:
        job_id = db.execute(
            select(Job.id).where(Job.workspace_id == workspace_id, Job.dedupe_key == dedupe_key)
        ).scalar_one_or_none()
    return job_id


def claim(db: Session, queue: JobQueue, worker_id: str, settings: Settings | None = None) -> ClaimedJob | None:
    """Claim one due job and commit, so other workers see it as running immediately."""
    s = settings or get_settings()
    row = db.execute(
        text(
            """
            UPDATE jobs SET status = 'running', locked_by = :worker, locked_at = now(), heartbeat_at = now(),
                   attempts = attempts + 1
            WHERE id = (
              SELECT j.id FROM jobs j
              WHERE j.queue = :queue AND j.status = 'pending' AND j.run_after <= now()
                AND (SELECT count(*) FROM jobs r
                     WHERE r.workspace_id = j.workspace_id AND r.status = 'running') < :per_ws
              ORDER BY j.priority, j.run_after, j.created_at
              FOR UPDATE SKIP LOCKED
              LIMIT 1
            )
            RETURNING id, workspace_id, kind, queue, task_id, step_id, payload, attempts, max_attempts
            """
        ),
        {"worker": worker_id[:120], "queue": queue.value, "per_ws": s.queue_max_running_per_workspace},
    ).first()
    db.commit()
    if row is None:
        return None
    return ClaimedJob(
        id=row.id,
        workspace_id=row.workspace_id,
        kind=row.kind,
        queue=row.queue,
        task_id=row.task_id,
        step_id=row.step_id,
        payload=dict(row.payload or {}),
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        locked_by=worker_id[:120],
    )


def heartbeat(db: Session, job_id: uuid.UUID, worker_id: str) -> bool:
    """Returns False if the job is no longer ours (recovered or cancelled)."""
    r = db.execute(
        update(Job)
        .where(Job.id == job_id, Job.locked_by == worker_id[:120], Job.status == JobStatus.running.value)
        .values(heartbeat_at=func.now())
    )
    db.commit()
    return bool(r.rowcount)  # type: ignore[attr-defined]


def still_owned(db: Session, job: ClaimedJob) -> bool:
    """True if this worker still holds the job (not recovered/cancelled meanwhile). Locks the row."""
    row = db.execute(
        select(Job.id)
        .where(Job.id == job.id, Job.status == JobStatus.running.value, Job.locked_by == job.locked_by)
        .with_for_update()
    ).first()
    return row is not None


def complete(db: Session, job_id: uuid.UUID, worker_id: str | None = None) -> bool:
    conds = [Job.id == job_id, Job.status == JobStatus.running.value]
    if worker_id is not None:
        conds.append(Job.locked_by == worker_id[:120])
    r = db.execute(
        update(Job)
        .where(*conds)
        .values(status=JobStatus.succeeded.value, finished_at=func.now(), locked_by=None, last_error=None)
    )
    return bool(r.rowcount)  # type: ignore[attr-defined]


def backoff_seconds(attempt: int, settings: Settings | None = None) -> float:
    """Exponential backoff with full jitter."""
    s = settings or get_settings()
    ceiling = min(s.job_backoff_max_seconds, s.job_backoff_base_seconds * (2 ** max(0, attempt - 1)))
    return random.uniform(ceiling / 2, ceiling)  # noqa: S311 - jitter, not security


def fail(
    db: Session,
    job: ClaimedJob,
    error: str,
    *,
    retryable: bool,
    settings: Settings | None = None,
) -> str:
    """Record a failure. Returns the new status: pending (retry), failed or dead."""
    if retryable and job.attempts < job.max_attempts:
        status = JobStatus.pending.value
        run_after: datetime | None = utcnow() + timedelta(seconds=backoff_seconds(job.attempts, settings))
    else:
        status = JobStatus.dead.value if retryable else JobStatus.failed.value
        run_after = None
    values: dict[str, Any] = {"status": status, "last_error": error[:1000], "locked_by": None}
    if run_after is not None:
        values["run_after"] = run_after
    else:
        values["finished_at"] = func.now()
    conds = [Job.id == job.id, Job.status == JobStatus.running.value]
    if job.locked_by:
        conds.append(Job.locked_by == job.locked_by)
    r = db.execute(update(Job).where(*conds).values(**values))
    if not r.rowcount:  # type: ignore[attr-defined]
        return "lost"  # recovered or cancelled meanwhile: someone else owns it now
    return status


def recover_stale(db: Session, settings: Settings | None = None) -> int:
    """Running jobs whose worker stopped heart-beating: retry or dead-letter. Returns count."""
    s = settings or get_settings()
    cutoff = utcnow() - timedelta(seconds=s.job_lease_seconds)
    rows = (
        db.execute(
            select(Job)
            .where(Job.status == JobStatus.running.value, Job.heartbeat_at < cutoff)
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )
    for j in rows:
        if j.attempts < j.max_attempts:
            j.status = JobStatus.pending.value
            j.run_after = utcnow() + timedelta(seconds=backoff_seconds(j.attempts, s))
        else:
            j.status = JobStatus.dead.value
            j.finished_at = utcnow()
        j.last_error = f"worker {j.locked_by or '?'} stopped responding (lease expired)"
        j.locked_by = None
    db.commit()
    return len(rows)


def cancel_task_jobs(db: Session, workspace_id: uuid.UUID, task_id: uuid.UUID) -> int:
    r = db.execute(
        update(Job)
        .where(Job.workspace_id == workspace_id, Job.task_id == task_id, Job.status == JobStatus.pending.value)
        .values(status=JobStatus.cancelled.value, finished_at=func.now(), last_error="task cancelled")
    )
    return int(r.rowcount)  # type: ignore[attr-defined]


def queue_stats(db: Session, workspace_id: uuid.UUID | None = None) -> dict[str, dict[str, int]]:
    q = select(Job.queue, Job.status, func.count()).group_by(Job.queue, Job.status)
    if workspace_id is not None:
        q = q.where(Job.workspace_id == workspace_id)
    out: dict[str, dict[str, int]] = {}
    for queue, status, n in db.execute(q).tuples():
        out.setdefault(queue, {})[status] = int(n)
    return out
