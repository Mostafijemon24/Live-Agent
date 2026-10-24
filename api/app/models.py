"""SQLAlchemy models.

Tenancy: every tenant-owned row carries `workspace_id`. Child tables reference
their parent through a composite foreign key `(workspace_id, parent_id)` →
`parent(workspace_id, id)`, so the database itself refuses a row that points at
another workspace's record. Enum-like columns are text + CHECK constraints so
migrations stay simple and additive.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain import enums as E


def _check(col: str, enum: type[Any], name: str | None = None) -> CheckConstraint:
    vals = ", ".join(f"'{v}'" for v in E.values(enum))
    return CheckConstraint(f"{col} IN ({vals})", name=name or f"{col}_valid")


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _updated() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


# ---------------------------------------------------------------- identity
class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="UTC")
    notification_prefs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    onboarding: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    __table_args__ = (
        Index("uq_users_email_lower", func.lower(email), unique=True),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    privacy_mode: Mapped[str] = mapped_column(String(16), nullable=False, server_default="strict")
    privacy_configured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    tool_permissions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    allowed_domains: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    # Per-workspace counters for human-friendly refs (T-1001, A-301, AU-1). Updated under row lock.
    task_seq: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1000")
    approval_seq: Mapped[int] = mapped_column(Integer, nullable=False, server_default="300")
    automation_seq: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    __table_args__ = (_check("privacy_mode", E.PrivacyMode),)


class WorkspaceMembership(Base):
    __tablename__ = "workspace_memberships"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = _created()
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id"),
        _check("role", E.WorkspaceRole),
        Index("ix_memberships_user", "user_id"),
    )


class AuthSession(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False, unique=True)
    created_at: Mapped[datetime] = _created()
    last_seen_at: Mapped[datetime] = _created()
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(32))
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(256))
    __table_args__ = (Index("ix_sessions_user_active", "user_id", postgresql_where=text("revoked_at IS NULL")),)


class AuthToken(Base):
    """One-time tokens for email verification and password reset. Only the hash is stored."""

    __tablename__ = "auth_tokens"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False, unique=True)
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (_check("purpose", E.AuthTokenPurpose), Index("ix_auth_tokens_user_purpose", "user_id", "purpose"))


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


# ---------------------------------------------------------------- tasks
class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    integration_key: Mapped[str | None] = mapped_column(String(32))
    waiting_for: Mapped[str | None] = mapped_column(String(32))
    question: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    plan_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # data_sources, destination (from planner)
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    automation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_tasks_workspace_id_id"),
        UniqueConstraint("workspace_id", "number", name="uq_tasks_workspace_number"),
        UniqueConstraint("workspace_id", "idempotency_key", name="uq_tasks_workspace_idempotency"),
        _check("status", E.TaskStatus),
        _check("type", E.TaskType),
        _check("priority", E.TaskPriority),
        _check("mode", E.ExecutionMode),
        CheckConstraint(
            "waiting_for IS NULL OR waiting_for IN ('planning_service','execution_engine','user_input','approval')",
            name="waiting_for_valid",
        ),
        Index("ix_tasks_ws_updated", "workspace_id", "updated_at"),
        Index("ix_tasks_ws_status", "workspace_id", "status"),
        Index("ix_tasks_ws_created", "workspace_id", "created_at"),
    )


class TaskStep(Base):
    __tablename__ = "task_steps"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    tool: Mapped[str] = mapped_column(String(120), nullable=False)
    risk: Mapped[str] = mapped_column(String(32), nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    state: Mapped[str] = mapped_column(String(32), nullable=False, server_default="not_started")
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "task_id"], ["tasks.workspace_id", "tasks.id"], ondelete="RESTRICT"),
        UniqueConstraint("task_id", "position"),
        _check("risk", E.StepRisk),
        _check("state", E.StepState),
    )


class TaskEvent(Base):
    """Task timeline / run log. Append-only for the application role."""

    __tablename__ = "task_events"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = _created()
    level: Mapped[str] = mapped_column(String(8), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str | None] = mapped_column(String(32))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "task_id"], ["tasks.workspace_id", "tasks.id"], ondelete="RESTRICT"),
        CheckConstraint("level IN ('info','warn','error','note')", name="level_valid"),
        Index("ix_task_events_task_created", "task_id", "created_at"),
    )


class TaskAttachment(Base):
    __tablename__ = "task_attachments"
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = _created()
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "task_id"], ["tasks.workspace_id", "tasks.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["workspace_id", "file_id"], ["files.workspace_id", "files.id"], ondelete="RESTRICT"),
    )


class Job(Base):
    """Background-job outbox. Phase 2 records intent only; Phase 3 workers consume it."""

    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    dedupe_key: Mapped[str | None] = mapped_column(String(120))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = _created()
    __table_args__ = (
        UniqueConstraint("workspace_id", "dedupe_key", name="uq_jobs_workspace_dedupe"),
        Index("ix_jobs_status_created", "status", "created_at"),
    )


# ---------------------------------------------------------------- approvals & deletion requests
class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    affected_items: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    data_leaves_workspace: Mapped[bool] = mapped_column(Boolean, nullable=False)
    destination: Mapped[str] = mapped_column(String(300), nullable=False)
    scope_summary: Mapped[str] = mapped_column(String(200), nullable=False)
    consequences: Mapped[str] = mapped_column(Text, nullable=False)
    reversible: Mapped[str] = mapped_column(Text, nullable=False)
    risk: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    execution_state: Mapped[str] = mapped_column(String(32), nullable=False, server_default="not_executed")
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # binds a decision to the exact action
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    requested_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = _updated()
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_approval_requests_workspace_id_id"),
        UniqueConstraint("workspace_id", "number", name="uq_approval_requests_workspace_number"),
        ForeignKeyConstraint(["workspace_id", "task_id"], ["tasks.workspace_id", "tasks.id"], ondelete="RESTRICT"),
        _check("category", E.ApprovalCategory),
        _check("status", E.ApprovalStatus),
        _check("risk", E.RiskLevel),
        _check("execution_state", E.ExecutionState),
        Index("ix_approvals_ws_status", "workspace_id", "status", "requested_at"),
    )


class ApprovalDecision(Base):
    """Every decision ever made. Append-only for the application role."""

    __tablename__ = "approval_decisions"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    approval_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decided_at: Mapped[datetime] = _created()
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "approval_id"],
            ["approval_requests.workspace_id", "approval_requests.id"],
            ondelete="RESTRICT",
        ),
        _check("decision", E.ApprovalDecisionKind),
    )


class DeletionRequest(Base):
    __tablename__ = "deletion_requests"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    scope: Mapped[str] = mapped_column(String(200), nullable=False)
    expected_affected: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approval_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending_approval")
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "approval_id"],
            ["approval_requests.workspace_id", "approval_requests.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("target_type IN ('file')", name="target_type_valid"),
        _check("status", E.DeletionRequestStatus),
        Index(
            "uq_deletion_requests_open_target",
            "workspace_id",
            "target_type",
            "target_id",
            unique=True,
            postgresql_where=text("status IN ('pending_approval','approved_blocked')"),
        ),
    )


# ---------------------------------------------------------------- files
class FileRecord(Base):
    __tablename__ = "files"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    type_label: Mapped[str] = mapped_column(String(16), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    scan_status: Mapped[str] = mapped_column(String(16), nullable=False)
    classification: Mapped[str] = mapped_column(String(32), nullable=False, server_default="unknown")
    collection: Mapped[str] = mapped_column(String(80), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_files_workspace_id_id"),
        _check("status", E.FileStatus),
        _check("scan_status", E.ScanStatus),
        _check("classification", E.FileClassification),
        CheckConstraint("size_bytes >= 0", name="size_nonnegative"),
        Index("ix_files_ws_created", "workspace_id", "created_at"),
    )


# ---------------------------------------------------------------- integrations, automations, artifacts
class IntegrationConnection(Base):
    __tablename__ = "integrations"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False)
    key: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    granted_scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    # Credentials are never stored in Phase 2. Phase 3 adds an encrypted secret reference here.
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    __table_args__ = (UniqueConstraint("workspace_id", "key"), _check("status", E.IntegrationStatus))


class Automation(Base):
    __tablename__ = "automations"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    frequency: Mapped[str | None] = mapped_column(String(16))
    day: Mapped[str | None] = mapped_column(String(16))
    time_of_day: Mapped[str | None] = mapped_column(String(5))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    template: Mapped[str] = mapped_column(String(120), nullable=False)
    tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    file_scope: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_policy: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    __table_args__ = (
        UniqueConstraint("workspace_id", "number", name="uq_automations_workspace_number"),
        CheckConstraint("trigger IN ('manual','schedule','event')", name="trigger_valid"),
        CheckConstraint("frequency IS NULL OR frequency IN ('daily','weekly','monthly')", name="frequency_valid"),
        # The scheduler is not installed: a scheduled automation may never be enabled in Phase 2.
        CheckConstraint("NOT (trigger = 'schedule' AND enabled)", name="schedule_disabled_until_scheduler"),
    )


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    provenance: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = _created()
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "task_id"], ["tasks.workspace_id", "tasks.id"], ondelete="RESTRICT"),
        CheckConstraint("provenance IN ('ai_generated','verified_result')", name="provenance_valid"),
        Index("ix_artifacts_ws_created", "workspace_id", "created_at"),
    )


# ---------------------------------------------------------------- audit, notifications, usage, requests
class AuditEvent(Base):
    """Security-relevant events. Append-only: the app role has INSERT/SELECT only and a trigger
    rejects UPDATE/DELETE for every role."""

    __tablename__ = "audit_events"
    id: Mapped[uuid.UUID] = _uuid_pk()
    created_at: Mapped[datetime] = _created()
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ip: Mapped[str | None] = mapped_column(INET)
    request_id: Mapped[str | None] = mapped_column(String(64))
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    __table_args__ = (
        CheckConstraint(
            "category IN ('task','plan','approval','execution','error','integration','security','auth','file','settings')",
            name="category_valid",
        ),
        Index("ix_audit_ws_created", "workspace_id", "created_at"),
        Index("ix_audit_ws_task", "workspace_id", "task_id"),
    )


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    icon: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()
    __table_args__ = (Index("ix_notifications_user_created", "workspace_id", "user_id", "created_at"),)


class UsageCounter(Base):
    __tablename__ = "usage_counters"
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="RESTRICT"), primary_key=True)
    period: Mapped[str] = mapped_column(String(7), primary_key=True)  # YYYY-MM, or 'all' for running totals
    metric: Mapped[str] = mapped_column(String(32), primary_key=True)
    used: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")


class AccountRequest(Base):
    __tablename__ = "account_requests"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="received")
    created_at: Mapped[datetime] = _created()
    __table_args__ = (CheckConstraint("kind IN ('data_export','account_deletion')", name="kind_valid"),)
