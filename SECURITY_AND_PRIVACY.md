# Security and privacy — Phase 2

This page separates what is **enforced and covered by an automated test** from what is **designed but not yet enforced**. Nothing in the second list should be described to users as protection.

## Enforced and tested

| Control | How | Test(s) |
|---|---|---|
| Password hashing | Argon2id (`argon2-cffi` defaults), automatic rehash on login when parameters change. A dummy verify on unknown emails keeps timing similar. | `test_full_registration_verification_login_flow` |
| Password policy | 10–128 characters including a digit, checked on the server. | `test_password_policy_and_input_validation` |
| No account enumeration | Register, login, resend-verification and forgot-password give the same response whether or not the email exists. Login requires a verified email, and all login failures share one generic message. The real owner is emailed when someone registers with their address. | `test_registration_does_not_reveal_existing_accounts`, `test_login_failures_are_indistinguishable`, `test_resend_verification_is_generic`, `test_password_reset_flow_revokes_sessions` |
| Server-side sessions | Opaque 256-bit token in an `HttpOnly`, `SameSite=Lax` cookie (`Secure` + `__Host-` prefix in production). Only the SHA-256 of the token is stored. Idle timeout 12 h, absolute 7 days. Revoked on logout. All revoked on password reset. Nothing secret is kept in `localStorage`. | `test_session_cookie_flags_and_hashed_storage`, `test_logout_revokes_session`, `test_session_idle_and_absolute_expiry`, `test_production_config_guards` |
| One-time tokens | Verification (24 h) and reset (1 h) links are single-use, stored hashed, and older tokens are invalidated on reissue. | `test_expired_reset_token_rejected`, flow tests |
| CSRF | Double-submit token on every state-changing request, including login, plus an `Origin` check. | `test_csrf_required_on_state_changes` |
| Rate limiting | PostgreSQL fixed-window counters (work across processes) on login (per IP and per email), registration, reset, verification, uploads, task creation and writes. `429` + `Retry-After`. Cannot be disabled in production. | `test_login_rate_limited_per_email`, `test_register_rate_limited_per_ip`, `test_forgot_password_rate_limited`, `test_task_creation_rate_limited` |
| Tenant isolation | The workspace comes from the session row, never from client input. Every query is scoped by `workspace_id`. Foreign IDs return `404` (no existence oracle) and are audited as `authz.denied` in the requester's workspace. Unknown body fields are rejected. Composite foreign keys stop cross-tenant child rows in the database itself. | `test_isolation.py`: tasks, files, approvals, reports, integrations, activity, notifications, automations, DB constraint |
| Roles | Workspace settings, integration changes and approval decisions need `owner`/`admin`. | `test_member_role_cannot_change_workspace_settings` |
| Least-privilege database role | The API connects as `steward_app`: no DDL, no `TRUNCATE`, **no `DELETE`** (except the rate-limit table), not a superuser. Migrations run as `steward_owner`. | `test_app_role_cannot_delete`, `test_app_role_cannot_run_ddl_or_truncate` |
| Append-only audit log | The app role can only `INSERT`/`SELECT` `audit_events`, `approval_decisions` and `task_events`. A trigger rejects `UPDATE`/`DELETE`/`TRUNCATE` on `audit_events` even for the schema owner. Secret-looking metadata keys are redacted. | `test_append_only_tables_for_app_role`, `test_audit_log_append_only_even_for_owner`, `test_audit_metadata_is_scrubbed`, `test_security_events_are_audited` |
| No secrets in logs | Tokens, passwords and full email addresses are not logged. The dev mail adapter logs only a masked address and the file name. | `test_tokens_and_passwords_never_logged` |
| File upload safety | Type detected from content (magic bytes / text checks) against an allowlist. Executables, scripts, HTML/SVG and archives refused. Size enforced while streaming. Random internal names; client names never used as paths (traversal-proof). Files `0600` in a `0700` directory outside any web root. Rejected uploads leave no bytes behind. | `test_content_is_sniffed_not_trusted`, `test_size_limit_enforced`, `test_path_traversal_names_are_neutralised`, `test_upload_csv_is_private_unscanned_and_unclassified` |
| Safe downloads | Authenticated and tenant-checked. Always `attachment`, `application/octet-stream`, `nosniff`, `CSP: sandbox`. Quarantined files refused. No public URLs. | `test_download_is_attachment_with_nosniff`, `test_files_are_isolated` |
| Uploading ≠ sharing | New files are `unknown` ("sharing blocked") and nothing is sent to any AI provider — none is configured. | `test_upload_csv_is_private_unscanned_and_unclassified`, `test_security_status_is_honest` |
| Approvals | `approve` needs explicit acknowledgement. Deletion needs the exact item list confirmed. One decision per request. Expiry enforced. The decision is bound to the stored action hash (tampering → `409`). | `test_approvals_audit.py` |
| Deletion safety | Deleting a file creates a `deletion_requests` row (target, scope, expected records, reason, requester) plus a `record_deletion` approval. Approving sets `approved_blocked` / `blocked_until_phase3`. No code path deletes user data. | `test_deletion_request_never_deletes` |
| No fake progress | New tasks are `queued` with `waiting_for="planning_service"`. Approving a plan moves it to `queued` waiting for the execution engine — never `running` or `completed`. Only `running` can reach `completed` in the state machine. | `test_create_task_is_persisted_and_waits_for_planner`, `test_plan_approval_flow_without_execution_engine`, `test_no_path_to_completed_without_running` |
| Request limits and headers | 30 MB body cap, request IDs, `nosniff`, `X-Frame-Options: DENY`, restrictive CSP on API responses, `no-store`, HSTS in production. Stack traces are never returned. | `test_error_envelope_and_request_id`, `test_oversized_request_rejected` |
| Production guards | The API refuses to start in production with the dev mail outbox, an `http://` origin, a placeholder DB password or rate limiting disabled. | `test_production_config_guards` |
| No exposed database | Compose publishes no database or API port. Only `web` (127.0.0.1) or Caddy (80/443) listen. | Verified with `docker compose config` and a live stack (see PHASE2_REPORT.md) |

