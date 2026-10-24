"""Approval requests, decisions and deletion requests.

An approval is one-time and bound to the exact operation: workspace, task step, tool/workflow,
canonical argument hash, targets, displayed details, expiry and policy version, all signed with
HMAC (`payload_hash`). Approving never executes anything here: it marks the approval
`pending_execution` and queues the job. The worker re-verifies the binding (`verify_binding`)
immediately before running and refuses if anything changed.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import schemas as S
from app.core.config import get_settings
from app.core.db import utcnow
from app.core.deps import Context
from app.core.errors import ApiError
from app.domain.enums import (
    ApprovalCategory,
    ApprovalDecisionKind,
    ApprovalStatus,
    DeletionRequestStatus,
    ExecutionState,
    RiskLevel,
    WorkspaceRole,
)
from app.models import (
    ApprovalDecision,
    ApprovalRequest,
    AuditEvent,
    DeletionRequest,
    FileRecord,
    Notification,
    Workspace,
    WorkspaceMembership,
)
from app.services.audit import scrub
from app.services.views import approval_ref, approvals_out


def payload_hash(a: ApprovalRequest, extra: dict[str, str]) -> str:
    """Keyed signature (HMAC-SHA256) over everything the approver is shown, plus identity fields.

    The key comes from APPROVAL_SIGNING_KEY (application config), which the database role cannot
    read, so changing any displayed field — or recomputing the value without the key — breaks it.
    """
    canonical = json.dumps(
        {
            "workspace": str(a.workspace_id),
            "number": a.number,
            "category": a.category,
            "title": a.title,
            "task": str(a.task_id) if a.task_id else None,
            "reason": a.reason,
            "affected": list(a.affected_items),
            "leaves": bool(a.data_leaves_workspace),
            "destination": a.destination,
            "scope": a.scope_summary,
            "consequences": a.consequences,
            "reversible": a.reversible,
            "risk": a.risk,
            "expires": a.expires_at.isoformat() if a.expires_at else None,
            # Phase 3 binding fields (absent on Phase 2 approvals, so their signatures stay valid).
            **(
                {
                    "step": str(a.step_id) if a.step_id else None,
                    "operation": a.operation,
                    "args_hash": a.args_hash,
                    "targets": sorted(a.targets or []),
                    "policy_version": a.policy_version,
                }
                if a.operation
                else {}
            ),
            **extra,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    key = get_settings().approval_signing_key.get_secret_value().encode()
    return hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()


def _next_approval_number(db: Session, workspace_id: uuid.UUID) -> int:
    return int(
        db.execute(
            update(Workspace)
            .where(Workspace.id == workspace_id)
            .values(approval_seq=Workspace.approval_seq + 1)
            .returning(Workspace.approval_seq)
        ).scalar_one()
    )


def _audit(
    db: Session,
    workspace_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action: str,
    message: str,
    *,
    target_type: str | None = None,
    target_id: str | None = None,
    task_id: uuid.UUID | None = None,
    ip: str | None = None,
    request_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    db.add(
        AuditEvent(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=action,
            category="approval" if action.startswith("approval") else "file" if action.startswith("file") else "task",
            message=message[:1000],
            target_type=target_type,
            target_id=target_id,
            task_id=task_id,
            ip=ip,
            request_id=request_id,
            meta=scrub(metadata or {}),
        )
    )


def new_approval(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    requested_by: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    category: ApprovalCategory,
    title: str,
    reason: str,
    affected: list[str],
    leaves: bool,
    destination: str,
    scope_summary: str,
    consequences: str,
    reversible: str,
    risk: RiskLevel,
    task_id: uuid.UUID | None = None,
    step_id: uuid.UUID | None = None,
    operation: str | None = None,
    args_hash: str | None = None,
    targets: list[str] | None = None,
    policy_version: str | None = None,
    expires_in: timedelta | None = timedelta(hours=24),
    extra_hash: dict[str, str] | None = None,
    ip: str | None = None,
    request_id: str | None = None,
) -> ApprovalRequest:
    """Create a signed approval request. Usable from the API and from workers (no request context)."""
    a = ApprovalRequest(
        workspace_id=workspace_id,
        number=_next_approval_number(db, workspace_id),
        category=category.value,
        title=title[:300],
        task_id=task_id,
        reason=reason,
        affected_items=affected,
        data_leaves_workspace=leaves,
        destination=destination,
        scope_summary=scope_summary,
        consequences=consequences,
        reversible=reversible,
        risk=risk.value,
        payload_hash="",
        requested_by=requested_by,
        expires_at=(utcnow() + expires_in) if expires_in else None,
        step_id=step_id,
        operation=operation,
        args_hash=args_hash,
        targets=sorted(targets or []),
        policy_version=policy_version,
    )
    a.payload_hash = payload_hash(a, extra_hash or {})
    db.add(a)
    db.flush()
    db.add(
        Notification(
            workspace_id=workspace_id,
            user_id=requested_by,
            type="Approval requested",
            icon="hourglass",
            text=f"{approval_ref(a.number)}: {title}"[:300],
            target={"route": f"/approvals?id={a.id}", "id": str(a.id)},
        )
    )
    _audit(
        db,
        workspace_id,
        actor_user_id,
        "approval.requested",
        f"{approval_ref(a.number)} requested{' by the agent' if actor_user_id is None else ''}: {title}",
        target_type="approval",
        target_id=str(a.id),
        task_id=task_id,
        ip=ip,
        request_id=request_id,
        metadata={"category": category.value, "operation": operation},
    )
    db.flush()
    return a


def create_approval(
    ctx: Context,
    *,
    category: ApprovalCategory,
    title: str,
    reason: str,
    affected: list[str],
    leaves: bool,
    destination: str,
    scope_summary: str,
    consequences: str,
    reversible: str,
    risk: RiskLevel,
    task_id: uuid.UUID | None = None,
    expires_in: timedelta | None = timedelta(hours=24),
    extra_hash: dict[str, str] | None = None,
) -> ApprovalRequest:
    return new_approval(
        ctx.db,
        workspace_id=ctx.workspace.id,
        requested_by=ctx.user.id,
        actor_user_id=ctx.user.id,
        category=category,
        title=title,
        reason=reason,
        affected=affected,
        leaves=leaves,
        destination=destination,
        scope_summary=scope_summary,
        consequences=consequences,
        reversible=reversible,
        risk=risk,
        task_id=task_id,
        expires_in=expires_in,
        extra_hash=extra_hash,
        ip=ctx.ip,
        request_id=ctx.request_id,
    )


def verify_binding(
    db: Session,
    a: ApprovalRequest,
    *,
    workspace_id: uuid.UUID,
    operation: str,
    args_hash: str | None,
    targets: list[str],
    step_id: uuid.UUID | None,
    policy_version: str,
    extra_hash: dict[str, str] | None = None,
) -> str | None:
    """Re-check an approval right before execution. Returns None if valid, else the reason."""
    now = utcnow()
    if a.workspace_id != workspace_id:
        return "approval belongs to another workspace"
    if a.status != ApprovalStatus.approved.value:
        return f"approval is {a.status}"
    if a.execution_state != ExecutionState.pending_execution.value:
        return "approval was already used or invalidated"
    if a.operation != operation:
        return "operation changed after approval"
    if (a.args_hash or None) != (args_hash or None):
        return "arguments changed after approval"
    if sorted(a.targets or []) != sorted(targets):
        return "targets changed after approval"
    if step_id is not None and a.step_id != step_id:
        return "approval is for a different step"
    if a.policy_version != policy_version:
        return "the policy changed after approval"
    if a.expires_at is not None and now > a.expires_at:
        return "approval expired before it could be used"
    if not hmac.compare_digest(payload_hash(a, extra_hash or {}), a.payload_hash):
        return "approval signature does not match the stored request"
    decision = db.execute(
        select(ApprovalDecision)
        .where(ApprovalDecision.workspace_id == workspace_id, ApprovalDecision.approval_id == a.id)
        .order_by(ApprovalDecision.decided_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if decision is None or decision.decision != ApprovalDecisionKind.approve.value:
        return "no approval decision recorded"
    if decision.payload_hash != a.payload_hash or decision.decided_by != a.decided_by:
        return "the recorded decision does not match the request"
    role = db.execute(
        select(WorkspaceMembership.role).where(
            WorkspaceMembership.workspace_id == workspace_id, WorkspaceMembership.user_id == decision.decided_by
        )
    ).scalar_one_or_none()
    if role not in (WorkspaceRole.owner.value, WorkspaceRole.admin.value):
        return "the approver is no longer an owner or admin of this workspace"
    return None


def _expire_overdue(ctx: Context) -> None:
    now = utcnow()
    rows = (
        ctx.db.execute(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.workspace_id == ctx.workspace.id,
                ApprovalRequest.status == ApprovalStatus.pending.value,
                ApprovalRequest.expires_at.is_not(None),
                ApprovalRequest.expires_at <= now,
            )
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )
    for a in rows:
        a.status = ApprovalStatus.expired.value
        a.updated_at = now
        ctx.log(
            "approval.expired",
            "approval",
            f"{approval_ref(a.number)} expired without a decision",
            target_type="approval",
            target_id=str(a.id),
        )


def list_approvals(ctx: Context, status: str, page: int, page_size: int) -> S.ApprovalPage:
    _expire_overdue(ctx)
    conds = [ApprovalRequest.workspace_id == ctx.workspace.id]
    if status == "pending":
        conds.append(ApprovalRequest.status == "pending")
    elif status == "decided":
        conds.append(ApprovalRequest.status != "pending")
    total = ctx.db.execute(select(func.count()).select_from(ApprovalRequest).where(*conds)).scalar_one()
    pending = ctx.db.execute(
        select(func.count())
        .select_from(ApprovalRequest)
        .where(ApprovalRequest.workspace_id == ctx.workspace.id, ApprovalRequest.status == "pending")
    ).scalar_one()
    rows = list(
        ctx.db.execute(
            select(ApprovalRequest)
            .where(*conds)
            .order_by(ApprovalRequest.requested_at.desc(), ApprovalRequest.number.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars()
    )
    return S.ApprovalPage(
        items=approvals_out(ctx.db, ctx.workspace.id, rows),
        page=page,
        page_size=page_size,
        total=total,
        pending_count=pending,
    )


def get_approval(ctx: Context, approval_id: uuid.UUID, lock: bool = False) -> ApprovalRequest:
    q = select(ApprovalRequest).where(
        ApprovalRequest.workspace_id == ctx.workspace.id, ApprovalRequest.id == approval_id
    )
    if lock:
        q = q.with_for_update()
    a = ctx.db.execute(q).scalar_one_or_none()
    if a is None:
        raise ctx.deny("approval", approval_id, "approval request")
    return a


def decide(ctx: Context, approval_id: uuid.UUID, body: S.DecisionIn) -> S.ApprovalOut:
    if ctx.role not in (WorkspaceRole.owner, WorkspaceRole.admin):
        ctx.require_role(WorkspaceRole.owner, WorkspaceRole.admin)
    a = get_approval(ctx, approval_id, lock=True)
    now = utcnow()
    if a.status == ApprovalStatus.pending.value and a.expires_at is not None and a.expires_at <= now:
        a.status = ApprovalStatus.expired.value
        ctx.log(
            "approval.expired",
            "approval",
            f"{approval_ref(a.number)} expired without a decision",
            target_type="approval",
            target_id=str(a.id),
        )
        ctx.db.commit()
        raise ApiError(409, "approval_expired", "This request has expired. The action needs a new approval request.")
    if a.status != ApprovalStatus.pending.value:
        raise ApiError(
            409,
            "approval_already_decided",
            "This request was already decided. Any change needs a new approval request.",
        )
    # The stored hash must still match the stored action (guards against tampering with the row).
    expected = payload_hash(a, _extra_for(ctx, a))
    if not hmac.compare_digest(expected, a.payload_hash):
        raise ApiError(
            409,
            "approval_payload_changed",
            "The requested action changed after it was requested. It needs a new approval.",
        )

    kind = body.decision
    note = (body.note or "").strip() or None
    if kind == ApprovalDecisionKind.approve:
        if not body.acknowledged:
            raise ApiError(
                422,
                "acknowledgement_required",
                "Confirm that you understand what this approval covers.",
                details=[{"field": "acknowledged", "message": "Required to approve."}],
            )
        if a.category == ApprovalCategory.record_deletion.value and sorted(body.confirmed_items or []) != sorted(
            a.affected_items
        ):
            raise ApiError(
                422,
                "confirmation_mismatch",
                "Confirm the exact list of items to be deleted.",
                details=[{"field": "confirmed_items", "message": "Must match the listed items exactly."}],
            )
        a.status = ApprovalStatus.approved.value
        # Approval never executes here: the worker re-verifies the binding and then runs it once.
        a.execution_state = ExecutionState.pending_execution.value if a.operation else ExecutionState.not_executed.value
    elif kind == ApprovalDecisionKind.reject:
        a.status = ApprovalStatus.rejected.value
    else:
        if not note:
            raise ApiError(
                422,
                "validation_error",
                "Describe the change you need first.",
                details=[{"field": "note", "message": "Describe the change you need."}],
            )
        a.status = ApprovalStatus.changes_requested.value
    a.decided_at = now
    a.decision_note = note
    a.decided_by = ctx.user.id
    a.updated_at = now
    ctx.db.add(
        ApprovalDecision(
            workspace_id=ctx.workspace.id,
            approval_id=a.id,
            decision=kind.value,
            note=note,
            payload_hash=a.payload_hash,
            decided_by=ctx.user.id,
        )
    )

    dr = ctx.db.execute(
        select(DeletionRequest).where(
            DeletionRequest.workspace_id == ctx.workspace.id, DeletionRequest.approval_id == a.id
        )
    ).scalar_one_or_none()
    if dr is not None:
        legacy = not a.operation  # Phase 2 requests stay blocked; they can't be executed
        dr.status = {
            ApprovalDecisionKind.approve: DeletionRequestStatus.approved_blocked
            if legacy
            else DeletionRequestStatus.approved,
            ApprovalDecisionKind.reject: DeletionRequestStatus.rejected,
            ApprovalDecisionKind.request_changes: DeletionRequestStatus.changes_requested,
        }[kind].value
        dr.updated_at = now

    verb = {
        "approve": "approved (one-time)" if a.operation else "approved — nothing to execute",
        "reject": "rejected",
        "request_changes": "changes requested",
    }[kind.value]
    ctx.log(
        f"approval.{kind.value}",
        "approval",
        f"{approval_ref(a.number)} {verb}: {a.title}",
        target_type="approval",
        target_id=str(a.id),
        task_id=a.task_id,
        metadata={"category": a.category, "operation": a.operation, "policy_version": a.policy_version},
    )
    ctx.db.flush()
    from app.services.agent import on_approval_decided

    on_approval_decided(ctx, a, kind, note, dr)
    ctx.db.flush()
    return approvals_out(ctx.db, ctx.workspace.id, [a])[0]


def deletion_extra(dr: DeletionRequest) -> dict[str, str]:
    extra = {"target": f"{dr.target_type}:{dr.target_id}"}
    first = (dr.expected_affected or [{}])[0]
    if isinstance(first, dict) and first.get("sha256"):
        extra["target_sha256"] = str(first["sha256"])
    return extra


def _extra_for(ctx: Context, a: ApprovalRequest) -> dict[str, str]:
    dr = ctx.db.execute(
        select(DeletionRequest).where(
            DeletionRequest.workspace_id == ctx.workspace.id, DeletionRequest.approval_id == a.id
        )
    ).scalar_one_or_none()
    return deletion_extra(dr) if dr else {}


OPEN_DELETION_STATES = ("pending_approval", "approved_blocked", "approved")


def file_deletion_request(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    requested_by: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    file_id: uuid.UUID,
    reason: str,
    requester_label: str = "the agent",
    task_id: uuid.UUID | None = None,
    ip: str | None = None,
    request_id: str | None = None,
) -> ApprovalRequest:
    """Deletion preview + request + one-time approval. Never deletes anything."""
    from app.engine.canonical import args_hash
    from app.engine.policy import POLICY_VERSION

    f = db.execute(
        select(FileRecord).where(FileRecord.workspace_id == workspace_id, FileRecord.id == file_id)
    ).scalar_one_or_none()
    if f is None or f.deleted_at is not None:
        raise ApiError(404, "not_found", "That file was not found in your workspace.")
    open_req = db.execute(
        select(DeletionRequest.id).where(
            DeletionRequest.workspace_id == workspace_id,
            DeletionRequest.target_type == "file",
            DeletionRequest.target_id == f.id,
            DeletionRequest.status.in_(OPEN_DELETION_STATES),
        )
    ).first()
    if open_req:
        raise ApiError(409, "deletion_already_requested", "A deletion request for this file already exists.")
    settings = get_settings()
    size_mb = f"{f.size_bytes / (1024 * 1024):.1f} MB"
    preview = {"type": "file", "id": str(f.id), "name": f.original_name, "size_bytes": f.size_bytes, "sha256": f.sha256}
    bound_args = {"file_id": str(f.id), "sha256": f.sha256, "size_bytes": f.size_bytes}
    target = f"file:{f.id}"
    a = new_approval(
        db,
        workspace_id=workspace_id,
        requested_by=requested_by,
        actor_user_id=actor_user_id,
        category=ApprovalCategory.record_deletion,
        title=f"Delete 1 file: {f.original_name}",
        reason=f"Requested by {requester_label}: {reason}",
        affected=[f.original_name],
        leaves=False,
        destination="Workspace file storage",
        scope_summary=f"1 file · {size_mb}",
        consequences="Tasks will no longer be able to read this file and it disappears from Files. "
        "The deletion service re-checks the file right before deleting and refuses if it changed.",
        reversible=f"Recoverable for {settings.deletion_retention_days} days (an owner or admin can restore it), "
        "then permanently removed.",
        risk=RiskLevel.high,
        task_id=task_id,
        operation="deletion.execute",
        args_hash=args_hash("deletion.execute", bound_args),
        targets=[target],
        policy_version=POLICY_VERSION,
        extra_hash={"target": target, "target_sha256": f.sha256},
        ip=ip,
        request_id=request_id,
    )
    try:
        with db.begin_nested():
            db.add(
                DeletionRequest(
                    workspace_id=workspace_id,
                    target_type="file",
                    target_id=f.id,
                    scope="single file (metadata and stored object)",
                    expected_affected=[preview],
                    reason=reason,
                    requested_by=requested_by,
                    approval_id=a.id,
                )
            )
    except IntegrityError:
        raise ApiError(409, "deletion_already_requested", "A deletion request for this file already exists.") from None
    _audit(
        db,
        workspace_id,
        actor_user_id,
        "file.deletion_requested",
        f"Deletion requested for {f.original_name} by {requester_label} — needs approval",
        target_type="file",
        target_id=str(f.id),
        task_id=task_id,
        ip=ip,
        request_id=request_id,
    )
    db.flush()
    return a


def request_file_deletion(ctx: Context, f: FileRecord, reason: str) -> S.ApprovalOut:
    a = file_deletion_request(
        ctx.db,
        workspace_id=ctx.workspace.id,
        requested_by=ctx.user.id,
        actor_user_id=ctx.user.id,
        file_id=f.id,
        reason=reason,
        requester_label=ctx.user.name,
        ip=ctx.ip,
        request_id=ctx.request_id,
    )
    return approvals_out(ctx.db, ctx.workspace.id, [a])[0]
