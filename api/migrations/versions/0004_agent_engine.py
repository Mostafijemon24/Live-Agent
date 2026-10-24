"""Phase 3 agent engine: plan/step policy fields, durable queue, model usage, worker
heartbeats, soft deletion, and separate database roles for workers and deletion.

Additive. The only data change remaps file classifications to the Phase 3 names
(private -> confidential, approved_integration -> internal); downgrade maps them back.
No rows are deleted.

Database roles (created by deploy/db/init-roles.sh; this migration only grants):
- steward_app       API process. Loses UPDATE on files.deleted_at / purge_after.
- steward_worker    orchestrator, tool runner, scheduler. No DELETE anywhere, no access
                    to sessions, auth tokens or password hashes, no file soft-delete.
- steward_deleter   deletion service. The only role that can soft-delete a file; it
                    reads approvals and deletion requests to revalidate them. No DELETE.
- steward_readonly  reporting / support. SELECT only, without secrets.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-24
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _role(env: str, default: str) -> str:
    return os.environ.get(env, default).replace('"', "")


APP = _role("DB_APP_ROLE", "steward_app")
WORKER = _role("DB_WORKER_ROLE", "steward_worker")
DELETER = _role("DB_DELETER_ROLE", "steward_deleter")
READONLY = _role("DB_READONLY_ROLE", "steward_readonly")

JSONB = postgresql.JSONB(astext_type=sa.Text())

# (table, constraint suffix, old expression, new expression)
CHECKS: list[tuple[str, str, str, str]] = [
    (
        "approval_requests",
        "category_valid",
        "category IN ('external_transfer', 'production_change', 'publish', 'send_message', 'record_deletion', 'permission_change')",
        "category IN ('external_transfer', 'production_change', 'publish', 'send_message', 'record_deletion', "
        "'permission_change', 'code_execution')",
    ),
    (
        "files",
        "classification_valid",
        "classification IN ('private', 'approved_integration', 'public', 'unknown')",
        "classification IN ('public', 'internal', 'confidential', 'unknown')",
    ),
    (
        "task_steps",
        "state_valid",
        "state IN ('not_started', 'in_progress', 'done', 'failed', 'paused', 'waiting_for_input', 'skipped', 'cancelled')",
        "state IN ('not_started', 'in_progress', 'done', 'failed', 'paused', 'waiting_for_input', 'skipped', "
        "'cancelled', 'awaiting_approval', 'blocked', 'rejected')",
    ),
    (
        "approval_requests",
        "execution_state_valid",
        "execution_state IN ('not_executed', 'blocked_until_phase3')",
        "execution_state IN ('not_executed', 'blocked_until_phase3', 'pending_execution', 'executed', "
        "'execution_failed', 'invalidated')",
    ),
    (
        "integrations",
        "status_valid",
        "status IN ('demo', 'not_connected', 'backend_required', 'connected')",
        "status IN ('demo', 'not_connected', 'backend_required', 'connected', 'error')",
    ),
    (
        "deletion_requests",
        "status_valid",
        "status IN ('pending_approval', 'approved_blocked', 'rejected', 'changes_requested')",
        "status IN ('pending_approval', 'approved_blocked', 'approved', 'rejected', 'changes_requested', "
        "'executed', 'execution_refused', 'restored')",
    ),
]

# Tables that hold no secrets; readonly and worker roles may SELECT them.
PLAIN_TABLES = [
    "workspaces",
    "workspace_memberships",
    "tasks",
    "task_steps",
    "task_attachments",
    "task_events",
    "jobs",
    "approval_requests",
    "approval_decisions",
    "deletion_requests",
    "files",
    "integrations",
    "automations",
    "artifacts",
    "notifications",
    "usage_counters",
    "audit_events",
    "model_calls",
    "workers",
]
USER_PUBLIC_COLUMNS = "id, email, name, timezone, notification_prefs, created_at"
FILE_APP_UPDATE_COLUMNS = (
    "original_name, storage_key, content_type, type_label, size_bytes, sha256, status, scan_status, "
    "classification, collection, error_message, updated_at"
)


def _require_roles() -> None:
    for role in (APP, WORKER, DELETER, READONLY):
        op.execute(f"""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
            RAISE EXCEPTION 'Database role {role} does not exist. Run deploy/db/init-roles.sh first.';
          END IF;
        END $$;
        """)


def upgrade() -> None:
    _require_roles()

    # ---------------------------------------------------------------- new tables
    op.create_table(
        "workers",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("hostname", sa.String(length=120), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("jobs_done", sa.Integer(), server_default="0", nullable=False),
        sa.Column("jobs_failed", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint(
            "kind IN ('orchestrator','tools','deletion','scheduler')", name=op.f("ck_workers_kind_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workers")),
    )
    op.create_table(
        "model_calls",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("location", sa.String(length=16), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("latency_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("outcome", sa.String(length=24), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("redactions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("location IN ('local', 'external')", name=op.f("ck_model_calls_location_valid")),
        sa.CheckConstraint(
            "outcome IN ('ok','error','timeout','rate_limited','blocked','invalid_output','quota_exceeded')",
            name=op.f("ck_model_calls_outcome_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["tasks.workspace_id", "tasks.id"],
            name="fk_model_calls_workspace_task",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_model_calls_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_calls")),
    )
    op.create_index("ix_model_calls_ws_created", "model_calls", ["workspace_id", "created_at"], unique=False)

    # ---------------------------------------------------------------- tasks
    op.add_column("tasks", sa.Column("plan_version", sa.Integer(), server_default="0", nullable=False))
    op.add_column(
        "tasks", sa.Column("data_classification", sa.String(length=16), server_default="confidential", nullable=False)
    )
    op.add_column("tasks", sa.Column("plan_summary", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        op.f("ck_tasks_data_classification_valid"),
        "tasks",
        "data_classification IN ('public', 'internal', 'confidential', 'unknown')",
    )

    # ---------------------------------------------------------------- task steps
    op.add_column("task_steps", sa.Column("plan_version", sa.Integer(), server_default="1", nullable=False))
    op.add_column("task_steps", sa.Column("step_key", sa.String(length=16), server_default="", nullable=False))
    op.add_column("task_steps", sa.Column("tool_id", sa.String(length=64), nullable=True))
    op.add_column("task_steps", sa.Column("args", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column("task_steps", sa.Column("args_hash", sa.String(length=64), nullable=True))
    for col in ("permissions", "classifications", "destinations"):
        op.add_column("task_steps", sa.Column(col, JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.add_column("task_steps", sa.Column("impact", sa.String(length=32), server_default="none", nullable=False))
    op.add_column("task_steps", sa.Column("policy", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column("task_steps", sa.Column("idempotent", sa.Boolean(), server_default="true", nullable=False))
    op.add_column("task_steps", sa.Column("expected_output", sa.Text(), server_default="", nullable=False))
    op.add_column("task_steps", sa.Column("timeout_seconds", sa.Integer(), server_default="60", nullable=False))
    op.add_column("task_steps", sa.Column("max_attempts", sa.Integer(), server_default="1", nullable=False))
    op.add_column("task_steps", sa.Column("attempts", sa.Integer(), server_default="0", nullable=False))
    op.add_column("task_steps", sa.Column("output", JSONB, nullable=True))
    op.add_column("task_steps", sa.Column("error", sa.Text(), nullable=True))
    op.add_column("task_steps", sa.Column("approval_id", sa.UUID(), nullable=True))
    op.execute("UPDATE task_steps SET step_key = 's' || position WHERE step_key = ''")
    op.drop_constraint("uq_task_steps_task_id_position", "task_steps", type_="unique")
    op.create_unique_constraint(
        "uq_task_steps_task_version_position", "task_steps", ["task_id", "plan_version", "position"]
    )
    op.create_unique_constraint("uq_task_steps_workspace_id_id", "task_steps", ["workspace_id", "id"])
    op.create_foreign_key(
        "fk_task_steps_workspace_approval",
        "task_steps",
        "approval_requests",
        ["workspace_id", "approval_id"],
        ["workspace_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_task_steps_impact_valid"),
        "task_steps",
        "impact IN ('none','workspace_write','external_read','external_transfer','publish','send_message',"
        "'production_change','sensitive_change','delete','permission_change')",
    )

    # ---------------------------------------------------------------- jobs (durable queue)
    op.add_column("jobs", sa.Column("queue", sa.String(length=16), server_default="orchestrator", nullable=False))
    op.add_column("jobs", sa.Column("priority", sa.Integer(), server_default="100", nullable=False))
    op.add_column("jobs", sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False))
    op.add_column(
        "jobs", sa.Column("run_after", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)
    )
    op.add_column("jobs", sa.Column("locked_by", sa.String(length=120), nullable=True))
    op.add_column("jobs", sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("step_id", sa.UUID(), nullable=True))
    op.create_index("ix_jobs_claim", "jobs", ["queue", "status", "run_after", "priority"], unique=False)
    op.create_check_constraint(
        op.f("ck_jobs_status_valid"),
        "jobs",
        "status IN ('pending', 'running', 'succeeded', 'failed', 'dead', 'cancelled')",
    )
    op.create_check_constraint(op.f("ck_jobs_queue_valid"), "jobs", "queue IN ('orchestrator', 'tools', 'deletion')")
    op.create_check_constraint(op.f("ck_jobs_attempts_valid"), "jobs", "attempts >= 0 AND max_attempts >= 1")

    # ---------------------------------------------------------------- approvals
    op.add_column("approval_requests", sa.Column("step_id", sa.UUID(), nullable=True))
    op.add_column("approval_requests", sa.Column("operation", sa.String(length=64), nullable=True))
    op.add_column("approval_requests", sa.Column("args_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "approval_requests", sa.Column("targets", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False)
    )
    op.add_column("approval_requests", sa.Column("policy_version", sa.String(length=32), nullable=True))
    op.add_column("approval_requests", sa.Column("decided_by", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_approval_requests_decided_by_users"),
        "approval_requests",
        "users",
        ["decided_by"],
        ["id"],
        ondelete="RESTRICT",
    )

    # ---------------------------------------------------------------- other tables
    op.add_column(
        "artifacts", sa.Column("content_type", sa.String(length=120), server_default="text/markdown", nullable=False)
    )
    op.add_column("artifacts", sa.Column("size_bytes", sa.BigInteger(), server_default="0", nullable=False))
    op.add_column("artifacts", sa.Column("sha256", sa.String(length=64), nullable=True))
    op.add_column("artifacts", sa.Column("step_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_artifacts_workspace_step",
        "artifacts",
        "task_steps",
        ["workspace_id", "step_id"],
        ["workspace_id", "id"],
        ondelete="RESTRICT",
    )
    op.add_column("automations", sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_automations_due", "automations", ["enabled", "next_run_at"], unique=False)
    op.drop_constraint(op.f("ck_automations_schedule_disabled_until_scheduler"), "automations", type_="check")
    op.add_column("deletion_requests", sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("deletion_requests", sa.Column("execution_result", JSONB, nullable=True))
    op.add_column("files", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("files", sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True))
    op.add_column("integrations", sa.Column("config", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column("integrations", sa.Column("error_message", sa.Text(), nullable=True))

    # ---------------------------------------------------------------- enum check changes + data remap
    for table, suffix, _old, _new in CHECKS:
        op.drop_constraint(op.f(f"ck_{table}_{suffix}"), table, type_="check")
        if table == "files":
            # Keep the old values valid during the remap, then tighten.
            op.create_check_constraint(
                op.f(f"ck_{table}_{suffix}"),
                table,
                "classification IN ('private', 'approved_integration', 'public', 'internal', 'confidential', 'unknown')",
            )
            op.execute("UPDATE files SET classification = 'confidential' WHERE classification = 'private'")
            op.execute("UPDATE files SET classification = 'internal' WHERE classification = 'approved_integration'")
            op.drop_constraint(op.f(f"ck_{table}_{suffix}"), table, type_="check")
    for table, suffix, _old, new in CHECKS:
        op.create_check_constraint(op.f(f"ck_{table}_{suffix}"), table, new)
    _open_deletion_index("status IN ('pending_approval','approved_blocked','approved')")

    _grant()


def _open_deletion_index(where: str) -> None:
    """One open deletion request per target; 'approved' (waiting for execution) counts as open."""
    op.drop_index("uq_deletion_requests_open_target", table_name="deletion_requests")
    op.create_index(
        "uq_deletion_requests_open_target",
        "deletion_requests",
        ["workspace_id", "target_type", "target_id"],
        unique=True,
        postgresql_where=sa.text(where),
    )


def _grant() -> None:
    plain = ", ".join(PLAIN_TABLES)

    # API: same as before for the new tables, but no soft-delete columns on files.
    op.execute(f'GRANT SELECT ON model_calls, workers TO "{APP}"')
    op.execute(f'REVOKE UPDATE ON files FROM "{APP}"')
    op.execute(f'GRANT UPDATE ({FILE_APP_UPDATE_COLUMNS}) ON files TO "{APP}"')

    # Workers: no DELETE, no sessions/auth_tokens/password hashes, no file soft delete.
    op.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{WORKER}"')
    op.execute(f'GRANT USAGE ON SCHEMA public TO "{WORKER}"')
    op.execute(f'GRANT SELECT ON {plain} TO "{WORKER}"')
    op.execute(f'GRANT SELECT ({USER_PUBLIC_COLUMNS}) ON users TO "{WORKER}"')
    op.execute(
        f"GRANT INSERT, UPDATE ON tasks, task_steps, jobs, approval_requests, artifacts, notifications, "
        f'usage_counters, workers TO "{WORKER}"'
    )
    op.execute(f'GRANT INSERT ON task_events, audit_events, model_calls TO "{WORKER}"')
    # The agent may propose a deletion (a request that needs its own approval); it cannot delete.
    op.execute(f'GRANT INSERT ON deletion_requests TO "{WORKER}"')
    op.execute(f'GRANT UPDATE (status, error_message, last_activity_at, updated_at) ON integrations TO "{WORKER}"')
    op.execute(f'GRANT UPDATE (last_run_at, next_run_at, updated_at) ON automations TO "{WORKER}"')
    op.execute(f'GRANT UPDATE (task_seq, approval_seq, updated_at) ON workspaces TO "{WORKER}"')
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON rate_limit_buckets TO "{WORKER}"')
    op.execute(f'GRANT SELECT ON alembic_version TO "{WORKER}"')

    # Deletion service: reads what it must revalidate; can only soft-delete files.
    op.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{DELETER}"')
    op.execute(f'GRANT USAGE ON SCHEMA public TO "{DELETER}"')
    op.execute(
        f"GRANT SELECT ON workspaces, workspace_memberships, files, deletion_requests, approval_requests, "
        f'approval_decisions, jobs, workers TO "{DELETER}"'
    )
    op.execute(f'GRANT SELECT ({USER_PUBLIC_COLUMNS}) ON users TO "{DELETER}"')
    op.execute(f'GRANT UPDATE (status, deleted_at, purge_after, updated_at) ON files TO "{DELETER}"')
    op.execute(f'GRANT UPDATE (status, executed_at, execution_result, updated_at) ON deletion_requests TO "{DELETER}"')
    op.execute(f'GRANT UPDATE (execution_state, updated_at) ON approval_requests TO "{DELETER}"')
    op.execute(f'GRANT UPDATE ON jobs, workers TO "{DELETER}"')
    op.execute(f'GRANT INSERT ON workers, audit_events, notifications TO "{DELETER}"')
    op.execute(f'GRANT SELECT ON alembic_version TO "{DELETER}"')

    # Read-only reporting role: no secrets.
    op.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{READONLY}"')
    op.execute(f'GRANT USAGE ON SCHEMA public TO "{READONLY}"')
    op.execute(f'GRANT SELECT ON {plain} TO "{READONLY}"')
    op.execute(f'GRANT SELECT ({USER_PUBLIC_COLUMNS}) ON users TO "{READONLY}"')


def downgrade() -> None:
    for role in (WORKER, DELETER, READONLY):
        op.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{role}"')
        op.execute(f'REVOKE ALL (id, email, name, timezone, notification_prefs, created_at) ON users FROM "{role}"')
    op.execute(f'REVOKE ALL ON files FROM "{APP}"')
    op.execute(f'GRANT SELECT, INSERT, UPDATE ON files TO "{APP}"')

    _open_deletion_index("status IN ('pending_approval','approved_blocked')")
    for table, suffix, _old, _new in CHECKS:
        op.drop_constraint(op.f(f"ck_{table}_{suffix}"), table, type_="check")
    op.create_check_constraint(
        op.f("ck_files_classification_valid"),
        "files",
        "classification IN ('private', 'approved_integration', 'public', 'internal', 'confidential', 'unknown')",
    )
    op.execute("UPDATE files SET classification = 'private' WHERE classification = 'confidential'")
    op.execute("UPDATE files SET classification = 'approved_integration' WHERE classification = 'internal'")
    op.drop_constraint(op.f("ck_files_classification_valid"), "files", type_="check")
    for table, suffix, old, _new in CHECKS:
        op.create_check_constraint(op.f(f"ck_{table}_{suffix}"), table, old)

    op.drop_column("integrations", "error_message")
    op.drop_column("integrations", "config")
    op.drop_column("files", "purge_after")
    op.drop_column("files", "deleted_at")
    op.drop_column("deletion_requests", "execution_result")
    op.drop_column("deletion_requests", "executed_at")
    op.create_check_constraint(
        op.f("ck_automations_schedule_disabled_until_scheduler"),
        "automations",
        "NOT (trigger = 'schedule' AND enabled)",
    )
    op.drop_index("ix_automations_due", table_name="automations")
    op.drop_column("automations", "next_run_at")
    op.drop_constraint("fk_artifacts_workspace_step", "artifacts", type_="foreignkey")
    for col in ("step_id", "sha256", "size_bytes", "content_type"):
        op.drop_column("artifacts", col)

    op.drop_constraint(op.f("fk_approval_requests_decided_by_users"), "approval_requests", type_="foreignkey")
    for col in ("decided_by", "policy_version", "targets", "args_hash", "operation", "step_id"):
        op.drop_column("approval_requests", col)

    for name in ("ck_jobs_attempts_valid", "ck_jobs_queue_valid", "ck_jobs_status_valid"):
        op.drop_constraint(op.f(name), "jobs", type_="check")
    op.drop_index("ix_jobs_claim", table_name="jobs")
    for col in (
        "step_id",
        "last_error",
        "finished_at",
        "heartbeat_at",
        "locked_at",
        "locked_by",
        "run_after",
        "max_attempts",
        "priority",
        "queue",
    ):
        op.drop_column("jobs", col)

    # Fails (rather than deleting rows) if a task has more than one plan version.
    op.drop_constraint(op.f("ck_task_steps_impact_valid"), "task_steps", type_="check")
    op.drop_constraint("fk_task_steps_workspace_approval", "task_steps", type_="foreignkey")
    op.drop_constraint("uq_task_steps_workspace_id_id", "task_steps", type_="unique")
    op.drop_constraint("uq_task_steps_task_version_position", "task_steps", type_="unique")
    op.create_unique_constraint("uq_task_steps_task_id_position", "task_steps", ["task_id", "position"])
    for col in (
        "approval_id",
        "error",
        "output",
        "attempts",
        "max_attempts",
        "timeout_seconds",
        "expected_output",
        "idempotent",
        "policy",
        "impact",
        "destinations",
        "classifications",
        "permissions",
        "args_hash",
        "args",
        "tool_id",
        "step_key",
        "plan_version",
    ):
        op.drop_column("task_steps", col)

    op.drop_constraint(op.f("ck_tasks_data_classification_valid"), "tasks", type_="check")
    for col in ("finished_at", "started_at", "plan_summary", "data_classification", "plan_version"):
        op.drop_column("tasks", col)

    op.drop_index("ix_model_calls_ws_created", table_name="model_calls")
    op.drop_table("model_calls")
    op.drop_table("workers")