## Designed but NOT enforced yet (Phase 3)

| Item | Current state |
|---|---|
| Privacy mode, AI behaviour rules, tool permissions, allowed domains | Saved and audited, labelled "not enforced" in the UI. No policy engine reads them yet. |
| Malware scanning | Interface present (`FileScanner`). Files are `unscanned` ("scanner not configured"). |
| Encrypted secret storage | No credentials are collected or stored. Integrations cannot be connected. |
| Outbound network / egress policy for AI providers | No AI provider exists, so nothing leaves. No gateway yet. |
| PostgreSQL Row-Level Security | Not enabled. Isolation is enforced by the application and composite FKs, and proven by tests. |
| Tamper-evident (hash-chained) audit log | Append-only is enforced. Hash chaining is not implemented. |
| Retention jobs and actual deletion | Deletion is disabled. Retention periods are documented, not automated. |
| Automated, restore-tested backups | `deploy/db/backup.sh` exists. Scheduling it and testing restores is an operator task. |
| MFA, session list / remote sign-out, account lockout notifications | Not implemented. |
| Data export and account deletion | Requests are recorded for manual handling. |

## HTTPS assumptions

Production must run behind TLS: the optional Caddy profile provides automatic certificates. With `APP_ENV=production` cookies are `Secure` and `__Host-`-prefixed, HSTS is sent, and `APP_ORIGIN` must be `https://`. `TRUST_PROXY_HEADERS=true` is set only because the API is reachable solely through the web container. Never publish the API port directly.

## Reporting

Until a security contact exists, report issues privately to the repository owner. Don't open public issues for vulnerabilities.
