# API contract — `/api/v1`

The browser calls these through the web app's own origin (`/api/v1/...` is forwarded to the API service). Types are defined twice and kept in sync by a test: Pydantic in `api/app/schemas/__init__.py` and TypeScript in `web/lib/api/types.ts` (`test_backend_schemas_match_frontend_types`). A second test fails if an endpoint is implemented but not listed here, or listed but not implemented (`test_openapi_lists_documented_endpoints`). In development the live OpenAPI document is at `/api/v1/openapi.json` (interactive docs at `/api/v1/docs`); both are disabled in production.

## Conventions

| Topic | Rule |
|---|---|
| Auth | Session cookie `stw_session` (`__Host-stw_session` in production): opaque, `HttpOnly`, `SameSite=Lax`, `Secure` in production. Idle timeout 12 h, absolute 7 days. |
| CSRF | Every `POST/PATCH/PUT/DELETE` (including login and register) needs header `X-CSRF-Token` equal to the `stw_csrf` cookie. Get both from `GET /auth/csrf`. A cross-site `Origin` is rejected. Failure → `403 csrf_failed`. |
| Tenancy | The workspace comes from the session. IDs from another workspace return `404 not_found` (same as nonexistent) and are audited as `authz.denied`. Unknown body fields are rejected (`422`). |
| Errors | `{"error": {"code", "message", "request_id", "details"}}`. `message` is safe to show users. Validation: `422 validation_error`, `details = [{"field", "message"}]`. |
| Request ID | Every response has `X-Request-ID` (echoes a valid incoming one). Shown to users as "Ref" on errors. |
| Pagination | `?page=1&page_size=N` → `{items, page, page_size, total}`. |
| Idempotency | `POST /tasks` accepts `Idempotency-Key` (≤ 80 chars). A repeat returns the original task with `200`. |
| Time | ISO-8601 UTC timestamps. |
| Rate limits | `429 rate_limited` with `Retry-After`. Limits below. |

### Rate limits

| Name | Limit |
|---|---|
| Login per IP / per email | 20 / 15 min · 10 / 15 min |
| Register per IP / per email | 5 / hour · 3 / hour |
| Forgot password per IP / per email | 5 / hour · 3 / hour |
| Resend verification per IP / per email | 5 / hour · 3 / hour |
| Reset password per IP · Verify email per IP | 10 / hour · 20 / hour |
| Task creation per user (incl. automation runs) | 30 / min |
| Uploads per user | 30 / 10 min |
| Other writes per user | 120 / min |
| Account requests per user | 3 / hour |
| Denied-ID probes per user (404s that are audited) | 30 / 10 min |

Client IP for these limits: the peer address, or `X-Real-IP` set by Caddy when `TRUST_PROXY_HEADERS=true`. `X-Forwarded-For` is never trusted. Register, forgot-password and resend-verification always take at least `AUTH_RESPONSE_FLOOR_MS`.

### Roles

viewer = read-only (plus own preferences, onboarding, notifications). member = also create/cancel tasks, messages, uploads, deletion requests. owner/admin = also plan approve/reject, file classification/collection, automations, integrations, approval decisions, workspace settings. A missing role → `403 forbidden`.

### Common error codes

`not_authenticated`, `session_expired`, `invalid_credentials`, `csrf_failed`, `forbidden`, `not_found`, `validation_error`, `rate_limited`, `quota_exceeded`, `invalid_state_transition`, `action_not_allowed`, `invalid_or_expired_token`, `approval_expired`, `approval_already_decided`, `approval_payload_changed`, `acknowledgement_required`, `confirmation_mismatch`, `deletion_already_requested`, `unsupported_file_type`, `file_too_large`, `file_empty`, `file_quarantined`, `integration_not_available`, `integration_not_connected`, `scheduler_not_configured`, `payload_too_large`, `internal_error`.

## Endpoints

### Auth & account

