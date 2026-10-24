"""Close tenant-FK gaps (SR-7) and give event tables a strict insertion order (SR-13).

Additive only: adds constraints and identity columns; no data is changed or removed.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_automations_workspace_id_id", "automations", ["workspace_id", "id"])
    op.create_foreign_key(
        "fk_tasks_workspace_automation",
        "tasks",
        "automations",
        ["workspace_id", "automation_id"],
        ["workspace_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_jobs_workspace_task",
        "jobs",
        "tasks",
        ["workspace_id", "task_id"],
        ["workspace_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_audit_events_workspace_task",
        "audit_events",
        "tasks",
        ["workspace_id", "task_id"],
        ["workspace_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_deletion_requests_workspace_file",
        "deletion_requests",
        "files",
        ["workspace_id", "target_id"],
        ["workspace_id", "id"],
        ondelete="RESTRICT",
    )
    for table in ("task_events", "audit_events"):
        op.add_column(table, sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False))
        op.create_unique_constraint(f"uq_{table}_seq", table, ["seq"])


def downgrade() -> None:
    for table in ("audit_events", "task_events"):
        op.drop_constraint(f"uq_{table}_seq", table, type_="unique")
        op.drop_column(table, "seq")
    op.drop_constraint("fk_deletion_requests_workspace_file", "deletion_requests", type_="foreignkey")
    op.drop_constraint("fk_audit_events_workspace_task", "audit_events", type_="foreignkey")
    op.drop_constraint("fk_jobs_workspace_task", "jobs", type_="foreignkey")
    op.drop_constraint("fk_tasks_workspace_automation", "tasks", type_="foreignkey")
    op.drop_constraint("uq_automations_workspace_id_id", "automations", type_="unique")
