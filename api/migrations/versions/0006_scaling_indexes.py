"""Indexes found by the Phase 4 query review (additive; CONCURRENTLY not used because
Alembic runs in a transaction — on a large live table create them manually with
CREATE INDEX CONCURRENTLY first, then stamp this revision).

- audit_events (workspace_id, seq): the activity feed orders by seq within one workspace.
- task_events (task_id, seq): the task timeline orders by seq.
- jobs partial index for claiming pending work; jobs (workspace_id, status) for backpressure counts.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_audit_ws_seq", "audit_events", ["workspace_id", "seq"])
    op.create_index("ix_task_events_task_seq", "task_events", ["task_id", "seq"])
    op.create_index(
        "ix_jobs_pending_claim", "jobs", ["queue", "priority", "run_after"], postgresql_where=sa.text("status = 'pending'")
    )
    op.create_index("ix_jobs_ws_status", "jobs", ["workspace_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_jobs_ws_status", table_name="jobs")
    op.drop_index("ix_jobs_pending_claim", table_name="jobs")
    op.drop_index("ix_task_events_task_seq", table_name="task_events")
    op.drop_index("ix_audit_ws_seq", table_name="audit_events")
