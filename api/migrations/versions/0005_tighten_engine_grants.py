"""Tighten agent-engine privileges (security review P3-SR-5, P3-SR-11).

- steward_worker: approval_requests INSERT + UPDATE(execution_state, updated_at) only;
  tasks UPDATE limited to engine-managed columns (not data_classification, prompt, owner...).
- A trigger keeps approvals one-time for every role: execution_state only moves forward
  (not_executed → pending_execution → executed/invalidated/execution_failed; executed → invalidated),
  and a decided status can never change again.
- No role may insert a file row that is already deleted (only the deletion service soft-deletes,
  by UPDATE, which steward_app is not allowed to do).

Additive: no data changes.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-24
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORKER = os.environ.get("DB_WORKER_ROLE", "steward_worker").replace('"', "")

TASK_ENGINE_COLUMNS = (
    "status, waiting_for, question, error_message, report, plan_meta, plan_version, plan_summary, "
    "started_at, finished_at, updated_at"
)


def upgrade() -> None:
    op.execute(f'REVOKE INSERT, UPDATE ON approval_requests FROM "{WORKER}"')
    op.execute(f'GRANT INSERT ON approval_requests TO "{WORKER}"')
    op.execute(f'GRANT UPDATE (execution_state, updated_at) ON approval_requests TO "{WORKER}"')
    op.execute(f'REVOKE UPDATE ON tasks FROM "{WORKER}"')
    op.execute(f'GRANT UPDATE ({TASK_ENGINE_COLUMNS}) ON tasks TO "{WORKER}"')

    op.execute("""
    CREATE OR REPLACE FUNCTION steward_reject_predeleted_file() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.deleted_at IS NOT NULL OR NEW.purge_after IS NOT NULL THEN
        RAISE EXCEPTION 'files are soft-deleted only by the deletion service' USING ERRCODE = 'insufficient_privilege';
      END IF;
      RETURN NEW;
    END $$;
    """)
    op.execute("""
    CREATE TRIGGER files_no_predeleted_insert
      BEFORE INSERT ON files
      FOR EACH ROW EXECUTE FUNCTION steward_reject_predeleted_file();
    """)

    op.execute("""
    CREATE OR REPLACE FUNCTION steward_guard_approval_update() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.status <> 'pending' AND NEW.status IS DISTINCT FROM OLD.status THEN
        RAISE EXCEPTION 'approval % is already decided', OLD.id USING ERRCODE = 'insufficient_privilege';
      END IF;
      IF NEW.execution_state IS DISTINCT FROM OLD.execution_state AND NOT (
           (OLD.execution_state = 'not_executed' AND NEW.execution_state = 'pending_execution' AND NEW.status = 'approved')
        OR (OLD.execution_state = 'pending_execution' AND NEW.execution_state IN ('executed', 'invalidated', 'execution_failed'))
        OR (OLD.execution_state = 'executed' AND NEW.execution_state = 'invalidated')
      ) THEN
        RAISE EXCEPTION 'approval % execution state cannot go from % to %', OLD.id, OLD.execution_state, NEW.execution_state
          USING ERRCODE = 'insufficient_privilege';
      END IF;
      RETURN NEW;
    END $$;
    """)
    op.execute("""
    CREATE TRIGGER approval_requests_one_time
      BEFORE UPDATE ON approval_requests
      FOR EACH ROW EXECUTE FUNCTION steward_guard_approval_update();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS approval_requests_one_time ON approval_requests")
    op.execute("DROP FUNCTION IF EXISTS steward_guard_approval_update()")
    op.execute("DROP TRIGGER IF EXISTS files_no_predeleted_insert ON files")
    op.execute("DROP FUNCTION IF EXISTS steward_reject_predeleted_file()")
    op.execute(f'REVOKE UPDATE ON tasks FROM "{WORKER}"')
    op.execute(f'GRANT INSERT, UPDATE ON tasks TO "{WORKER}"')
    op.execute(f'REVOKE INSERT, UPDATE ON approval_requests FROM "{WORKER}"')
    op.execute(f'GRANT INSERT, UPDATE ON approval_requests TO "{WORKER}"')
