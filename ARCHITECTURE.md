# Architecture — Steward AI Agent Workspace (Phase 2 foundation)

Status: accepted · Date: 2026-10-24 · Scope: Phase 2 (full-stack foundation). The autonomous AI engine is **Phase 3** and is not implemented here.

## 1. Context

Phase 1 produced an approved, single-file design prototype (`project/Steward AI Agent Workspace.dc.html`, see `project/docs/`). Phase 2 turns it into a real application that a non-technical user reaches through a browser, deployable to a single Hostinger VPS, without making the product one giant process.

## 2. Decisions

| # | Decision | Why |
|---|---|---|
| D1 | **Two services**: `web/` (Next.js 16, TypeScript, App Router) and `api/` (Python 3.13, FastAPI). PostgreSQL 16 as the only stateful dependency. | The approved README named Next.js. The spec prefers FastAPI when no backend exists. Python is also the natural home for the Phase 3 agent/worker code, so the API, planner and workers share one language and one data layer. |
| D2 | **Same-origin deployment.** The browser only talks to `web`. Next.js rewrites `/api/*` to the API service on the private network. | First-party cookies, no CORS, `SameSite=Lax` works, the API is never exposed directly. |
| D3 | **SQLAlchemy 2 + Alembic** for the data layer and versioned migrations. Migrations are additive; a migration test runs upgrade → downgrade → upgrade on a throwaway `_test` database only. | Mature, explicit, typed. |
| D4 | **Two database roles.** `steward_owner` owns the schema and runs migrations. `steward_app` is what the API uses at runtime: `SELECT/INSERT/UPDATE` only, **no `DELETE`** (except the rate-limit table), no DDL, `INSERT/SELECT` only on `audit_events`. | Least privilege. The general application/agent role physically cannot delete tasks, files, approvals or audit records (spec: deletion safety). |
| D5 | **Server-side sessions** in Postgres. Opaque 256-bit token in an `HttpOnly`, `SameSite=Lax`, `Secure` (production) cookie. Only the SHA-256 of the token is stored. Idle timeout 12 h, absolute lifetime 7 days, rotated at login, all revoked on password reset. | Revocable, simple, nothing secret in `localStorage`. |
| D6 | **CSRF**: double-submit token (`stw_csrf` cookie + `X-CSRF-Token` header) on every unsafe method, including login/register, plus an `Origin` check against `APP_ORIGIN`. | Cookie auth needs CSRF defence; the Origin check is defence in depth. |
| D7 | **Password hashing: Argon2id** (`argon2-cffi`, library defaults, automatic rehash on login when parameters change). | Current OWASP recommendation. |
| D8 | **Rate limiting** in Postgres (fixed window, `INSERT … ON CONFLICT` counter). | Works across several API worker processes without adding Redis in Phase 2. Phase 3 can swap the `RateLimiter` implementation. |
| D9 | **Tenancy**: every user gets a private workspace at registration; data is owned by `workspace_id`; access goes through `workspace_memberships` (role `owner` now, `admin/member/viewer` reserved). The active workspace is resolved **server-side from the session**, never from request input. Every repository query is scoped by `workspace_id`; a foreign ID returns `404 not_found` and writes an `authz.denied` audit event. Composite foreign keys `(workspace_id, id)` stop child rows from pointing at another tenant's parent. | Correct application authorization first. PostgreSQL RLS is **not** enabled in Phase 2 (see §6); we do not claim it. |
| D10 | **Explicit task state machine** in `api/app/domain/task_states.py`, enforced in one function, tested exhaustively. Without a planner, a new task is persisted as `queued` with `waiting_for = "planning_service"`. Nothing ever shows a fake completed result. | Spec requires honesty and an explicit state machine. |
| D11 | **Ports-and-adapters interfaces** in `api/app/ports/`: `TaskPlanner`, `ApprovalPolicy`, `ModelProvider`, `JobQueue`, `Worker`, `ToolRegistry`, `AuditLogger`, `FileStorage`, `FileScanner`, `Mailer`. Phase 2 ships safe adapters: `UnavailablePlanner`, `NullJobQueue` (records intent, never runs), `NotConfiguredScanner`, `RequireApprovalPolicy`, `LocalPrivateFileStorage`, `FileOutboxMailer` (dev) / `SmtpMailer`. | Phase 3 replaces adapters without touching routes or UI. |
| D12 | **Private file storage**: uploads are streamed to `STORAGE_DIR` (outside any web root, not served statically) under random names (`<workspace_uuid>/<uuid>`); type detected from magic bytes against an allowlist; size limit enforced while streaming; path traversal impossible because client names are never used as paths. Files start `unscanned` ("scanner not configured") and classification `unknown` (sharing blocked). Downloads go through an authenticated, tenant-checked endpoint as `attachment` with `nosniff`. | Spec: file security. |
| D13 | **Deletion is a request, not an action.** `deletion_requests` + an `approval_requests` row of category `record_deletion`. Approving records the decision; execution is `blocked_until_phase3`. No code path deletes user data. | Spec: deletion safety. |
| D14 | **Audit log** `audit_events`: append-only (app role has no UPDATE/DELETE; a trigger also rejects UPDATE/DELETE for every role), scoped by workspace, metadata scrubbed of secret-looking keys. The user-facing Activity feed reads from it. | Spec: audit logging. |
| D15 | **API**: REST under `/api/v1`, Pydantic schemas, `{"error": {"code", "message", "request_id", "details"}}` envelope, `X-Request-ID` on every response, page/page_size pagination with `total`. OpenAPI at `/api/v1/openapi.json` (disabled in production). | Spec: API contract. |
| D16 | **Frontend API adapter**: `web/lib/api` defines one `AgentApi` interface with `HttpAgentApi` (real) and `MockAgentApi` (the Phase 1 demo data). The mock is chosen only when `NEXT_PUBLIC_DEMO_MODE=true`; the production build refuses to enable it unless explicitly set, and the UI shows the DEMO strip whenever it is on. HTTP errors are surfaced, never converted into mock success. | Spec: isolated demo mode, no silent fallbacks. |
| D17 | **Docker Compose** for development and VPS: `db` (no published port), `api`, `web`, optional `caddy` for TLS. Only `web`/`caddy` publish ports. | Reproducible, Hostinger-friendly. |

