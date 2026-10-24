"""Read-only tools over files attached to the task. Files are read from private storage by the
tools worker; only small, redacted statistics and previews are stored as step output."""

from __future__ import annotations

import csv
import io
import re
import uuid
from collections import Counter

from pydantic import Field

from app.adapters.storage import LocalPrivateFileStorage
from app.domain.enums import StepRisk
from app.engine.redaction import redact
from app.engine.tools.base import (
    FileInfo,
    PlanEnv,
    ToolArgs,
    ToolContext,
    ToolDefinition,
    ToolError,
    ToolResult,
    const,
    no_destinations,
)

TEXT_TYPES = {"CSV", "TXT", "MD", "JSON"}
MAX_READ_BYTES = 5 * 1024 * 1024


class FileArgs(ToolArgs):
    file_id: uuid.UUID


def _file_class(a: ToolArgs, e: PlanEnv) -> list[str]:
    assert isinstance(a, FileArgs)
    f = e.attached_files.get(a.file_id)
    return [f.classification] if f else ["unknown"]


def _load(ctx: ToolContext, file_id: uuid.UUID) -> tuple[FileInfo, str]:
    f = ctx.env.attached_files.get(file_id)
    if f is None:
        raise ToolError("file_not_attached", "Only files attached to this task can be read.")
    if f.deleted:
        raise ToolError("file_deleted", f"{f.name} has been deleted.")
    if f.status not in ("ready", "unscanned"):
        raise ToolError("file_not_ready", f"{f.name} can't be read (status: {f.status}).")
    if f.type_label not in TEXT_TYPES:
        raise ToolError(
            "unsupported_type", f"{f.type_label} files can't be analysed yet (text, CSV, Markdown and JSON only)."
        )
    path = LocalPrivateFileStorage(ctx.settings.storage_dir).local_path(f.storage_key)
    with path.open("rb") as fh:
        raw = fh.read(MAX_READ_BYTES + 1)
    return f, raw[:MAX_READ_BYTES].decode("utf-8", errors="replace")


def _clip(value: str, n: int = 60) -> str:
    v = redact(value).text.replace("\n", " ")
    return v if len(v) <= n else v[: n - 1] + "…"


def run_read(ctx: ToolContext, args: ToolArgs) -> ToolResult:
    assert isinstance(args, FileArgs)
    f, text = _load(ctx, args.file_id)
    preview = redact(text[:2000])
    lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    return ToolResult(
        summary=f"Read {f.name}: {lines} lines, {len(text.split())} words",
        output={
            "file": f.name,
            "lines": lines,
            "words": len(text.split()),
            "characters": len(text),
            "preview": preview.text,
            "redactions": preview.count,
        },
        classification=f.classification,
    )


def run_analyze(ctx: ToolContext, args: ToolArgs) -> ToolResult:
    assert isinstance(args, FileArgs)
    f, text = _load(ctx, args.file_id)
    if f.type_label == "CSV":
        try:
            rows = list(csv.reader(io.StringIO(text)))
        except csv.Error as e:
            raise ToolError("invalid_csv", f"{f.name} is not valid CSV ({e}).") from None
        if not rows:
            raise ToolError("empty_file", f"{f.name} has no rows.")
        header, data = rows[0], rows[1:50_001]
        columns = []
        for i, name in enumerate(header[:50]):
            values = [r[i] if i < len(r) else "" for r in data]
            empty = sum(1 for v in values if not v.strip())
            top = Counter(v for v in values if v.strip()).most_common(3)
            numeric = [float(v) for v in values if re.fullmatch(r"-?\d+(\.\d+)?", v.strip() or "x")]
            col: dict[str, object] = {
                "name": _clip(name, 40),
                "empty": empty,
                "distinct": len({v for v in values if v.strip()}),
                "top_values": [{"value": _clip(v), "count": c} for v, c in top],
            }
            if numeric and len(numeric) >= len(values) * 0.8:
                col.update(min=min(numeric), max=max(numeric), mean=round(sum(numeric) / len(numeric), 3))
            columns.append(col)
        issues = [
            f"{c['name']}: {c['empty']} empty cells" for c in columns if isinstance(c["empty"], int) and c["empty"]
        ]
        return ToolResult(
            summary=f"Analysed {f.name}: {len(data)} rows x {len(header)} columns, {len(issues)} columns with empty cells",
            output={"file": f.name, "kind": "csv", "rows": len(data), "columns": columns, "issues": issues[:20]},
            classification=f.classification,
        )
    words = re.findall(r"[A-Za-z][A-Za-z'-]{3,}", text.lower())
    top_words = Counter(words).most_common(10)
    return ToolResult(
        summary=f"Analysed {f.name}: {len(text.splitlines())} lines, {len(words)} words",
        output={
            "file": f.name,
            "kind": "text",
            "lines": len(text.splitlines()),
            "words": len(words),
            "top_words": [{"word": w, "count": c} for w, c in top_words],
        },
        classification=f.classification,
    )


FILES_READ = ToolDefinition(
    id="files.read",
    label="Read an attached file",
    description="Reads a text, CSV, Markdown or JSON file attached to this task and returns a short redacted preview.",
    args_model=FileArgs,
    risk=StepRisk.read_only,
    permissions=("files.read",),
    impact=const("none"),
    classifications=_file_class,
    destinations=no_destinations,
    run=run_read,
    timeout_seconds=30,
    args_hint={"file_id": "id of a file attached to the task"},
)

FILES_ANALYZE = ToolDefinition(
    id="files.analyze",
    label="Analyse an attached file",
    description="Counts rows, columns, empty cells and frequent values in an attached CSV or text file.",
    args_model=FileArgs,
    risk=StepRisk.read_only,
    permissions=("files.read",),
    impact=const("none"),
    classifications=_file_class,
    destinations=no_destinations,
    run=run_analyze,
    timeout_seconds=60,
    args_hint={"file_id": "id of a file attached to the task"},
)


class DeletionArgs(ToolArgs):
    file_id: uuid.UUID
    reason: str = Field(min_length=3, max_length=300)


def run_request_deletion(ctx: ToolContext, args: ToolArgs) -> ToolResult:
    from app.services.approvals import file_deletion_request

    assert isinstance(args, DeletionArgs)
    f = ctx.env.attached_files.get(args.file_id)
    if f is None or f.deleted:
        raise ToolError("file_not_attached", "Only files attached to this task can be proposed for deletion.")
    approval = file_deletion_request(
        ctx.db,
        workspace_id=ctx.workspace_id,
        requested_by=ctx.requested_by,
        actor_user_id=None,
        file_id=f.id,
        reason=f"Proposed by the agent for task step {ctx.step_key}: {args.reason}",
        task_id=ctx.task_id,
    )
    return ToolResult(
        summary=f"Deletion of {f.name} requested — waiting for a separate approval. Nothing was deleted.",
        output={"file": f.name, "approval_id": str(approval.id), "deleted": False},
        classification="internal",
    )


FILES_REQUEST_DELETION = ToolDefinition(
    id="files.request_deletion",
    label="Request deletion of a file",
    description="Creates a deletion request for an attached file. It never deletes: deletion needs its own approval and runs in the deletion service.",
    args_model=DeletionArgs,
    risk=StepRisk.workspace_only,
    permissions=("files.request_deletion",),
    impact=const("delete"),
    classifications=lambda a, e: ["internal"],
    destinations=no_destinations,
    run=run_request_deletion,
    idempotent=False,
    max_attempts=1,
    args_hint={"file_id": "id of an attached file", "reason": "why it should be deleted"},
)
