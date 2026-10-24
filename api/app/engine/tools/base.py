"""Tool registry types. A tool declares — in code, never from model output — its argument
schema, impact, permissions, data classifications and destinations."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.enums import DataClass, StepRisk


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ToolError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class FileInfo:
    id: uuid.UUID
    name: str
    classification: str
    type_label: str
    status: str
    deleted: bool
    size_bytes: int
    sha256: str
    storage_key: str


@dataclass(frozen=True)
class ProviderView:
    configured: bool
    location: str  # local | external
    label: str


@dataclass(frozen=True)
class PlanEnv:
    """Server-side facts used to derive a step's policy fields. Never from the model."""

    workspace_id: uuid.UUID
    task_classification: str
    attached_files: dict[uuid.UUID, FileInfo]
    allowed_domains: list[str]
    privacy_mode: str
    tool_permissions: dict[str, bool]
    ai_rules: dict[str, bool]
    provider: ProviderView
    wordpress_site: str | None  # connected site URL, if any
    step_outputs_classification: dict[str, str] = field(default_factory=dict)  # step_key -> class


@dataclass
class ArtifactOut:
    name: str
    kind: str
    content: bytes
    content_type: str
    provenance: str  # ai_generated | verified_result


@dataclass
class ToolResult:
    summary: str  # one line for the task log
    output: dict[str, Any]
    classification: str
    artifact: ArtifactOut | None = None


@dataclass
class ToolContext:
    db: Session
    settings: Settings
    workspace_id: uuid.UUID
    task_id: uuid.UUID
    step_id: uuid.UUID
    step_key: str
    task_title: str
    task_prompt: str
    requested_by: uuid.UUID
    env: PlanEnv
    previous_outputs: dict[str, dict[str, Any]]  # step_key -> output (done steps of this plan version)
    is_cancelled: Callable[[], bool]
    external_transfer_authorised: bool


@dataclass(frozen=True)
class ToolDefinition:
    id: str
    label: str
    description: str
    args_model: type[ToolArgs]
    risk: StepRisk
    permissions: tuple[str, ...]
    impact: Callable[[ToolArgs, PlanEnv], str]
    classifications: Callable[[ToolArgs, PlanEnv], list[str]]
    destinations: Callable[[ToolArgs, PlanEnv], list[str]]
    run: Callable[[ToolContext, ToolArgs], ToolResult] | None
    setting_key: str | None = None  # workspace tool_permissions switch that must be on
    idempotent: bool = True
    timeout_seconds: int = 60
    max_attempts: int = 2
    network: bool = False
    available: Callable[[Settings], tuple[bool, str]] = field(default=lambda s: (True, ""))
    args_hint: dict[str, str] = field(default_factory=dict)

    def catalog_entry(self, settings: Settings, enabled: bool) -> dict[str, Any]:
        ok, reason = self.available(settings)
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "args": self.args_hint,
            "available": ok and enabled,
            "unavailable_reason": None if ok and enabled else (reason or "Turned off in workspace settings."),
        }


def const(value: str) -> Callable[[ToolArgs, PlanEnv], str]:
    return lambda _a, _e: value


def no_destinations(_a: ToolArgs, _e: PlanEnv) -> list[str]:
    return []


def task_text_class(_a: ToolArgs, e: PlanEnv) -> list[str]:
    return [e.task_classification]


def public_only(_a: ToolArgs, _e: PlanEnv) -> list[str]:
    return [DataClass.public.value]
