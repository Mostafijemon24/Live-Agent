"""File upload, listing, classification and download — tenant-scoped, private storage."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from functools import lru_cache
from typing import BinaryIO

from sqlalchemy import func, select

from app import schemas as S
from app.adapters.phase2 import scanner
from app.adapters.storage import ALLOWED, LocalPrivateFileStorage, detect_type, safe_display_name, validate_stored
from app.core.config import get_settings
from app.core.db import utcnow
from app.core.deps import Context
from app.core.errors import ApiError
from app.domain.enums import FileClassification, FileStatus, ScanStatus
from app.models import FileRecord
from app.services.usage import bump_usage, usage_value
from app.services.views import files_out

COLLECTIONS = ["Website audits", "SEO & content", "Research", "Support data", "Code"]


@lru_cache
def storage() -> LocalPrivateFileStorage:
    return LocalPrivateFileStorage(get_settings().storage_dir)


def limits() -> S.UploadLimitsOut:
    return S.UploadLimitsOut(
        max_bytes=get_settings().max_upload_bytes, allowed_types=list(ALLOWED), collections=COLLECTIONS
    )


def get_file(ctx: Context, file_id: uuid.UUID, include_deleted: bool = False) -> FileRecord:
    f = ctx.db.execute(
        select(FileRecord).where(FileRecord.workspace_id == ctx.workspace.id, FileRecord.id == file_id)
    ).scalar_one_or_none()
    if f is None:
        raise ctx.deny("file", file_id, "file")
    if f.deleted_at is not None and not include_deleted:
        raise ApiError(
            410, "file_deleted", "This file was deleted. An owner or admin can restore it from Recently deleted."
        )
    return f


def upload(ctx: Context, stream: BinaryIO, filename: str, collection: str) -> S.FileOut:
    settings = get_settings()
    if collection not in COLLECTIONS:
        raise ApiError(
            422,
            "validation_error",
            "Some fields need attention.",
            details=[{"field": "collection", "message": "Choose a collection from the list."}],
        )
    used = usage_value(ctx.db, ctx.workspace.id, "all", "storage_bytes")
    remaining = settings.workspace_storage_quota_bytes - used
    if remaining <= 0:
        raise ApiError(429, "quota_exceeded", "This workspace has used all of its file storage.")
    max_bytes = min(settings.max_upload_bytes, remaining)
    stored = storage().save(ctx.workspace.id, stream, max_bytes)
    try:
        detected = detect_type(stored.head, filename)
        if detected is None:
            raise ApiError(
                415,
                "unsupported_file_type",
                "This kind of file isn't accepted. Allowed: " + ", ".join(ALLOWED) + ".",
            )
        label, content_type = detected
        reason = validate_stored(storage().local_path(stored.key), label)
        if reason is not None:
            raise ApiError(415, "unsupported_file_type", f"This file was refused: it {reason}.")
        scan_status = scanner.scan(stored.key) if scanner.is_configured() else ScanStatus.not_configured.value
        status = (
            FileStatus.unscanned.value if scan_status == ScanStatus.not_configured.value else FileStatus.ready.value
        )
        if scan_status == ScanStatus.infected.value:
            storage().quarantine(stored.key)
            status = FileStatus.quarantined.value
        f = FileRecord(
            workspace_id=ctx.workspace.id,
            original_name=safe_display_name(filename),
            storage_key=stored.key,
            content_type=content_type,
            type_label=label,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
            status=status,
            scan_status=scan_status,
            classification=FileClassification.unknown.value,  # sharing blocked until classified
            collection=collection,
            uploaded_by=ctx.user.id,
        )
        ctx.db.add(f)
        ctx.db.flush()
        bump_usage(ctx.db, ctx.workspace.id, "storage_bytes", stored.size_bytes, period="all")
        bump_usage(ctx.db, ctx.workspace.id, "files_uploaded", 1)
        ctx.log(
            "file.uploaded",
            "file",
            f"{f.original_name} uploaded to private storage (not scanned — scanner not configured)",
            target_type="file",
            target_id=str(f.id),
            metadata={"type": label, "size_bytes": stored.size_bytes},
        )
        ctx.db.flush()
    except BaseException:
        # The object was never recorded (rejected or DB failure): remove the orphaned bytes.
        storage().discard_incomplete(stored.key)
        raise
    return files_out(ctx.db, ctx.workspace.id, [f])[0]


def list_files(
    ctx: Context,
    q: str | None,
    collection: str | None,
    classification: str | None,
    status: str | None,
    page: int,
    page_size: int,
    deleted: bool = False,
) -> S.FilePage:
    conds = [FileRecord.workspace_id == ctx.workspace.id]
    if deleted:  # "Recently deleted": restorable files only
        conds += [FileRecord.deleted_at.is_not(None), FileRecord.purge_after.is_not(None)]
    else:
        conds.append(FileRecord.deleted_at.is_(None))
    if q:
        like = f"%{q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')}%"
        conds.append(FileRecord.original_name.ilike(like, escape="\\"))
    if collection:
        conds.append(FileRecord.collection == collection)
    if classification:
        conds.append(FileRecord.classification == classification)
    if status:
        conds.append(FileRecord.status == status)
    total = ctx.db.execute(select(func.count()).select_from(FileRecord).where(*conds)).scalar_one()
    rows = list(
        ctx.db.execute(
            select(FileRecord)
            .where(*conds)
            .order_by(FileRecord.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars()
    )
    counts: dict[str, int] = dict(
        ctx.db.execute(
            select(FileRecord.collection, func.count())
            .where(FileRecord.workspace_id == ctx.workspace.id, FileRecord.deleted_at.is_(None))
            .group_by(FileRecord.collection)
        )
        .tuples()
        .all()
    )
    names = list(dict.fromkeys(COLLECTIONS + sorted(counts)))
    return S.FilePage(
        items=files_out(ctx.db, ctx.workspace.id, rows),
        page=page,
        page_size=page_size,
        total=total,
        collections=[S.CollectionCount(name=n, count=int(counts.get(n, 0))) for n in names],
    )


def patch(ctx: Context, file_id: uuid.UUID, body: S.FilePatchIn) -> S.FileOut:
    f = get_file(ctx, file_id)
    if body.classification is not None and body.classification.value != f.classification:
        old = f.classification
        f.classification = body.classification.value
        ctx.log(
            "privacy.classification_changed",
            "security",
            f"Classification of {f.original_name} changed from {old} to {f.classification}",
            target_type="file",
            target_id=str(f.id),
            metadata={"from": old, "to": f.classification},
        )
    if body.collection is not None and body.collection != f.collection:
        if body.collection not in COLLECTIONS:
            raise ApiError(
                422,
                "validation_error",
                "Some fields need attention.",
                details=[{"field": "collection", "message": "Choose a collection from the list."}],
            )
        f.collection = body.collection
        ctx.log(
            "file.updated",
            "file",
            f"{f.original_name} moved to {f.collection}",
            target_type="file",
            target_id=str(f.id),
        )
    f.updated_at = utcnow()
    return files_out(ctx.db, ctx.workspace.id, [f])[0]


def download(ctx: Context, file_id: uuid.UUID) -> tuple[FileRecord, Iterator[bytes]]:
    f = get_file(ctx, file_id)
    if f.status == FileStatus.quarantined.value:
        raise ApiError(403, "file_quarantined", "This file is quarantined and can't be opened.")
    if not f.storage_key.startswith(f"{ctx.workspace.id}/") or not storage().exists(f.storage_key):
        raise ApiError(410, "file_unavailable", "The stored copy of this file is unavailable.")
    ctx.log("file.downloaded", "file", f"{f.original_name} downloaded", target_type="file", target_id=str(f.id))
    return f, storage().open(f.storage_key)


def artifact_download(ctx: Context, artifact_id: uuid.UUID) -> tuple[str, Iterator[bytes]]:
    from app.models import Artifact

    a = ctx.db.execute(
        select(Artifact).where(Artifact.workspace_id == ctx.workspace.id, Artifact.id == artifact_id)
    ).scalar_one_or_none()
    if a is None or not a.storage_key or not a.storage_key.startswith(f"{ctx.workspace.id}/"):
        raise ctx.deny("artifact", artifact_id, "report")
    if not storage().exists(a.storage_key):
        raise ApiError(410, "file_unavailable", "The stored copy of this report is unavailable.")
    ctx.log("artifact.downloaded", "file", f"{a.name} downloaded", target_type="artifact", target_id=str(a.id))
    return a.name, storage().open(a.storage_key)
