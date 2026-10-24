"""Wire enums shared by models, schemas and services. Values match web/lib/api/types.ts."""

from __future__ import annotations

from enum import StrEnum


class TaskStatus(StrEnum):
    draft = "draft"
    queued = "queued"
    planning = "planning"
    awaiting_approval = "awaiting_approval"
    running = "running"
    needs_input = "needs_input"
    completed = "completed"
    failed = "failed"
    paused = "paused"
    cancelled = "cancelled"
    partially_completed = "partially_completed"


class TaskType(StrEnum):
    research = "research"
    website = "website"
    seo_content = "seo_content"
    code = "code"
    browser = "browser"
    file_analysis = "file_analysis"
    custom = "custom"


class TaskPriority(StrEnum):
    normal = "normal"
    high = "high"


class ExecutionMode(StrEnum):
    plan_only = "plan_only"
    prepare = "prepare"
    execute = "execute"


class WaitingFor(StrEnum):
    planning_service = "planning_service"
    execution_engine = "execution_engine"
    user_input = "user_input"
    approval = "approval"


class StepRisk(StrEnum):
    read_only = "read_only"
    workspace_only = "workspace_only"
    prepare_only = "prepare_only"
    production_change = "production_change"
    publish = "publish"
    external_transfer = "external_transfer"


class StepState(StrEnum):
    not_started = "not_started"
    in_progress = "in_progress"
    done = "done"
    failed = "failed"
    paused = "paused"
    waiting_for_input = "waiting_for_input"
    skipped = "skipped"
    cancelled = "cancelled"


class ApprovalCategory(StrEnum):
    external_transfer = "external_transfer"
    production_change = "production_change"
    publish = "publish"
    send_message = "send_message"
    record_deletion = "record_deletion"
    permission_change = "permission_change"


class ApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    changes_requested = "changes_requested"
    expired = "expired"


class ApprovalDecisionKind(StrEnum):
    approve = "approve"
    reject = "reject"
    request_changes = "request_changes"


class ExecutionState(StrEnum):
    not_executed = "not_executed"
    blocked_until_phase3 = "blocked_until_phase3"


class RiskLevel(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class FileStatus(StrEnum):
    uploading = "uploading"
    unscanned = "unscanned"
    scanning = "scanning"
    processing = "processing"
    ready = "ready"
    failed = "failed"
    quarantined = "quarantined"


class ScanStatus(StrEnum):
    not_configured = "not_configured"
    pending = "pending"
    clean = "clean"
    infected = "infected"


class FileClassification(StrEnum):
    private = "private"
    approved_integration = "approved_integration"
    public = "public"
    unknown = "unknown"


class WorkspaceRole(StrEnum):
    owner = "owner"
    admin = "admin"
    member = "member"
    viewer = "viewer"


class PrivacyMode(StrEnum):
    strict = "strict"
    approval = "approval"
    custom = "custom"


class IntegrationStatus(StrEnum):
    demo = "demo"
    not_connected = "not_connected"
    backend_required = "backend_required"
    connected = "connected"


class AuthTokenPurpose(StrEnum):
    verify_email = "verify_email"
    reset_password = "reset_password"  # noqa: S105 - token purpose name, not a secret


class DeletionRequestStatus(StrEnum):
    pending_approval = "pending_approval"
    approved_blocked = "approved_blocked"  # approved, but execution disabled until Phase 3
    rejected = "rejected"
    changes_requested = "changes_requested"


class JobStatus(StrEnum):
    pending = "pending"  # recorded; no worker is installed in Phase 2


def values(e: type[StrEnum]) -> list[str]:
    return [m.value for m in e]
