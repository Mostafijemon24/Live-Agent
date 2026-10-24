# Backend readiness — endpoints each screen needs

All endpoints are tenant-scoped, authorised server-side, versioned under `/api/v1`, return a request ID, and never include secrets or stack traces.

| Screen | Endpoints |
|---|---|
| Register / Login / Logout | `POST /auth/register`, `POST /auth/login`, `POST /auth/logout` (HttpOnly, Secure, SameSite cookies; CSRF; rate limits) |
| Forgot / Reset / Verify | `POST /auth/forgot-password`, `POST /auth/reset-password`, `POST /auth/verify-email` |
| Session / header | `GET /me`, `GET /workspaces` |
| Onboarding | `PATCH /me/preferences`, `PATCH /workspace/policy` |
| Overview | `GET /dashboard` (counts, agent status, setup checklist) |
| New task | `POST /tasks` (idempotency key), `GET /files?status=ready` |
| Plan review | `GET /tasks/{id}/plan`, `POST /tasks/{id}/plan/approve` (selected step IDs, payload hash), `POST /tasks/{id}/plan/reject`, `POST /tasks/{id}/plan/revise`, `POST /tasks/{id}/messages` |
| Tasks list | `GET /tasks?q=&status=&type=&created_from=&integration=&sort=&cursor=` |
| Task detail | `GET /tasks/{id}`, `GET /tasks/{id}/events` (SSE or bounded polling), `GET /tasks/{id}/logs` (redacted), `GET /tasks/{id}/artifacts`, `POST /tasks/{id}/pause`, `/resume`, `/cancel`, `/answer`, `/retry` (only if server marks retry-safe) |
| Approvals | `GET /approvals?status=`, `POST /approvals/{id}/approve` (bound to action hash, user, tenant, target, expiry), `/reject`, `/request-changes` |
| Files | `GET /files?collection=&classification=&status=&q=`, `POST /files` (validate, scan, private storage), `PATCH /files/{id}` (classification), deletion via `POST /approvals` of type `record_deletion`, `GET /files/{id}/preview` (short-lived signed URL) |
| Automations | `GET /automations`, `POST /automations`, `PATCH /automations/{id}` (pause/resume), `POST /automations/{id}/run`, `GET /automations/{id}/runs` — scheduler with queue, back-pressure, idempotency |
| Integrations | `GET /integrations`, `POST /integrations/{id}/connect` (OAuth/server flow), `DELETE /integrations/{id}` (disconnect only) |
| Reports & Activity | `GET /reports`, `GET /activity?type=&cursor=`, `POST /exports` |
| Security & Privacy | `GET /security/status`, `PATCH /workspace/privacy-mode`, `GET /security/blocked-actions`, `POST /account/export-request`, `POST /account/deletion-request` |
| Settings | `PATCH /me`, `PATCH /workspace`, `PATCH /me/notification-settings`, `PATCH /workspace/ai-policy`, `GET /usage` |
| Notifications | `GET /notifications`, `POST /notifications/read-all`, `PATCH /notifications/{id}` |

## Server-side controls the UI assumes
Policy engine enforcing approvals and privacy mode · egress gateway for AI providers · encrypted secrets · isolated browser/code workers · durable job queue + workers · audit log · retention jobs · backups with tested restore.