## 3. Repository layout

```
api/                     FastAPI service
  app/
    core/                config, db, security (hashing, tokens), errors, request ids, rate limit
    domain/              task state machine, enums, policies
    models/              SQLAlchemy models
    schemas/             Pydantic request/response models
    ports/               interfaces (planner, queue, storage, scanner, mailer, audit, …)
    adapters/            Phase 2 implementations of the ports
    services/            use cases (auth, tasks, approvals, files, audit, …) — tenant-scoped
    routers/             HTTP routes (thin)
  migrations/            Alembic
  tests/                 pytest (isolated *_test database)
web/                     Next.js app
  app/                   routes (public, auth, (app) shell)
  components/            ui kit + shell
  features/              one folder per product area
  lib/api/               AgentApi interface, http + mock adapters, types
deploy/                  compose helpers, db init, Caddyfile
project/, chats/         Phase 1 design bundle (source of truth for visuals)
```

## 4. Request lifecycle

Browser → `web` (`/api/v1/...` rewrite) → FastAPI middleware (request ID → security headers → body-size limit) → dependency `current_context` (session cookie → user → membership → workspace) → CSRF check on unsafe methods → rate limit (where configured) → service (tenant-scoped query, transaction) → audit event → response.

## 5. Dependency versions

Pinned in `api/pyproject.toml` / `api/requirements.lock` and `web/package.json` / `web/package-lock.json`; the exact versions are listed in `README.md`.

## 6. Not in Phase 2 (explicitly)

- AI planning/execution, model providers, browser/code workers, real integrations (OAuth), scheduler. Interfaces exist; adapters report "not configured".
- Malware scanning (interface + `unscanned` state only).
- PostgreSQL Row-Level Security — considered; deferred to Phase 3 hardening because it needs per-transaction tenant context across the planner and workers too. Isolation is enforced by the application and proven by tests.
- Actual deletion of any record or file.
- Email delivery in development is a local outbox directory, not real email.
