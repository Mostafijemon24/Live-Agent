# Security and privacy — Phase 2

This page separates what is **enforced and covered by an automated test** from what is **designed but not yet enforced**. Nothing in the second list should be described to users as protection.

## Enforced and tested

| Control | How | Test(s) |
|---|---|---|
| Password hashing | Argon2id (`argon2-cffi` defaults), automatic rehash on login when parameters change. A dummy verify on unknown emails keeps timing similar. | `test_full_registration_verification_login_flow` |
| Password policy | 10–128 characters including a digit, checked on the server. | `test_password_policy_and_input_validation` |
| No account enumeration | Register, login, resend-verification and forgot-password give the same response whether or not the email exists. Login requires a verified email, and all login failures share one generic message. **Timing:** the existing-email path does the same Argon2 work, and register/forgot/resend are padded to a fixed minimum duration (`AUTH_RESPONSE_FLOOR_MS`, default 400 ms). **Mail** is delivered after the response, so slowness or outages can't reveal accounts. The real owner is emailed when someone registers with their address. | `test_registration_does_not_reveal_existing_accounts`, `test_login_failures_are_indistinguishable`, `test_resend_verification_is_generic`, `test_sr4_register_and_forgot_timing_do_not_reveal_accounts`, `test_sr5_mail_outage_does_not_change_auth_responses` |
| Server-side sessions | Opaque 256-bit token in an `HttpOnly`, `SameSite=Lax` cookie (`Secure` + `__Host-` prefix in production). Only the SHA-256 of the token is stored. Idle timeout 12 h, absolute 7 days. Revoked on logout. All revoked on password reset. Nothing secret is kept in `localStorage`. | `test_session_cookie_flags_and_hashed_storage`, `test_logout_revokes_session`, `test_session_idle_and_absolute_expiry`, `test_production_config_guards` |
| One-time tokens | Verification (24 h) and reset (1 h) links are single-use, stored hashed, and older tokens are invalidated on reissue. | `test_expired_reset_token_rejected`, flow tests |
| CSRF | Double-submit token on every state-changing request, including login, plus an `Origin` check. | `test_csrf_required_on_state_changes` |
| Rate limiting | PostgreSQL fixed-window counters (work across processes) on login (per IP and per email), registration (per IP and per email), reset, verification, uploads, task creation, writes and denied-ID probes. `429` + `Retry-After`. **Client IP:** `X-Forwarded-For` is never trusted. With `TRUST_PROXY_HEADERS=true` (required in production, behind Caddy) only `X-Real-IP`, which Caddy overwrites, is used, and uvicorn runs with `--no-proxy-headers`. Rate limiting cannot be disabled in production. | `test_login_rate_limited_per_email`, `test_register_rate_limited_per_ip`, `test_forgot_password_rate_limited`, `test_task_creation_rate_limited`, `test_sr1_*`, `test_sr9_*` |
| Tenant isolation | The workspace comes from the session row, never from client input. Every query is scoped by `workspace_id`. Foreign IDs return `404` (no existence oracle) and are audited as `authz.denied` in the requester's workspace (rate limited). Unknown body fields are rejected. Composite foreign keys on every cross-table reference (including jobs, audit events, automations and deletion targets) stop cross-tenant rows in the database itself. | `test_isolation.py`, `test_sr7_database_rejects_cross_tenant_references` |
| Roles | Central matrix: **viewer** = read-only (plus own preferences); **member** = create/cancel tasks, messages, uploads, deletion requests; **owner/admin** = plan approval/rejection, file classification, automations, integrations, approval decisions, workspace settings. | `test_member_role_cannot_change_workspace_settings`, `test_sr6_role_matrix_on_write_endpoints` |
| Least-privilege database role | The API connects as `steward_app`: no DDL, no `TRUNCATE`, **no `DELETE`** (except the rate-limit table), not a superuser. Migrations run as `steward_owner`. | `test_app_role_cannot_delete`, `test_app_role_cannot_run_ddl_or_truncate` |
| Append-only audit log | The app role can only `INSERT`/`SELECT` `audit_events`, `approval_decisions` and `task_events`. A trigger rejects `UPDATE`/`DELETE`/`TRUNCATE` on `audit_events` for every role. **Limit:** the schema owner (`steward_owner`) can disable that trigger, so this is not tamper-evidence against the database owner (see the second list). Events have a strict insertion order (`seq`). Secret-looking metadata keys are redacted. | `test_append_only_tables_for_app_role`, `test_audit_log_append_only_even_for_owner`, `test_audit_metadata_is_scrubbed`, `test_security_events_are_audited`, `test_sr13_task_events_have_deterministic_order` |
| No secrets in logs | Tokens, passwords and full email addresses are not logged. The dev mail adapter logs only a masked address and the file name. | `test_tokens_and_passwords_never_logged` |
| File upload safety | Type detected from content against an allowlist, and the extension must match the detected type. DOCX/XLSX are opened and must have real OOXML structure, with no executables, macros or embedded OLE objects, and limits on entry count and expanded size. Text files are scanned in full for active web content and must be valid UTF-8. Executables, scripts, HTML/SVG and archives are refused. Size enforced while streaming. Random internal names; invisible/bidi characters stripped from display names; client names never used as paths. Files `0600` in a `0700` directory outside any web root. Rejected uploads leave no bytes behind. | `test_content_is_sniffed_not_trusted`, `test_size_limit_enforced`, `test_path_traversal_names_are_neutralised`, `test_sr3_*`, `test_sr12_*` |
| Safe downloads | Authenticated and tenant-checked. Always `attachment`, `application/octet-stream`, `nosniff`, `CSP: sandbox`. Quarantined files refused. No public URLs. | `test_download_is_attachment_with_nosniff`, `test_files_are_isolated` |
| Uploading ≠ sharing | New files are `unknown` ("sharing blocked") and nothing is sent to any AI provider — none is configured. | `test_upload_csv_is_private_unscanned_and_unclassified`, `test_security_status_is_honest` |
| Approvals | `approve` needs explicit acknowledgement. Deletion needs the exact item list confirmed. One decision per request. Expiry enforced. Each request is signed with HMAC-SHA256 (`APPROVAL_SIGNING_KEY`, kept out of the database) over every field shown to the approver, so a changed field or a recomputed hash → `409`. | `test_approvals_audit.py`, `test_sr8_*` |
| Deletion safety | Deleting a file creates a `deletion_requests` row (target, scope, expected records, reason, requester) plus a `record_deletion` approval. Approving sets `approved_blocked` / `blocked_until_phase3`. No code path deletes user data. | `test_deletion_request_never_deletes` |
| No fake progress | New tasks are `queued` with `waiting_for="planning_service"`. Approving a plan moves it to `queued` waiting for the execution engine — never `running` or `completed`. Only `running` can reach `completed` in the state machine. | `test_create_task_is_persisted_and_waits_for_planner`, `test_plan_approval_flow_without_execution_engine`, `test_no_path_to_completed_without_running` |
| Request limits and headers | 30 MB body cap, request IDs, `nosniff`, `X-Frame-Options: DENY`, restrictive CSP on API responses, `no-store`, HSTS in production. Web app (production builds): CSP `default-src 'self'` with no external origins, `object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'`. Open-redirect-safe `?next=` handling. Stack traces are never returned. | `test_error_envelope_and_request_id`, `test_oversized_request_rejected`, `web/lib/security-headers.test.ts`, `web/lib/safe-path.test.ts` |
| Production guards | The API refuses to start in production with placeholder/dev secrets, an approval signing key under 32 characters, non-SMTP mail or SMTP without STARTTLS, an `http://` origin, rate limiting disabled, or `TRUST_PROXY_HEADERS=false`. Compose requires `APP_ENV` and `APPROVAL_SIGNING_KEY`. Session and CSRF cookies use the `__Host-` prefix in production. | `test_production_config_guards`, `test_sr13_csrf_cookie_is_host_prefixed_when_secure` |
| No exposed database | Compose publishes no database or API port. Only `web` (127.0.0.1) or Caddy (80/443) listen. | Verified with `docker compose config` and a live stack (see PHASE2_REPORT.md) |

