"""Model → response-schema conversion helpers (always given already tenant-scoped rows)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas as S
from app.domain.enums import TaskStatus
from app.domain.task_states import allowed_actions
from app.models import (
    ApprovalRequest,
    Artifact,
    AuditEvent,
    DeletionRequest,
    FileRecord,
    Task,
    TaskAttachment,
    TaskStep,
    User,
)


def task_ref(number: int) -> str:
    return f"T-{number}"


def approval_ref(number: int) -> str:
    return f"A-{number}"


def task_summary(t: Task) -> S.TaskSummaryOut:
    return S.TaskSummaryOut(
        id=t.id,
        ref=task_ref(t.number),
        title=t.title,
        status=t.status,
        type=t.type,
        priority=t.priority,
        mode=t.mode,
        integration_key=t.integration_key,
        waiting_for=t.waiting_for,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


def step_out(s: TaskStep) -> S.TaskStepOut:
    out = dict(s.output or {})
    pol = s.policy or {}
    visible = {k: v for k, v in out.items() if not k.startswith("_")} if out else None
    return S.TaskStepOut(
        id=s.id,
        position=s.position,
        title=s.title,
        description=s.description,
        tool=s.tool,
        risk=s.risk,
        requires_approval=s.requires_approval,
        state=s.state,
        selected=s.selected,
        started_at=s.started_at,
        finished_at=s.finished_at,
        step_key=s.step_key or f"s{s.position}",
        tool_id=s.tool_id,
        impact=s.impact,
        classifications=list(s.classifications or []),
        destinations=list(s.destinations or []),
        policy=S.StepPolicyOut(
            outcome=pol["outcome"],
            reasons=list(pol.get("reasons", [])),
            data_leaves=bool(pol.get("data_leaves")),
            classification=str(pol.get("classification", "")),
            version=str(pol.get("version", "")),
        )
        if pol.get("outcome")
        else None,
        output_summary=out.get("_summary"),
        output=visible,
        error=s.error,
        approval_id=s.approval_id,
        attempts=s.attempts,
        artifact_id=uuid.UUID(out["_artifact_id"]) if out.get("_artifact_id") else None,
    )


def task_full(db: Session, t: Task) -> S.TaskOut:
    steps = (
        db.execute(
            select(TaskStep)
            .where(
                TaskStep.workspace_id == t.workspace_id,
                TaskStep.task_id == t.id,
                TaskStep.plan_version == max(t.plan_version, 1),
            )
            .order_by(TaskStep.position)
        )
        .scalars()
        .all()
    )
    atts = db.execute(
        select(FileRecord.id, FileRecord.original_name)
        .join(
            TaskAttachment,
            (TaskAttachment.file_id == FileRecord.id) & (TaskAttachment.workspace_id == FileRecord.workspace_id),
        )
        .where(TaskAttachment.workspace_id == t.workspace_id, TaskAttachment.task_id == t.id)
        .order_by(FileRecord.original_name)
    ).all()
    plan = None
    if steps:
        meta = t.plan_meta or {}
        plan = S.TaskPlanOut(
            steps=[step_out(s) for s in steps],
            data_sources=list(meta.get("data_sources", [])),
            destination=meta.get("destination"),
            version=max(t.plan_version, 1),
            summary=t.plan_summary,
            provider=meta.get("provider"),
            provider_location=meta.get("provider_location"),
        )
    report = S.TaskReportOut(**t.report) if t.report else None
    arts = db.execute(
        select(Artifact)
        .where(Artifact.workspace_id == t.workspace_id, Artifact.task_id == t.id)
        .order_by(Artifact.created_at)
    ).scalars()
    base = task_summary(t).model_dump()
    return S.TaskOut(
        **base,
        prompt=t.prompt,
        question=t.question,
        error_message=t.error_message,
        attachments=[S.TaskAttachmentOut(file_id=a[0], name=a[1]) for a in atts],
        plan=plan,
        report=report,
        allowed_actions=allowed_actions(TaskStatus(t.status), has_plan=plan is not None),
        data_classification=t.data_classification,
        started_at=t.started_at,
        finished_at=t.finished_at,
        artifacts=[
            S.TaskArtifactOut(
                id=a.id,
                name=a.name,
                kind=a.kind,
                provenance=a.provenance,
                size_bytes=a.size_bytes,
                created_at=a.created_at,
            )
            for a in arts
        ],
    )


def task_refs(db: Session, workspace_id: uuid.UUID, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = db.execute(select(Task.id, Task.number).where(Task.workspace_id == workspace_id, Task.id.in_(wanted))).all()
    return {r[0]: task_ref(r[1]) for r in rows}


def approval_out(a: ApprovalRequest, refs: dict[uuid.UUID, str]) -> S.ApprovalOut:
    return S.ApprovalOut(
        id=a.id,
        ref=approval_ref(a.number),
        category=a.category,
        title=a.title,
        task_id=a.task_id,
        task_ref=refs.get(a.task_id) if a.task_id else None,
        reason=a.reason,
        affected_items=list(a.affected_items),
        data_leaves_workspace=a.data_leaves_workspace,
        destination=a.destination,
        scope_summary=a.scope_summary,
        consequences=a.consequences,
        reversible=a.reversible,
        risk=a.risk,
        status=a.status,
        requested_at=a.requested_at,
        expires_at=a.expires_at,
        decided_at=a.decided_at,
        decision_note=a.decision_note,
        execution_state=a.execution_state,
        operation=a.operation,
        targets=list(a.targets or []),
        policy_version=a.policy_version,
        step_id=a.step_id,
    )


def approvals_out(db: Session, workspace_id: uuid.UUID, rows: list[ApprovalRequest]) -> list[S.ApprovalOut]:
    refs = task_refs(db, workspace_id, (a.task_id for a in rows))
    return [approval_out(a, refs) for a in rows]


def files_out(db: Session, workspace_id: uuid.UUID, rows: list[FileRecord]) -> list[S.FileOut]:
    ids = [f.id for f in rows]
    pending: set[uuid.UUID] = set()
    if ids:
        pending = set(
            db.execute(
                select(DeletionRequest.target_id).where(
                    DeletionRequest.workspace_id == workspace_id,
                    DeletionRequest.target_type == "file",
                    DeletionRequest.target_id.in_(ids),
                    DeletionRequest.status.in_(("pending_approval", "approved_blocked", "approved")),
                )
            ).scalars()
        )
    return [
        S.FileOut(
            id=f.id,
            name=f.original_name,
            type_label=f.type_label,
            content_type=f.content_type,
            size_bytes=f.size_bytes,
            status=f.status,
            classification=f.classification,
            collection=f.collection,
            uploaded_at=f.created_at,
            error_message=f.error_message,
            scan_status=f.scan_status,
            deletion_requested=f.id in pending,
            deleted_at=f.deleted_at,
            restorable_until=f.purge_after,
        )
        for f in rows
    ]


def activity_out(db: Session, workspace_id: uuid.UUID, rows: list[AuditEvent]) -> list[S.ActivityOut]:
    refs = task_refs(db, workspace_id, (r.task_id for r in rows))
    actor_ids = {r.actor_user_id for r in rows if r.actor_user_id}
    names: dict[uuid.UUID, str] = {}
    if actor_ids:
        names = {u.id: u.name for u in db.execute(select(User).where(User.id.in_(actor_ids))).scalars()}
    return [
        S.ActivityOut(
            id=r.id,
            created_at=r.created_at,
            type=r.category,
            action=r.action,
            message=r.message,
            task_id=r.task_id,
            task_ref=refs.get(r.task_id) if r.task_id else None,
            actor=names.get(r.actor_user_id) if r.actor_user_id else None,
        )
        for r in rows
    ]
