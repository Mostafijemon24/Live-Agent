# Phase 2 report — full-stack foundation

Date: 2026-10-24. Scope: the "Master Prompt 2" brief, built on the approved Phase 1 design (`project/Steward AI Agent Workspace.dc.html`).

**The autonomous AI engine is not built.** No planner, model provider, worker, real integration or scheduler exists. The application is honest about this everywhere: a persistent "PREVIEW — The AI agent engine is not installed yet" strip, task states like *Queued — waiting for the planning service*, and approvals that record decisions with `execution_state = blocked_until_phase3`.

## What was built

| Area | Delivered |
|---|---|
| Architecture | `ARCHITECTURE.md`, with 17 decisions: two services (Next.js + FastAPI), PostgreSQL, same-origin proxy, two DB roles, ports-and-adapters interfaces. |
| Frontend | All 20 Phase 1 screens ported to Next.js 16 / TypeScript / Tailwind, faithful to the prototype's visuals, wired to the real API through one `AgentApi` adapter (`web/lib/api`). Loading, empty and error states everywhere. Errors are shown, never turned into fake success. Mobile drawer below 980 px. |
| Demo mode | The Phase 1 sample data lives in `MockAgentApi`, used only when built with `NEXT_PUBLIC_DEMO_MODE=true`. Production builds exclude it entirely (verified: sample data not present in the bundle). |
| Auth | Register → email verification → login. Logout, forgot/reset password (revokes all sessions), resend verification, idle and absolute session expiry, Argon2id, CSRF, rate limits, generic messages with no account enumeration, dev mail outbox. |
| Tenancy | Private workspace per user, memberships with roles, workspace taken from the session, every query scoped, cross-tenant IDs → 404 + audit event, composite FKs in the database. |
| Data model | 22 tables: users, workspaces, memberships, sessions, auth tokens, rate-limit buckets, tasks, steps, events, attachments, jobs (outbox), approval requests, decisions, deletion requests, files, integrations, automations, artifacts, audit events, notifications, usage counters, account requests. Constraints, indexes, timestamps. |
| Migrations | Alembic `0001` (schema) and `0002` (least-privilege grants + append-only audit trigger). Upgrade → downgrade → upgrade tested. A test asserts the models match the migrations. |
| State machine | `api/app/domain/task_states.py`, tested for all 121 status pairs. |
| API | 50 versioned endpoints (`API_CONTRACT.md`), Pydantic validation (unknown fields rejected), stable error envelope, request IDs, pagination, idempotency keys, rate limits. |
| Files | Private storage outside any web root, random names, content sniffing against an allowlist, streaming size limit, traversal-proof, safe attachment downloads, `unscanned` state with a `FileScanner` interface, quota tracking. |
| Approvals and deletion | Approval requests and append-only decisions bound to an action hash, expiry, exact-item confirmation for deletions. Deletion requests record target, scope, expected records, reason, requester and approval link. Nothing is ever deleted. |
| Audit | Append-only `audit_events` (app role INSERT/SELECT only, plus a trigger that blocks UPDATE/DELETE/TRUNCATE for every role), scrubbed metadata. Covers auth, tasks, plans, approvals, files, privacy, integrations, settings and authorization failures. |
| Interfaces for Phase 3 | `TaskPlanner`, `ApprovalPolicy`, `ModelProvider`, `JobQueue`, `Worker`, `ToolRegistry`, `AuditLogger`, `FileStorage`, `FileScanner`, `Mailer` in `api/app/ports`, with safe Phase 2 adapters in `api/app/adapters`. |
| Deployment | `docker-compose.yml` (db, migrate, api, web, optional Caddy TLS), Dockerfiles running as non-root, role bootstrap script, backup script, `.env.example` with placeholders only. |
| Docs | `README.md`, `ARCHITECTURE.md`, `API_CONTRACT.md`, `SECURITY_AND_PRIVACY.md`, this report, `web/FRONTEND_GUIDE.md`. |

## Commands run and results

All commands were run in this environment on 2026-10-24.

| Command | Result |
|---|---|
| `cd api && uv run ruff check app migrations tests` | All checks passed |
| `uv run ruff format --check app migrations tests` | 42 files already formatted |
| `uv run mypy app` (strict) | Success: no issues found in 32 source files |
| `uv run pytest` (isolated `steward_test` database, app connects as `steward_app`) | **225 passed** in ~31 s |
| `cd web && npm run lint` | 0 problems |
| `npm run typecheck` | 0 errors |
| `npm test` (Vitest) | 7 passed |
| `npm run build` (production) | Compiled, 22 routes generated |
| `NEXT_PUBLIC_DEMO_MODE=true npm run build` + browser check | Demo works with sample data; 0 calls to `/api/v1` |
| `node e2e/smoke.mjs` against local API + production web build | **25/25 steps passed**, 0 console errors |
| `docker compose config -q` | Valid; only `web` publishes a port (127.0.0.1:3000) |
| Fresh `docker compose up` (empty volumes) | db healthy → roles created → `migrate` ran 0001 and 0002 as owner → api healthy → web up |
| `node e2e/smoke.mjs` against the Docker stack | **25/25 steps passed**, 0 console errors |
| `docker compose restart db api`, then row counts | Users, tasks, files, audit events and decisions persisted |
| `has_table_privilege('steward_app', …)` in the container | No DELETE on tasks, no UPDATE on audit_events, not a superuser |