| Endpoint | Body → Response | Notes |
|---|---|---|
| `GET /auth/csrf` | → `{csrf_token}` | Sets the `stw_csrf` cookie. |
| `POST /auth/register` | `{name, email, password, accept_terms}` → `202 {message}` | Same response whether or not the email exists. Sends a verification link (dev: file in `MAIL_OUTBOX_DIR`). Does **not** sign in. Password: 10–128 chars incl. a digit. |
| `POST /auth/verify-email` | `{token}` → `{message}` | Single-use, 24 h. |
| `POST /auth/resend-verification` | `{email}` → `202 {message}` | Generic response. |
| `POST /auth/login` | `{email, password}` → `Me` + session cookie | Requires a verified email. All failures → `401 invalid_credentials` with one generic message. Rotates to a new session. |
| `POST /auth/logout` | → `204` | Revokes the session server-side. |
| `POST /auth/forgot-password` | `{email}` → `202 {message}` | Generic response. Link valid 1 h, single use. |
| `POST /auth/reset-password` | `{token, password}` → `{message}` | Revokes **all** sessions of the user. |
| `GET /me` | → `Me` | `{user, workspace: {id, name, role}, demo:false}` |
| `POST /me/onboarding` | `{goals[], where[], ai_rules}` → `Me` | Codes are `[a-z0-9_]`, ≤ 10 each. |
| `PATCH /me/preferences` | `{name?, timezone?, notifications?}` → `Settings` | |
| `POST /account/export-request` | → `201 AccountRequest` | Recorded for manual handling. |
| `POST /account/deletion-request` | `{reason}` → `201 AccountRequest` | Recorded only; nothing is deleted. |

### Dashboard, tasks

| Endpoint | Body / query → Response | Notes |
|---|---|---|
| `GET /dashboard` | → `Dashboard` | Counts, agent status (`not_connected`), setup checklist, recent tasks/approvals/activity, unread count. |
| `GET /tasks` | `?q&status&type&created=today\|3d&integration=<key>\|none&sort=updated\|created\|title&page&page_size≤100` → `Page<TaskSummary>` | `q` matches title, prompt or `T-<n>`. |
| `POST /tasks` | `CreateTaskInput` → `201 Task` | `mode=execute` is refused (engine not installed). Attachments must be your own ready/unscanned files. New tasks are `queued` with `waiting_for="planning_service"` and a `task.plan` job recorded in the outbox. |
| `GET /tasks/{task_id}` | → `Task` | Includes `plan` (null until a planner exists), `allowed_actions` from the state machine. |
| `POST /tasks/{task_id}/cancel` | `{reason?}` → `Task` | Allowed from any non-terminal status. |
| `POST /tasks/{task_id}/pause` | → `Task` | Only from `running`. |
| `POST /tasks/{task_id}/resume` | → `Task` | From `paused` → `queued` (`waiting_for=execution_engine`). |
| `POST /tasks/{task_id}/messages` | `{text, kind: question\|answer\|plan_change}` → `Task` | `answer` only in `needs_input`; `plan_change` only in `awaiting_approval` with a plan. |
| `POST /tasks/{task_id}/plan/approve` | `{selected_step_ids[]}` → `Task` | Unselected steps become `skipped`; task → `queued` waiting for the execution engine. Never "running". |
| `POST /tasks/{task_id}/plan/reject` | `{note?}` → `Task` | → `cancelled`. |
| `GET /tasks/{task_id}/events` | `?page&page_size≤200` → `Page<TaskEvent>` | Oldest first. |

Task state machine: `api/app/domain/task_states.py` (tested for every pair). Only `running` can reach `completed`.

### Approvals

