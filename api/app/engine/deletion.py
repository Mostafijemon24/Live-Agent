"""Deletion service (runs as the `steward_deleter` database role, in its own process).

Workflow: preview (deletion request lists the exact file, size and SHA-256) → one-time approval
by an owner/admin → this service re-validates everything right before executing (approval
binding, approver still owner/admin, expiry, policy version, file unchanged and in the same
workspace) → soft delete in one transaction (row marked deleted, object moved to trash) → audit →
recoverable during the retention window → purge of the stored bytes after it. The database row
is kept as a tombstone. Nothing is deleted because a model suggested it: only approved requests
reach this service.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.storage import LocalPrivateFileStorage
from app.core.config import Settings
from app.core.db import utcnow
from app.domain.enums import DeletionRequestStatus, ExecutionState
from app.engine import queue as Q
from app.engine.canonical import args_hash
from app.engine.policy import POLICY_VERSION
from app.engine.records import audit, notify
from app.models import ApprovalRequest, DeletionRequest, FileRecord
from app.services.approvals import deletion_extra, verify_binding


def _refuse(db: Session, dr: DeletionRequest, a: ApprovalRequest | None, reason: str, job: Q.ClaimedJob) -> None:
    dr.status = DeletionRequestStatus.execution_refused.value
    dr.execution_result = {"refused": True, "reason": reason}
    dr.updated_at = utcnow()
    if a is not None and a.execution_state == ExecutionState.pending_execution.value:
        a.execution_state = ExecutionState.invalidated.value
    audit(
        db,
        dr.workspace_id,
        "file.deletion_refused",
        "file",
        f"Deletion refused at execution time: {reason}",
        target_type="file",
        target_id=str(dr.target_id),
        job_id=job.id,
        metadata={"reason": reason, "deletion_request": str(dr.id)},
    )
    notify(
        db,
        dr.workspace_id,
        dr.requested_by,
        "Deletion not performed",
        "shield-alert",
        f"A file deletion was refused: {reason}",
        "/approvals",
    )


def handle_delete(db: Session, job: Q.ClaimedJob, settings: Settings) -> None:
    dr_id = uuid.UUID(str(job.payload["deletion_request_id"]))
    dr = db.execute(
        select(DeletionRequest)
        .where(DeletionRequest.workspace_id == job.workspace_id, DeletionRequest.id == dr_id)
        .with_for_update()
    ).scalar_one_or_none()
    if dr is None or dr.status != DeletionRequestStatus.approved.value:
        return  # stale/duplicate delivery: never act twice
    a = db.execute(
        select(ApprovalRequest)
        .where(ApprovalRequest.workspace_id == dr.workspace_id, ApprovalRequest.id == dr.approval_id)
        .with_for_update()
    ).scalar_one_or_none()
    f = db.execute(
        select(FileRecord)
        .where(FileRecord.workspace_id == dr.workspace_id, FileRecord.id == dr.target_id)
        .with_for_update()
    ).scalar_one_or_none()
    if a is None:
        _refuse(db, dr, None, "the approval is missing", job)
        return
    if f is None:
        _refuse(db, dr, a, "the file no longer exists in this workspace", job)
        return
    if f.deleted_at is not None:
        _refuse(db, dr, a, "the file was already deleted", job)
        return
    current = args_hash("deletion.execute", {"file_id": str(f.id), "sha256": f.sha256, "size_bytes": f.size_bytes})
    reason = verify_binding(
        db,
        a,
        workspace_id=dr.workspace_id,
        operation="deletion.execute",
        args_hash=current,
        targets=[f"file:{f.id}"],
        step_id=None,
        policy_version=POLICY_VERSION,
        extra_hash=deletion_extra(dr),
    )
    if reason is not None:
        if reason == "arguments changed after approval":
            reason = "the file changed after the deletion was approved"
        _refuse(db, dr, a, reason, job)
        return

    storage = LocalPrivateFileStorage(settings.storage_dir)
    now = utcnow()
    purge_after = now + timedelta(days=settings.deletion_retention_days)
    f.deleted_at = now
    f.purge_after = purge_after
    f.updated_at = now
    dr.status = DeletionRequestStatus.executed.value
    dr.executed_at = now
    dr.execution_result = {"soft_deleted": True, "purge_after": purge_after.isoformat(), "file": f.original_name}
    dr.updated_at = now
    a.execution_state = ExecutionState.executed.value
    a.updated_at = now
    audit(
        db,
        dr.workspace_id,
        "file.deleted",
        "file",
        f"{f.original_name} deleted (recoverable until {purge_after:%Y-%m-%d})",
        target_type="file",
        target_id=str(f.id),
        job_id=job.id,
        metadata={"deletion_request": str(dr.id), "approval": str(a.id), "sha256": f.sha256},
    )
    notify(
        db,
        dr.workspace_id,
        dr.requested_by,
        "File deleted",
        "trash-2",
        f"{f.original_name} was deleted. It can be restored until {purge_after:%b %d}.",
        "/files",
    )
    db.flush()  # surface constraint/privilege errors before touching storage
    moved = False
    if storage.exists(f.storage_key):
        storage.move_to_trash(f.storage_key)
        moved = True
    try:
        db.commit()
    except Exception:
        if moved:
            storage.restore_from_trash(f.storage_key)  # recovery: the database change did not happen
        raise


def handle_restore(db: Session, job: Q.ClaimedJob, settings: Settings) -> None:
    file_id = uuid.UUID(str(job.payload["file_id"]))
    f = db.execute(
        select(FileRecord)
        .where(FileRecord.workspace_id == job.workspace_id, FileRecord.id == file_id)
        .with_for_update()
    ).scalar_one_or_none()
    if f is None or f.deleted_at is None:
        return
    storage = LocalPrivateFileStorage(settings.storage_dir)
    if f.purge_after is None or f.purge_after <= utcnow() or not storage.in_trash(f.storage_key):
        audit(
            db,
            f.workspace_id,
            "file.restore_failed",
            "file",
            f"{f.original_name} could not be restored: the retention period has ended",
            target_type="file",
            target_id=str(f.id),
            job_id=job.id,
        )
        return
    dr = db.execute(
        select(DeletionRequest)
        .where(
            DeletionRequest.workspace_id == f.workspace_id,
            DeletionRequest.target_id == f.id,
            DeletionRequest.status == DeletionRequestStatus.executed.value,
        )
        .order_by(DeletionRequest.executed_at.desc())
        .limit(1)
        .with_for_update()
    ).scalar_one_or_none()
    f.deleted_at = None
    f.purge_after = None
    f.updated_at = utcnow()
    if dr is not None:
        dr.status = DeletionRequestStatus.restored.value
        dr.updated_at = utcnow()
    by = job.payload.get("requested_by")
    audit(
        db,
        f.workspace_id,
        "file.restored",
        "file",
        f"{f.original_name} restored",
        target_type="file",
        target_id=str(f.id),
        job_id=job.id,
        metadata={"requested_by": by},
    )
    if by:
        notify(
            db,
            f.workspace_id,
            uuid.UUID(str(by)),
            "File restored",
            "rotate-ccw",
            f"{f.original_name} was restored.",
            "/files",
        )
    db.flush()
    storage.restore_from_trash(f.storage_key)
    try:
        db.commit()
    except Exception:
        storage.move_to_trash(f.storage_key)
        raise


def handle_purge(db: Session, job: Q.ClaimedJob, settings: Settings) -> None:
    storage = LocalPrivateFileStorage(settings.storage_dir)
    rows = (
        db.execute(
            select(FileRecord)
            .where(
                FileRecord.workspace_id == job.workspace_id,
                FileRecord.deleted_at.is_not(None),
                FileRecord.purge_after.is_not(None),
                FileRecord.purge_after <= utcnow(),
            )
            .with_for_update(skip_locked=True)
            .limit(200)
        )
        .scalars()
        .all()
    )
    for f in rows:
        storage.purge_from_trash(f.storage_key)
        f.purge_after = None  # tombstone: deleted, bytes gone
        f.updated_at = utcnow()
        audit(
            db,
            f.workspace_id,
            "file.purged",
            "file",
            f"{f.original_name} permanently removed after the retention period",
            target_type="file",
            target_id=str(f.id),
            job_id=job.id,
        )
