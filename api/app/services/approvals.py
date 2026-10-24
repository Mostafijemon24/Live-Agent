"""Approval requests, decisions and deletion requests.

A decision is bound to the exact action through `payload_hash`. Approving never
executes anything in Phase 2: deletion requests become `approved_blocked` and
the approval's execution_state is `blocked_until_phase3`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

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
from app.models import ApprovalDecision, ApprovalRequest, DeletionRequest, FileRecord, Notification, Workspace
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
            **extra,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    key = get_settings().approval_signing_key.get_secret_value().encode()
    return hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()


def _next_approval_number(ctx: Context) -> int:
    from sqlalchemy import update

    return int(
        ctx.db.execute(
            update(Workspace)
            .where(Workspace.id == ctx.workspace.id)
            .values(approval_seq=Workspace.approval_seq + 1)
            .returning(Workspace.approval_seq)
        ).scalar_one()
    )


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
    a = ApprovalRequest(
        workspace_id=ctx.workspace.id,
        number=_next_approval_number(ctx),
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
        requested_by=ctx.user.id,
        expires_at=(utcnow() + expires_in) if expires_in else None,
    )
    a.payload_hash = payload_hash(a, extra_hash or {})
    ctx.db.add(a)
    ctx.db.flush()
    ctx.db.add(
        Notification(
            workspace_id=ctx.workspace.id,
            user_id=ctx.user.id,
            type="Approval requested",
            icon="hourglass",
            text=f"{approval_ref(a.number)}: {title}"[:300],
            target={"route": f"/approvals?id={a.id}", "id": str(a.id)},
        )
    )
    ctx.log(
        "approval.requested",
        "approval",
        f"{approval_ref(a.number)} requested: {title}",
        target_type="approval",
        target_id=str(a.id),
        task_id=task_id,
        metadata={"category": category.value},
    )
    return a


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
        a.execution_state = ExecutionState.blocked_until_phase3.value
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

    # Deletion requests follow the decision, but never delete anything in Phase 2.
    dr = ctx.db.execute(
        select(DeletionRequest).where(
            DeletionRequest.workspace_id == ctx.workspace.id, DeletionRequest.approval_id == a.id
        )
    ).scalar_one_or_none()
    if dr is not None:
        dr.status = {
            ApprovalDecisionKind.approve: DeletionRequestStatus.approved_blocked,
            ApprovalDecisionKind.reject: DeletionRequestStatus.rejected,
            ApprovalDecisionKind.request_changes: DeletionRequestStatus.changes_requested,
        }[kind].value
        dr.updated_at = now

    verb = {
        "approve": "approved — execution blocked until Phase 3",
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
        metadata={"category": a.category},
    )
    ctx.db.flush()
    return approvals_out(ctx.db, ctx.workspace.id, [a])[0]


def _extra_for(ctx: Context, a: ApprovalRequest) -> dict[str, str]:
    dr = ctx.db.execute(
        select(DeletionRequest).where(
            DeletionRequest.workspace_id == ctx.workspace.id, DeletionRequest.approval_id == a.id
        )
    ).scalar_one_or_none()
    return {"target": f"{dr.target_type}:{dr.target_id}"} if dr else {}


def request_file_deletion(ctx: Context, f: FileRecord, reason: str) -> S.ApprovalOut:
    open_req = ctx.db.execute(
        select(DeletionRequest.id).where(
            DeletionRequest.workspace_id == ctx.workspace.id,
            DeletionRequest.target_type == "file",
            DeletionRequest.target_id == f.id,
            DeletionRequest.status.in_(("pending_approval", "approved_blocked")),
        )
    ).first()
    if open_req:
        raise ApiError(409, "deletion_already_requested", "A deletion request for this file already exists.")
    size_mb = f"{f.size_bytes / (1024 * 1024):.1f} MB"
    a = create_approval(
        ctx,
        category=ApprovalCategory.record_deletion,
        title=f"Delete 1 file: {f.original_name}",
        reason=f"Requested by {ctx.user.name}: {reason}",
        affected=[f.original_name],
        leaves=False,
        destination="Workspace file storage",
        scope_summary=f"1 file · {size_mb}",
        consequences="Tasks that use this file will no longer be able to read it.",
        reversible="Deletion is disabled until Phase 3. When enabled, deleted files are kept for 30 days before permanent removal.",
        risk=RiskLevel.high,
        extra_hash={"target": f"file:{f.id}"},
    )
    try:
        ctx.db.add(
            DeletionRequest(
                workspace_id=ctx.workspace.id,
                target_type="file",
                target_id=f.id,
                scope="single file (metadata and stored object)",
                expected_affected=[
                    {"type": "file", "id": str(f.id), "name": f.original_name, "size_bytes": f.size_bytes}
                ],
                reason=reason,
                requested_by=ctx.user.id,
                approval_id=a.id,
            )
        )
        ctx.db.flush()
    except IntegrityError:
        ctx.db.rollback()
        raise ApiError(409, "deletion_already_requested", "A deletion request for this file already exists.") from None
    ctx.log(
        "file.deletion_requested",
        "file",
        f"Deletion requested for {f.original_name} — needs approval",
        target_type="file",
        target_id=str(f.id),
    )
    return approvals_out(ctx.db, ctx.workspace.id, [a])[0]