The e2e run covers: register → generic error before verification → verify via emailed link → login → onboarding → overview → create task (persisted, queued, waiting for planner) → task detail and logs → tasks list → real file upload (unscanned, unknown) → deletion request → approval with exact-item confirmation (decision recorded, nothing deleted) → file still present → integration connect explains Phase 3 → automations, reports, security, settings, notifications, help, states → audit events in the activity log → 390 px mobile layout with no horizontal scroll → logout, with protected pages redirecting to login.

### Test coverage by requirement

| Requirement | Tests |
|---|---|
| Authentication | `test_auth.py` (12 tests) |
| Authorization and roles | `test_member_role_cannot_change_workspace_settings`, owner/admin checks on decisions and integrations |
| Cross-tenant isolation (tasks, files, approvals, reports, integrations, activity, plus notifications and automations) | `test_isolation.py` (10 tests) |
| Task CRUD and state transitions | `test_tasks.py` (132 tests, including the full 121-pair transition matrix) |
| Input validation | Validation tests in auth, tasks, files, settings and onboarding |
| File access controls | `test_files.py` (8 tests) |
| Approval records | `test_approvals_audit.py` (22 tests: approval rules, append-only decisions, tamper detection, DB privileges) |
| Audit logging | Audit tests plus DB privilege tests |
| Rate limiting | 4 tests (login per email, register per IP, forgot password, task creation) |
| Migrations | Upgrade/downgrade/upgrade and models-match-migrations |
| API contract | Error envelope, request IDs, OpenAPI ↔ `API_CONTRACT.md`, Pydantic ↔ `types.ts` field parity for 22 types |

## Not tested / known limitations

- **Docker image builds in this sandbox** needed the sandbox's proxy CA certificate added in a scratch copy of the Dockerfiles. The committed Dockerfiles are unchanged and assume normal internet access, which a VPS has. Docker Hub was rate-limited here, so images were pulled through `mirror.gcr.io`.
- **SMTP delivery** (`MAIL_BACKEND=smtp`) is implemented but not exercised against a real mail server. Only the dev outbox was tested.
- **The Caddy TLS profile** was validated as config only. Obtaining real certificates needs a public domain.
- **Load and performance** testing was not done. Offset pagination is fine at this scale; cursor pagination is a Phase 3 option.
- **Browser coverage**: Chromium only. Visual fidelity was spot-checked by screenshot against the prototype, not pixel-diffed.
- **The plan review UI with a real plan** is exercised only by API tests (steps inserted directly) and in demo mode. No planner exists to produce plans.
- **Settings "Appearance" and "Billing"** are placeholders, as in the prototype.

## Decisions made without asking (for review)

1. **Verify before login.** Registration doesn't sign the user in, and all login failures share one message. This prevents account enumeration but changes the prototype flow, which went straight from register to onboarding.
2. **Collected integration credentials: none.** Connect returns `409 integration_not_available` until Phase 3 builds real OAuth/server-side flows.
3. **Archives (.zip) are refused** for now, because nothing can inspect their contents safely yet. The prototype showed a quarantined zip as sample data.
4. **Workspace name** defaults to "\<first name\>'s workspace" (editable in Settings).
5. Still open from Phase 1: the product name "Steward" (placeholder), the default timezone (now UTC per user, with Asia/Dhaka selectable), and the default execution mode for WordPress tasks.

## Remaining Phase 3 work

- Planner service implementing `TaskPlanner`. Writes `task_steps` and moves `queued → planning → awaiting_approval`.
- Job workers consuming the `jobs` outbox, with retries, idempotency, back-pressure and dead-lettering. Also the scheduler for automations.
- Policy engine implementing `ApprovalPolicy`, actually enforcing privacy mode, AI rules, tool permissions, allowlists and file classifications. Per-step approvals at run time.
- Model provider adapters behind an egress gateway. Real integrations (WordPress, Notion, storage, email) with OAuth and encrypted secret storage.
- Isolated browser/code execution sandboxes. Tool registry wired to real tools.
- Malware scanner adapter (for example ClamAV) and quarantine flow.
- Executing approved deletions with soft-delete, retention jobs and permanent removal.
- PostgreSQL RLS as defence in depth, a hash-chained audit log, MFA, a session management UI, data export, and processing of account-deletion requests.
- Monitoring, structured logs shipping, automated restore-tested backups, CI pipeline.