## Designed but NOT enforced yet (Phase 3)

| Item | Current state |
|---|---|
| Privacy mode, AI behaviour rules, tool permissions, allowed domains | Saved and audited, labelled "not enforced" in the UI. No policy engine reads them yet. |
| Malware scanning | Interface present (`FileScanner`). Files are `unscanned` ("scanner not configured"). |
| Encrypted secret storage | No credentials are collected or stored. Integrations cannot be connected. |
| Outbound network / egress policy for AI providers | No AI provider exists, so nothing leaves. No gateway yet. |
| Nonce-based CSP | The web CSP still allows inline scripts (`'unsafe-inline'`), which Next.js needs without per-request nonces. Moving to nonces needs dynamic rendering via middleware. |
| Login lockout | 10 failed logins per 15 min lock that email's sign-in temporarily. This deliberately trades a lockout-DoS risk for protection against password spraying. Accepted for Phase 2. |
| Separation of duties | In a single-user workspace the requester approves their own requests. Second-approver rules come with multi-member workspaces. |
| PostgreSQL Row-Level Security | Not enabled. Isolation is enforced by the application and composite FKs, and proven by tests. |
| Tamper-evident (hash-chained) audit log | Append-only is enforced for the app role and by a trigger, but the schema owner can disable the trigger. Hash chaining or shipping events to an external write-once log is Phase 3. |
| Retention jobs and actual deletion | Deletion is disabled. Retention periods are documented, not automated. |
| Automated, restore-tested backups | `deploy/db/backup.sh` exists. Scheduling it and testing restores is an operator task. |
| MFA, session list / remote sign-out, account lockout notifications | Not implemented. |
| Data export and account deletion | Requests are recorded for manual handling. |

## HTTPS assumptions

Production must run behind TLS: the optional Caddy profile provides automatic certificates. With `APP_ENV=production` cookies are `Secure` and `__Host-`-prefixed, HSTS is sent, and `APP_ORIGIN` must be `https://`. Set `TRUST_PROXY_HEADERS=true` only with the Caddy profile: Caddy overwrites `X-Real-IP`, the only header the API trusts for client IPs. Never publish the API or web port directly in production (web binds to 127.0.0.1).

## Reporting

Until a security contact exists, report issues privately to the repository owner. Don't open public issues for vulnerabilities.
