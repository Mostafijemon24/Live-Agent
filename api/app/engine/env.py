"""Build the server-side facts (PlanEnv) for a task from stored records only."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.engine.providers import get_provider
from app.engine.tools.base import FileInfo, PlanEnv, ProviderView
from app.models import FileRecord, IntegrationConnection, Task, TaskAttachment, Workspace
from app.services.auth import DEFAULT_AI_RULES, DEFAULT_TOOLS


def build_env(db: Session, task: Task, settings: Settings) -> PlanEnv:
    ws = db.execute(select(Workspace).where(Workspace.id == task.workspace_id)).scalar_one()
    rows = db.execute(
        select(FileRecord)
        .join(
            TaskAttachment,
            (TaskAttachment.file_id == FileRecord.id) & (TaskAttachment.workspace_id == FileRecord.workspace_id),
        )
        .where(TaskAttachment.workspace_id == task.workspace_id, TaskAttachment.task_id == task.id)
    ).scalars()
    files = {
        f.id: FileInfo(
            id=f.id,
            name=f.original_name,
            classification=f.classification,
            type_label=f.type_label,
            status=f.status,
            deleted=f.deleted_at is not None,
            size_bytes=f.size_bytes,
            sha256=f.sha256,
            storage_key=f.storage_key,
        )
        for f in rows
    }
    wp = db.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.workspace_id == task.workspace_id,
            IntegrationConnection.key == "wordpress",
            IntegrationConnection.status == "connected",
        )
    ).scalar_one_or_none()
    info = get_provider(settings).info
    return PlanEnv(
        workspace_id=task.workspace_id,
        task_classification=task.data_classification,
        attached_files=files,
        allowed_domains=list(ws.allowed_domains or []),
        privacy_mode=ws.privacy_mode,
        tool_permissions={**DEFAULT_TOOLS, **(ws.tool_permissions or {})},
        ai_rules={**DEFAULT_AI_RULES, **(ws.ai_rules or {})},
        provider=ProviderView(configured=info.configured, location=info.location, label=info.label),
        wordpress_site=str((wp.config or {}).get("site_url")) if wp and (wp.config or {}).get("site_url") else None,
    )
