"""Phase 2 adapters: safe, honest implementations of the ports.

Nothing here plans, executes, calls an AI provider, or scans files. Each adapter
says plainly that the capability is not configured.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import Job
from app.ports import (
    EnqueueResult,
    Plan,
    PlanningRequest,
    PolicyDecision,
    ProposedAction,
    ToolSpec,
)


class UnavailablePlanner:
    """No planning service is installed. Tasks wait in `queued` with waiting_for=planning_service."""

    def is_available(self) -> bool:
        return False

    def plan(self, request: PlanningRequest) -> Plan:
        raise ApiError(503, "planner_not_configured", "The planning service is not installed yet.")


class NoModelProvider:
    name = "none"

    def is_configured(self) -> bool:
        return False

    def complete(self, prompt: str, *, max_tokens: int) -> str:
        raise ApiError(503, "model_provider_not_configured", "No AI model provider is configured.")


class OutboxJobQueue:
    """Records jobs in the `jobs` table for Phase 3 workers. Nothing consumes them yet."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def enqueue(
        self,
        *,
        workspace_id: uuid.UUID,
        kind: str,
        task_id: uuid.UUID | None,
        payload: dict[str, Any],
        dedupe_key: str | None,
    ) -> EnqueueResult:
        stmt = (
            insert(Job)
            .values(workspace_id=workspace_id, kind=kind, task_id=task_id, payload=payload, dedupe_key=dedupe_key)
            .on_conflict_do_nothing(constraint="uq_jobs_workspace_dedupe")
            .returning(Job.id)
        )
        job_id = self.db.execute(stmt).scalar_one_or_none()
        if job_id is None and dedupe_key is not None:
            job_id = self.db.execute(
                select(Job.id).where(Job.workspace_id == workspace_id, Job.dedupe_key == dedupe_key)
            ).scalar_one_or_none()
        return EnqueueResult(job_id=job_id, dispatched=False, reason="no_worker_installed")


class RequireApprovalPolicy:
    """Conservative placeholder: anything that leaves the workspace or changes something needs approval;
    files that are not classified are blocked from leaving. Not yet wired to an execution engine."""

    def evaluate(self, action: ProposedAction) -> PolicyDecision:
        if action.data_leaves_workspace and any(c in ("unknown", "private") for c in action.file_classifications):
            return PolicyDecision(False, True, "Private or unclassified files cannot leave the workspace.")
        return PolicyDecision(True, True, "Every sensitive action needs a one-time approval.")


class StaticToolRegistry:
    _TOOLS = [
        ToolSpec("wordpress.read", "WordPress (read-only)", "read_only", False),
        ToolSpec("wordpress.write", "WordPress (write)", "production_change", True),
        ToolSpec("browser", "Browser runtime", "read_only", False),
        ToolSpec("analysis", "Agent analysis", "workspace_only", False),
        ToolSpec("email.send", "Email", "external_transfer", True),
    ]

    def list_tools(self) -> list[ToolSpec]:
        return list(self._TOOLS)

    def get(self, key: str) -> ToolSpec | None:
        return next((t for t in self._TOOLS if t.key == key), None)


class NotConfiguredScanner:
    def is_configured(self) -> bool:
        return False

    def scan(self, key: str) -> str:
        return "not_configured"


class NoWorker:
    def run_once(self) -> int:
        return 0


planner = UnavailablePlanner()
model_provider = NoModelProvider()
approval_policy = RequireApprovalPolicy()
tool_registry = StaticToolRegistry()
scanner = NotConfiguredScanner()
