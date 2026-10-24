"""Least-privilege grants for the application role and append-only guards.

- steward_app: SELECT/INSERT/UPDATE on application tables, no DELETE anywhere
  except rate_limit_buckets (expired counters). No TRUNCATE, no DDL.
- Append-only tables (audit_events, approval_decisions, task_events): SELECT/INSERT only.
- A trigger rejects UPDATE/DELETE/TRUNCATE on audit_events for every role, so even
  the schema owner needs an explicit, reviewed migration to change history.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = os.environ.get("DB_APP_ROLE", "steward_app")

READ_WRITE = [
    "users",
    "workspaces",
    "workspace_memberships",
    "sessions",
    "auth_tokens",
    "tasks",
    "task_steps",
    "task_attachments",
    "jobs",
    "approval_requests",
    "deletion_requests",
    "files",
    "integrations",
    "automations",
    "artifacts",
    "notifications",
    "usage_counters",
    "account_requests",
]
APPEND_ONLY = ["audit_events", "approval_decisions", "task_events"]


def upgrade() -> None:
    role = APP_ROLE.replace('"', "")
    op.execute(f"""
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
        RAISE EXCEPTION 'Application role {role} does not exist. Run deploy/db/init-roles.sh first.';
      END IF;
    END $$;
    """)
    op.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{role}"')
    op.execute(f'GRANT SELECT, INSERT, UPDATE ON {", ".join(READ_WRITE)} TO "{role}"')
    op.execute(f'GRANT SELECT, INSERT ON {", ".join(APPEND_ONLY)} TO "{role}"')
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON rate_limit_buckets TO "{role}"')
    op.execute(f'GRANT SELECT ON alembic_version TO "{role}"')

    op.execute("""
    CREATE OR REPLACE FUNCTION steward_reject_audit_change() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
      RAISE EXCEPTION 'audit_events is append-only (% blocked)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
    END $$;
    """)
    op.execute("""
    CREATE TRIGGER audit_events_append_only
      BEFORE UPDATE OR DELETE ON audit_events
      FOR EACH ROW EXECUTE FUNCTION steward_reject_audit_change();
    """)
    op.execute("""
    CREATE TRIGGER audit_events_no_truncate
      BEFORE TRUNCATE ON audit_events
      FOR EACH STATEMENT EXECUTE FUNCTION steward_reject_audit_change();
    """)


def downgrade() -> None:
    role = APP_ROLE.replace('"', "")
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_truncate ON audit_events")
    op.execute("DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS steward_reject_audit_change()")
    op.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{role}"')
