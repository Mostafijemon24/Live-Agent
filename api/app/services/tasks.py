"""Task use cases. Every query is scoped to ctx.workspace.id."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app import schemas as S
from app.adapters.phase2 import OutboxJobQueue, planner
from app.core.config import get_settings
from app.core.db import utcnow
from app.core.deps import Context
from app.core.errors import ApiError
from app.domain.enums import FileStatus, TaskStatus, WaitingFor
from app.domain.task_states import assert_transition, require_action
from app.models import FileRecord, Task, TaskAttachment, TaskEvent, TaskStep, Workspace
from app.services.usage import bump_usage, current_period, usage_value
from app.services.views import task_full, task_ref

KNOWN_INTEGRATIONS = {"wordpress", "notion", "cloud_storage", "email", "browser", "ai_provider"}


def _next_number(db: Session, ws_id: uuid.UUID, column: str) -> int:
    col = getattr(Workspace, column)
    return int(
        db.execute(update(Workspace).where(Workspace.id == ws_id).values({column: col + 1}).returning(col)).scalar_one()
    )


def get_task(ctx: Context, task_id: uuid.UUID, *, lock: bool = False) -> Task:
    q = select(Task).where(Task.workspace_id == ctx.workspace.id, Task.id == task_id)
    if lock:
        q = q.with_for_update()
    t = ctx.db.execute(q).scalar_one_or_none()
    if t is None:
        raise ctx.deny("task", task_id, "task")
    return t


def add_event(
    ctx: Context,
    t: Task,
    kind: str,
    message: str,
    level: str = "info",
    from_status: str | None = None,
    to_status: str | None = None,
) -> None:
    ctx.db.add(
        TaskEvent(
            workspace_id=t.workspace_id,
            task_id=t.id,
            kind=kind,
            message=message,
            level=level,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=ctx.user.id,
        )
    )


def transition(ctx: Context, t: Task, dst: TaskStatus, reason: str, waiting_for: WaitingFor | None = None) -> None:
    src = TaskStatus(t.status)
    assert_transition(src, dst)
    t.status = dst.value
    t.waiting_for = waiting_for.value if waiting_for else None
    t.updated_at = utcnow()
    add_event(ctx, t, "task.status_changed", reason, "info", src.value, dst.value)
    ctx.log(
        "task.status_changed",
        "task",
        f"{task_ref(t.number)}: {reason}",
        target_type="task",
        target_id=str(t.id),
        task_id=t.id,
        metadata={"from": src.value, "to": dst.value},
    )


def create_task(ctx: Context, body: S.CreateTaskIn, idempotency_key: str | None) -> tuple[S.TaskOut, bool]:
    db = ctx.db
    if idempotency_key:
        existing = db.execute(
            select(Task).where(Task.workspace_id == ctx.workspace.id, Task.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        if existing is not None:
            return task_full(db, existing), False

    if body.integration_key is not None and body.integration_key not in KNOWN_INTEGRATIONS:
        raise ApiError(
            422,
            "validation_error",
            "Some fields need attention.",
            details=[{"field": "integration_key", "message": "Unknown integration."}],
        )
    if body.integration_key is not None:
        raise ApiError(
            422,
            "integration_not_connected",
            "That integration is not connected. Connections arrive with the Phase 3 integration service.",
            details=[{"field": "integration_key", "message": "Not connected."}],
        )

    quota = get_settings().monthly_task_quota
    if usage_value(db, ctx.workspace.id, current_period(), "tasks_created") >= quota:
        raise ApiError(429, "quota_exceeded", f"This workspace has reached its limit of {quota} tasks this month.")

    file_ids = list(dict.fromkeys(body.attachment_file_ids))
    if file_ids:
        files = (
            db.execute(
                select(FileRecord).where(FileRecord.workspace_id == ctx.workspace.id, FileRecord.id.in_(file_ids))
            )
            .scalars()
            .all()
        )
        found = {f.id: f for f in files}
        for fid in file_ids:
            if fid not in found:
                raise ctx.deny("file", fid, "file")
        not_usable = [
            f.original_name for f in files if f.status not in (FileStatus.ready.value, FileStatus.unscanned.value)
        ]
        if not_usable:
            raise ApiError(422, "file_not_ready", f"These files can't be attached yet: {', '.join(not_usable)[:300]}")

    title = (body.title or "").strip() or _suggest_title(body.prompt)
    number = _next_number(db, ctx.workspace.id, "task_seq")
    planner_ready = planner.is_available()
    t = Task(
        workspace_id=ctx.workspace.id,
        number=number,
        title=title[:200],
        prompt=body.prompt.strip(),
        status=TaskStatus.queued.value,
        type=body.type.value,
        priority=body.priority.value,
        mode=body.mode.value,
        integration_key=None,
        waiting_for=None if planner_ready else WaitingFor.planning_service.value,
        idempotency_key=idempotency_key,
        created_by=ctx.user.id,
    )
    db.add(t)
    try:
        db.flush()
    except IntegrityError:
        # A concurrent request with the same idempotency key won the race.
        db.rollback()
        raise ApiError(409, "duplicate_request", "This task was already submitted. Refresh to see it.") from None
    for fid in file_ids:
        db.add(TaskAttachment(workspace_id=ctx.workspace.id, task_id=t.id, file_id=fid))
    add_event(ctx, t, "task.created", f"Task created by {ctx.user.name}")
    queue_result = OutboxJobQueue(db).enqueue(
        workspace_id=ctx.workspace.id,
        kind="task.plan",
        task_id=t.id,
        payload={"mode": t.mode},
        dedupe_key=f"plan:{t.id}",
    )
    if not planner_ready:
        add_event(
            ctx,
            t,
            "task.waiting",
            "Waiting for the planning service — it is not installed yet (Phase 3). Nothing has run.",
            "warn",
        )
    ctx.log(
        "task.created",
        "task",
        f"Task {task_ref(number)} created" + ("" if planner_ready else " — waiting for the planning service"),
        target_type="task",
        target_id=str(t.id),
        task_id=t.id,
        metadata={
            "type": t.type,
            "mode": t.mode,
            "attachments": len(file_ids),
            "job_dispatched": queue_result.dispatched,
        },
    )
    bump_usage(db, ctx.workspace.id, "tasks_created", 1)
    db.flush()
    return task_full(db, t), True


def _suggest_title(prompt: str) -> str:
    import re

    words = re.sub(r"[^\w\s&'-]", "", prompt).split()
    t = " ".join(words[:7])
    return (t[:1].upper() + t[1:] + ("…" if len(words) > 7 else "")) or "Untitled task"


def list_tasks(
    ctx: Context,
    q: str | None,
    status: TaskStatus | None,
    type_: str | None,
    created: str | None,
    integration: str | None,
    sort: str,
    page: int,
    page_size: int,
) -> S.Page[S.TaskSummaryOut]:
    from app.services.views import task_summary

    conds: list[ColumnElement[bool]] = [Task.workspace_id == ctx.workspace.id]
    if q:
        like = f"%{q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')}%"
        ref_num = q.upper().removeprefix("T-")
        ors: list[ColumnElement[bool]] = [Task.title.ilike(like, escape="\\"), Task.prompt.ilike(like, escape="\\")]
        if ref_num.isdigit():
            ors.append(Task.number == int(ref_num))
        conds.append(or_(*ors))
    if status:
        conds.append(Task.status == status.value)
    if type_:
        conds.append(Task.type == type_)
    if created == "today":
        conds.append(Task.created_at >= utcnow().replace(hour=0, minute=0, second=0, microsecond=0))
    elif created == "3d":
        conds.append(Task.created_at >= utcnow() - timedelta(days=3))
    if integration == "none":
        conds.append(Task.integration_key.is_(None))
    elif integration:
        conds.append(Task.integration_key == integration)
    order = (
        Task.title.asc() if sort == "title" else Task.created_at.desc() if sort == "created" else Task.updated_at.desc()
    )
    total = ctx.db.execute(select(func.count()).select_from(Task).where(*conds)).scalar_one()
    rows = (
        ctx.db.execute(
            select(Task)
            .where(*conds)
            .order_by(order, Task.number.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return S.Page[S.TaskSummaryOut](items=[task_summary(t) for t in rows], page=page, page_size=page_size, total=total)


def cancel(ctx: Context, task_id: uuid.UUID, reason: str | None) -> S.TaskOut:
    t = get_task(ctx, task_id, lock=True)
    require_action(TaskStatus(t.status), "cancel", has_plan=True)
    transition(ctx, t, TaskStatus.cancelled, "Cancelled by " + ctx.user.name + (f": {reason}" if reason else ""))
    ctx.db.execute(
        update(TaskStep)
        .where(
            TaskStep.workspace_id == ctx.workspace.id,
            TaskStep.task_id == t.id,
            TaskStep.state.in_(("not_started", "in_progress", "paused", "waiting_for_input")),
        )
        .values(state="cancelled")
    )
    return task_full(ctx.db, t)


def pause(ctx: Context, task_id: uuid.UUID) -> S.TaskOut:
    t = get_task(ctx, task_id, lock=True)
    require_action(TaskStatus(t.status), "pause")
    transition(ctx, t, TaskStatus.paused, f"Paused by {ctx.user.name}")
    return task_full(ctx.db, t)


def resume(ctx: Context, task_id: uuid.UUID) -> S.TaskOut:
    t = get_task(ctx, task_id, lock=True)
    require_action(TaskStatus(t.status), "resume")
    # No execution engine: the task goes back to the queue instead of pretending to run.
    transition(
        ctx,
        t,
        TaskStatus.queued,
        f"Resumed by {ctx.user.name} — waiting for the execution engine",
        WaitingFor.execution_engine,
    )
    return task_full(ctx.db, t)


def message(ctx: Context, task_id: uuid.UUID, text: str, kind: str) -> S.TaskOut:
    t = get_task(ctx, task_id, lock=True)
    status = TaskStatus(t.status)
    has_plan = (
        ctx.db.execute(
            select(func.count())
            .select_from(TaskStep)
            .where(TaskStep.workspace_id == ctx.workspace.id, TaskStep.task_id == t.id)
        ).scalar_one()
        > 0
    )
    if kind == "answer":
        require_action(status, "answer", has_plan)
        add_event(ctx, t, "task.message", f"Your answer: {text}", "note")
        t.question = None
        transition(
            ctx, t, TaskStatus.queued, "Answer received — waiting for the execution engine", WaitingFor.execution_engine
        )
    elif kind == "plan_change":
        require_action(status, "revise_plan", has_plan)
        add_event(ctx, t, "task.message", f"Plan change requested: {text}", "note")
        # The planner would revise the plan; without it, the request is recorded and the task waits.
        transition(
            ctx,
            t,
            TaskStatus.queued,
            "Plan change requested — waiting for the planning service",
            WaitingFor.planning_service,
        )
    else:
        if status in (TaskStatus.completed, TaskStatus.cancelled, TaskStatus.failed, TaskStatus.partially_completed):
            raise ApiError(409, "action_not_allowed", "This task is finished, so questions can't be added.")
        add_event(ctx, t, "task.message", f"Question from you: {text}", "note")
        t.updated_at = utcnow()
        ctx.log(
            "task.message",
            "task",
            f"{task_ref(t.number)}: question added",
            target_type="task",
            target_id=str(t.id),
            task_id=t.id,
        )
    return task_full(ctx.db, t)


def approve_plan(ctx: Context, task_id: uuid.UUID, selected: list[uuid.UUID]) -> S.TaskOut:
    t = get_task(ctx, task_id, lock=True)
    steps = (
        ctx.db.execute(select(TaskStep).where(TaskStep.workspace_id == ctx.workspace.id, TaskStep.task_id == t.id))
        .scalars()
        .all()
    )
    require_action(TaskStatus(t.status), "approve_plan", has_plan=bool(steps))
    ids = {s.id for s in steps}
    sel = set(selected)
    if not sel or not sel <= ids:
        raise ApiError(
            422,
            "validation_error",
            "Select at least one step from this plan.",
            details=[{"field": "selected_step_ids", "message": "Select steps from this plan."}],
        )
    for s in steps:
        s.selected = s.id in sel
        if not s.selected:
            s.state = "skipped"
    ctx.log(
        "plan.approved",
        "plan",
        f"Plan for {task_ref(t.number)} approved ({len(sel)} of {len(steps)} steps)",
        target_type="task",
        target_id=str(t.id),
        task_id=t.id,
    )
    transition(
        ctx, t, TaskStatus.queued, "Plan approved — waiting for the execution engine", WaitingFor.execution_engine
    )
    OutboxJobQueue(ctx.db).enqueue(
        workspace_id=ctx.workspace.id,
        kind="task.execute",
        task_id=t.id,
        payload={"steps": [str(i) for i in sel]},
        dedupe_key=f"exec:{t.id}",
    )
    return task_full(ctx.db, t)


def reject_plan(ctx: Context, task_id: uuid.UUID, note: str | None) -> S.TaskOut:
    t = get_task(ctx, task_id, lock=True)
    has = (
        ctx.db.execute(
            select(func.count())
            .select_from(TaskStep)
            .where(TaskStep.workspace_id == ctx.workspace.id, TaskStep.task_id == t.id)
        ).scalar_one()
        > 0
    )
    require_action(TaskStatus(t.status), "reject_plan", has_plan=has)
    ctx.log(
        "plan.rejected",
        "plan",
        f"Plan for {task_ref(t.number)} rejected" + (f": {note}" if note else ""),
        target_type="task",
        target_id=str(t.id),
        task_id=t.id,
    )
    transition(ctx, t, TaskStatus.cancelled, "Plan rejected — nothing ran")
    return task_full(ctx.db, t)


def list_events(ctx: Context, task_id: uuid.UUID, page: int, page_size: int) -> S.Page[S.TaskEventOut]:
    get_task(ctx, task_id)
    conds = [TaskEvent.workspace_id == ctx.workspace.id, TaskEvent.task_id == task_id]
    total = ctx.db.execute(select(func.count()).select_from(TaskEvent).where(*conds)).scalar_one()
    rows = (
        ctx.db.execute(
            select(TaskEvent)
            .where(*conds)
            .order_by(TaskEvent.created_at, TaskEvent.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return S.Page[S.TaskEventOut](
        items=[S.TaskEventOut.model_validate(e) for e in rows], page=page, page_size=page_size, total=total
    )
