"""Interfaces (ports) between the application core and replaceable infrastructure.

Phase 2 ships safe adapters (app/adapters). Phase 3 replaces them with the real
planner, model providers, queue workers and tool registry without changing the
HTTP layer, the UI or the database schema.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, BinaryIO, Protocol

# ------------------------------------------------------------------ planning / execution


@dataclass(frozen=True)
class PlannedStep:
    title: str
    description: str
    tool: str
    risk: str  # StepRisk value
    requires_approval: bool


@dataclass(frozen=True)
class Plan:
    steps: list[PlannedStep]
    data_sources: list[str] = field(default_factory=list)
    destination: str | None = None


@dataclass(frozen=True)
class PlanningRequest:
    workspace_id: uuid.UUID
    task_id: uuid.UUID
    prompt: str
    task_type: str
    mode: str
    attachment_ids: list[uuid.UUID]


class TaskPlanner(Protocol):
    """Turns a task request into a reviewable plan. Never executes anything."""

    def is_available(self) -> bool: ...
    def plan(self, request: PlanningRequest) -> Plan: ...


class ModelProvider(Protocol):
    """An external or local AI model. Phase 2 has none; files must never be sent without approval."""

    name: str

    def is_configured(self) -> bool: ...
    def complete(self, prompt: str, *, max_tokens: int) -> str: ...


@dataclass(frozen=True)
class EnqueueResult:
    job_id: uuid.UUID | None
    dispatched: bool  # False in Phase 2: recorded in the outbox, no worker installed
    reason: str


class JobQueue(Protocol):
    def enqueue(
        self,
        *,
        workspace_id: uuid.UUID,
        kind: str,
        task_id: uuid.UUID | None,
        payload: dict[str, Any],
        dedupe_key: str | None,
    ) -> EnqueueResult: ...


class Worker(Protocol):
    """Consumes jobs. Not installed in Phase 2."""

    def run_once(self) -> int: ...


@dataclass(frozen=True)
class ToolSpec:
    key: str
    label: str
    risk: str
    requires_approval: bool


class ToolRegistry(Protocol):
    def list_tools(self) -> list[ToolSpec]: ...
    def get(self, key: str) -> ToolSpec | None: ...


# ------------------------------------------------------------------ policy


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    requires_approval: bool
    reason: str


@dataclass(frozen=True)
class ProposedAction:
    workspace_id: uuid.UUID
    category: str  # ApprovalCategory value
    data_leaves_workspace: bool
    destination: str
    file_classifications: list[str]


class ApprovalPolicy(Protocol):
    def evaluate(self, action: ProposedAction) -> PolicyDecision: ...


# ------------------------------------------------------------------ audit, files, mail


@dataclass(frozen=True)
class AuditRecord:
    action: str
    category: str
    message: str
    workspace_id: uuid.UUID | None = None
    actor_user_id: uuid.UUID | None = None
    target_type: str | None = None
    target_id: str | None = None
    task_id: uuid.UUID | None = None
    ip: str | None = None
    request_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AuditLogger(Protocol):
    def record(self, rec: AuditRecord) -> None: ...


@dataclass(frozen=True)
class StoredObject:
    key: str
    size_bytes: int
    sha256: str
    head: bytes  # first bytes, for content sniffing


class FileStorage(Protocol):
    """Private object storage. Keys are generated server-side; client names are never paths."""

    def save(self, workspace_id: uuid.UUID, stream: BinaryIO, max_bytes: int) -> StoredObject: ...
    def open(self, key: str) -> Iterator[bytes]: ...
    def exists(self, key: str) -> bool: ...
    def quarantine(self, key: str) -> None: ...
    def discard_incomplete(self, key: str) -> None: ...


class FileScanner(Protocol):
    def is_configured(self) -> bool: ...
    def scan(self, key: str) -> str: ...  # ScanStatus value


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str


class Mailer(Protocol):
    def send(self, msg: EmailMessage) -> None: ...
