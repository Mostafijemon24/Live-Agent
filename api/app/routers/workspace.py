"""Tenant-scoped resource routes. Every handler receives a Context resolved from the session."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Header, Query, Response, UploadFile
from fastapi.responses import StreamingResponse

from app import schemas as S
from app.core import ratelimit as RL
from app.core.deps import Context, get_context, parse_uuid
from app.core.errors import ApiError
from app.domain.enums import FileClassification, FileStatus, TaskStatus, TaskType, WorkspaceRole
from app.services import agent as AG
from app.services import approvals as A
from app.services import files as F
from app.services import tasks as T
from app.services import workspace as W
from app.services.usage import usage_report

router = APIRouter()
Ctx = Annotated[Context, Depends(get_context)]


# Role matrix (see SECURITY_AND_PRIVACY.md): viewer = read-only; member = day-to-day work;
# owner/admin = anything that approves, shares, schedules or changes workspace policy.
def _writer(ctx: Ctx) -> Context:
    ctx.require_role(WorkspaceRole.owner, WorkspaceRole.admin, WorkspaceRole.member)
    return ctx


def _admin(ctx: Ctx) -> Context:
    ctx.require_role(WorkspaceRole.owner, WorkspaceRole.admin)
    return ctx


Writer = Annotated[Context, Depends(_writer)]
Admin = Annotated[Context, Depends(_admin)]
PageQ = Annotated[int, Query(ge=1, le=10_000)]


def _write_limit(ctx: Context) -> None:
    RL.hit(RL.WRITE_USER, str(ctx.user.id))


# ------------------------------------------------------------------ dashboard
@router.get("/agent/status", response_model=S.AgentStatusOut)
def agent_status(ctx: Ctx) -> S.AgentStatusOut:
    return AG.agent_status(ctx)


@router.get("/agent/tools", response_model=list[S.ToolOut])
def agent_tools(ctx: Ctx) -> list[S.ToolOut]:
    return AG.tools_out(ctx)


@router.get("/dashboard", response_model=S.DashboardOut)
def dashboard(ctx: Ctx) -> S.DashboardOut:
    return W.dashboard(ctx)


# ------------------------------------------------------------------ tasks
@router.get("/tasks", response_model=S.Page[S.TaskSummaryOut])
def list_tasks(
    ctx: Ctx,
    q: Annotated[str | None, Query(max_length=200)] = None,
    status: TaskStatus | None = None,
    type: TaskType | None = None,
    created: Literal["today", "3d"] | None = None,
    integration: Annotated[str | None, Query(max_length=32)] = None,
    sort: Literal["updated", "created", "title"] = "updated",
    page: PageQ = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> S.Page[S.TaskSummaryOut]:
    return T.list_tasks(ctx, q, status, type.value if type else None, created, integration, sort, page, page_size)


@router.post("/tasks", response_model=S.TaskOut, status_code=201)
def create_task(
    body: S.CreateTaskIn,
    ctx: Writer,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=80)] = None,
) -> S.TaskOut:
    RL.hit(RL.TASK_CREATE_USER, str(ctx.user.id))
    out, created = T.create_task(ctx, body, idempotency_key)
    if not created:
        response.status_code = 200
    return out


@router.get("/tasks/{task_id}", response_model=S.TaskOut)
def get_task(task_id: str, ctx: Ctx) -> S.TaskOut:
    from app.services.views import task_full

    return task_full(ctx.db, T.get_task(ctx, parse_uuid(task_id, "task")))


@router.post("/tasks/{task_id}/cancel", response_model=S.TaskOut)
def cancel_task(task_id: str, ctx: Writer, body: S.CancelIn | None = None) -> S.TaskOut:
    _write_limit(ctx)
    return T.cancel(ctx, parse_uuid(task_id, "task"), body.reason if body else None)


@router.post("/tasks/{task_id}/pause", response_model=S.TaskOut)
def pause_task(task_id: str, ctx: Writer) -> S.TaskOut:
    _write_limit(ctx)
    return T.pause(ctx, parse_uuid(task_id, "task"))


@router.post("/tasks/{task_id}/resume", response_model=S.TaskOut)
def resume_task(task_id: str, ctx: Writer) -> S.TaskOut:
    _write_limit(ctx)
    return T.resume(ctx, parse_uuid(task_id, "task"))


@router.post("/tasks/{task_id}/messages", response_model=S.TaskOut)
def task_message(task_id: str, body: S.TaskMessageIn, ctx: Writer) -> S.TaskOut:
    _write_limit(ctx)
    return T.message(ctx, parse_uuid(task_id, "task"), body.text, body.kind)


@router.post("/tasks/{task_id}/plan/approve", response_model=S.TaskOut)
def approve_plan(task_id: str, body: S.ApprovePlanIn, ctx: Admin) -> S.TaskOut:
    _write_limit(ctx)
    return T.approve_plan(ctx, parse_uuid(task_id, "task"), body.selected_step_ids)


@router.post("/tasks/{task_id}/plan/reject", response_model=S.TaskOut)
def reject_plan(task_id: str, body: S.RejectPlanIn, ctx: Admin) -> S.TaskOut:
    _write_limit(ctx)
    return T.reject_plan(ctx, parse_uuid(task_id, "task"), body.note)


@router.get("/tasks/{task_id}/events", response_model=S.Page[S.TaskEventOut])
def task_events(
    task_id: str, ctx: Ctx, page: PageQ = 1, page_size: Annotated[int, Query(ge=1, le=200)] = 100
) -> S.Page[S.TaskEventOut]:
    return T.list_events(ctx, parse_uuid(task_id, "task"), page, page_size)


# ------------------------------------------------------------------ approvals
@router.get("/approvals", response_model=S.ApprovalPage)
def list_approvals(
    ctx: Ctx,
    status: Literal["pending", "decided", "all"] = "pending",
    page: PageQ = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> S.ApprovalPage:
    return A.list_approvals(ctx, status, page, page_size)


@router.get("/approvals/{approval_id}", response_model=S.ApprovalOut)
def get_approval(approval_id: str, ctx: Ctx) -> S.ApprovalOut:
    from app.services.views import approvals_out

    a = A.get_approval(ctx, parse_uuid(approval_id, "approval request"))
    return approvals_out(ctx.db, ctx.workspace.id, [a])[0]


@router.post("/approvals/{approval_id}/decision", response_model=S.ApprovalOut)
def decide(approval_id: str, body: S.DecisionIn, ctx: Admin) -> S.ApprovalOut:
    _write_limit(ctx)
    return A.decide(ctx, parse_uuid(approval_id, "approval request"), body)


# ------------------------------------------------------------------ files
@router.get("/files/limits", response_model=S.UploadLimitsOut)
def file_limits(ctx: Ctx) -> S.UploadLimitsOut:
    return F.limits()


@router.get("/files", response_model=S.FilePage)
def list_files(
    ctx: Ctx,
    q: Annotated[str | None, Query(max_length=200)] = None,
    collection: Annotated[str | None, Query(max_length=80)] = None,
    classification: FileClassification | None = None,
    status: FileStatus | None = None,
    page: PageQ = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    deleted: bool = False,
) -> S.FilePage:
    return F.list_files(
        ctx,
        q,
        collection,
        classification.value if classification else None,
        status.value if status else None,
        page,
        page_size,
        deleted,
    )


@router.post("/files", response_model=S.FileOut, status_code=201)
def upload_file(
    ctx: Writer, file: Annotated[UploadFile, File()], collection: Annotated[str, Form(max_length=80)] = "Research"
) -> S.FileOut:
    RL.hit(RL.UPLOAD_USER, str(ctx.user.id))
    if not file.filename:
        raise ApiError(
            422,
            "validation_error",
            "Choose a file to upload.",
            details=[{"field": "file", "message": "Choose a file."}],
        )
    return F.upload(ctx, file.file, file.filename, collection)


@router.get("/files/{file_id}", response_model=S.FileOut)
def get_file(file_id: str, ctx: Ctx) -> S.FileOut:
    from app.services.views import files_out

    return files_out(ctx.db, ctx.workspace.id, [F.get_file(ctx, parse_uuid(file_id, "file"))])[0]


@router.patch("/files/{file_id}", response_model=S.FileOut)
def patch_file(file_id: str, body: S.FilePatchIn, ctx: Admin) -> S.FileOut:
    _write_limit(ctx)
    return F.patch(ctx, parse_uuid(file_id, "file"), body)


@router.get("/files/{file_id}/download")
def download_file(file_id: str, ctx: Ctx) -> StreamingResponse:
    f, chunks = F.download(ctx, parse_uuid(file_id, "file"))
    ctx.db.commit()  # persist the audit event before streaming
    return _attachment(f.original_name, chunks)


def _attachment(name: str, chunks: Iterator[bytes]) -> StreamingResponse:
    # Always an attachment with a generic type: the browser must never render stored content inline.
    ascii_name = "".join(ch if 32 <= ord(ch) < 127 and ch not in '"\\' else "_" for ch in name)
    return StreamingResponse(
        chunks,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{ascii_name}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
        },
    )


@router.post("/files/{file_id}/restore", response_model=S.FileOut, status_code=202)
def restore_file(file_id: str, ctx: Admin) -> S.FileOut:
    _write_limit(ctx)
    return AG.restore_file(ctx, parse_uuid(file_id, "file"))


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: str, ctx: Ctx) -> StreamingResponse:
    name, chunks = F.artifact_download(ctx, parse_uuid(artifact_id, "artifact"))
    ctx.db.commit()
    return _attachment(name, chunks)


@router.post("/files/{file_id}/deletion-request", response_model=S.ApprovalOut, status_code=201)
def file_deletion_request(file_id: str, body: S.DeletionRequestIn, ctx: Writer) -> S.ApprovalOut:
    _write_limit(ctx)
    f = F.get_file(ctx, parse_uuid(file_id, "file"))
    return A.request_file_deletion(ctx, f, body.reason)


# ------------------------------------------------------------------ automations
@router.get("/automations", response_model=list[S.AutomationOut])
def list_automations(ctx: Ctx) -> list[S.AutomationOut]:
    return W.list_automations(ctx)


@router.post("/automations", response_model=S.AutomationOut, status_code=201)
def create_automation(body: S.CreateAutomationIn, ctx: Admin) -> S.AutomationOut:
    _write_limit(ctx)
    return W.create_automation(ctx, body)


@router.patch("/automations/{automation_id}", response_model=S.AutomationOut)
def patch_automation(automation_id: str, body: S.AutomationPatchIn, ctx: Admin) -> S.AutomationOut:
    _write_limit(ctx)
    return W.set_automation_enabled(ctx, parse_uuid(automation_id, "automation"), body.enabled)


@router.post("/automations/{automation_id}/run", response_model=S.TaskOut, status_code=201)
def run_automation(automation_id: str, ctx: Admin) -> S.TaskOut:
    RL.hit(RL.TASK_CREATE_USER, str(ctx.user.id))
    return W.run_automation(ctx, parse_uuid(automation_id, "automation"))


# ------------------------------------------------------------------ integrations
@router.get("/integrations", response_model=list[S.IntegrationOut])
def list_integrations(ctx: Ctx) -> list[S.IntegrationOut]:
    return W.list_integrations(ctx)


@router.post("/integrations/wordpress/connect", response_model=S.IntegrationOut, status_code=202)
def connect_wordpress(body: S.ConnectWordPressIn, ctx: Admin) -> S.IntegrationOut:
    _write_limit(ctx)
    AG.connect_wordpress(ctx, body)
    return next(i for i in W.list_integrations(ctx) if i.key == "wordpress")


@router.post("/integrations/{key}/connect", response_model=S.IntegrationOut)
def connect_integration(key: str, ctx: Admin) -> S.IntegrationOut:
    _write_limit(ctx)
    return W.connect_integration(ctx, key)


@router.post("/integrations/{key}/disconnect", response_model=S.IntegrationOut)
def disconnect_integration(key: str, ctx: Admin) -> S.IntegrationOut:
    _write_limit(ctx)
    return W.disconnect_integration(ctx, key)


# ------------------------------------------------------------------ reports, activity, notifications
@router.get("/reports", response_model=S.ReportsOut)
def reports(ctx: Ctx) -> S.ReportsOut:
    return W.reports(ctx)


@router.get("/activity", response_model=S.Page[S.ActivityOut])
def activity(
    ctx: Ctx, type: S.ActivityType | None = None, page: PageQ = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 50
) -> S.Page[S.ActivityOut]:
    return W.list_activity(ctx, type, page, page_size)


@router.get("/notifications", response_model=S.NotificationList)
def notifications(ctx: Ctx, unread: bool = False) -> S.NotificationList:
    return W.list_notifications(ctx, unread)


@router.post("/notifications/read-all", status_code=204)
def read_all(ctx: Ctx) -> Response:
    W.mark_all_notifications(ctx)
    return Response(status_code=204)


@router.post("/notifications/{notification_id}/read", status_code=204)
def read_one(notification_id: str, ctx: Ctx) -> Response:
    W.mark_notification(ctx, parse_uuid(notification_id, "notification"))
    return Response(status_code=204)


# ------------------------------------------------------------------ security, settings, usage, account
@router.get("/security/status", response_model=S.SecurityStatusOut)
def security_status(ctx: Ctx) -> S.SecurityStatusOut:
    return W.security_status(ctx)


@router.get("/settings", response_model=S.SettingsOut)
def get_settings_(ctx: Ctx) -> S.SettingsOut:
    return W.settings_out(ctx)


@router.patch("/me/preferences", response_model=S.SettingsOut)
def update_preferences(body: S.PreferencesIn, ctx: Ctx) -> S.SettingsOut:
    _write_limit(ctx)
    return W.update_preferences(ctx, body)


@router.patch("/workspace/settings", response_model=S.SettingsOut)
def update_workspace_settings(body: S.WorkspaceSettingsIn, ctx: Admin) -> S.SettingsOut:
    _write_limit(ctx)
    return W.update_workspace_settings(ctx, body)


@router.get("/usage", response_model=S.UsageOut)
def usage(ctx: Ctx) -> S.UsageOut:
    return usage_report(ctx.db, ctx.workspace.id)


@router.post("/account/export-request", response_model=S.AccountRequestOut, status_code=201)
def export_request(ctx: Ctx) -> S.AccountRequestOut:
    RL.hit(RL.ACCOUNT_REQUEST_USER, str(ctx.user.id))
    return W.account_request(ctx, "data_export", None)


@router.post("/account/deletion-request", response_model=S.AccountRequestOut, status_code=201)
def deletion_request(body: S.AccountDeletionIn, ctx: Ctx) -> S.AccountRequestOut:
    RL.hit(RL.ACCOUNT_REQUEST_USER, str(ctx.user.id))
    return W.account_request(ctx, "account_deletion", body.reason)