| Endpoint | Body / query → Response | Notes |
|---|---|---|
| `GET /approvals` | `?status=pending\|decided\|all&page&page_size` → `Page<Approval> + pending_count` | Overdue pending requests are marked `expired`. |
| `GET /approvals/{approval_id}` | → `Approval` | |
| `POST /approvals/{approval_id}/decision` | `{decision: approve\|reject\|request_changes, note?, acknowledged, confirmed_items?}` → `Approval` | Owner/admin only. `approve` needs `acknowledged=true`; for `record_deletion` also `confirmed_items` equal to `affected_items`. `request_changes` needs a note. One decision per request (`409` after). Bound to the stored `payload_hash`. Approval sets `execution_state="blocked_until_phase3"` — nothing runs. |

### Files

| Endpoint | Body / query → Response | Notes |
|---|---|---|
| `GET /files/limits` | → `UploadLimits` | Max size and allowed types. |
| `GET /files` | `?q&collection&classification&status&page&page_size≤200` → `Page<FileItem> + collections[{name,count}]` | Collection counts are workspace-wide. |
| `POST /files` | multipart `file`, `collection` → `201 FileItem` | Type detected from content (PDF, PNG, JPG, DOCX, XLSX, CSV, TXT, MD, JSON); executables, scripts, HTML/SVG and archives refused (`415`). Size limit while streaming (`413`). Stored privately under a random name. Status `unscanned` (scanner not configured), classification `unknown`. |
| `GET /files/{file_id}` | → `FileItem` | |
| `PATCH /files/{file_id}` | `{classification?, collection?}` → `FileItem` | Classification changes are audited. |
| `GET /files/{file_id}/download` | → bytes | `Content-Disposition: attachment`, `application/octet-stream`, `nosniff`, `CSP: sandbox`. Quarantined files refused. |
| `POST /files/{file_id}/deletion-request` | `{reason}` → `201 Approval` | Creates a `deletion_requests` row + a `record_deletion` approval. Never deletes. |

### Automations, integrations

| Endpoint | Body → Response | Notes |
|---|---|---|
| `GET /automations` | → `Automation[]` | |
| `POST /automations` | `CreateAutomationInput` → `201 Automation` | Scheduled automations are saved disabled (DB constraint) until the scheduler exists. |
| `PATCH /automations/{automation_id}` | `{enabled}` → `Automation` | Enabling a scheduled one → `409 scheduler_not_configured`. |
| `POST /automations/{automation_id}/run` | → `201 Task` | Queues a task (waiting for the planner). |
| `GET /integrations` | → `Integration[]` | Catalog with this workspace's status. `connectable=false` in Phase 2. |
| `POST /integrations/{key}/connect` | → `409 integration_not_available` | Audited. Real OAuth/server flows are Phase 3. No credentials are ever collected. |
| `POST /integrations/{key}/disconnect` | → `Integration` | Only for connected integrations. |

### Reports, activity, notifications, security, settings

| Endpoint | Response | Notes |
|---|---|---|
| `GET /reports` | `{artifacts[], reports: Task[]}` | Empty until the execution engine produces outputs. |
| `GET /activity` | `Page<ActivityEvent>` (`?type&page&page_size`) | Reads the workspace's audit log (newest first). |
| `GET /notifications` | `{items, unread}` (`?unread=true`) | `target.route` is an app path. |
| `POST /notifications/read-all` | `204` | |
| `POST /notifications/{notification_id}/read` | `204` | |
| `GET /security/status` | `SecurityStatus` | Checklist states are computed from configuration: `enforced`, `partial` or `not_configured`. `privacy_enforced=false`. |
| `GET /settings` | `Settings` | `enforced=false` until the Phase 3 policy engine. |
| `PATCH /workspace/settings` | `Settings` | Owner/admin only. `{name?, privacy_mode?, ai_rules?, tool_permissions?, allowed_domains?}`. |
| `GET /usage` | `Usage` | Tasks/month, storage, uploads; quotas from config. |

The health check `/healthz` (GET, outside `/api/v1`, not proxied to browsers) returns `{"status":"ok"}` when the database is reachable.
