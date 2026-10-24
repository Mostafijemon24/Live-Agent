# Phase 3 report — secure AI agent engine

Date: 2026-10-24 · Branch: `phase-3-agent-engine` · **Not deployed to production** (as instructed).

## 1. What was built

| Area | Implementation | Key files |
|---|---|---|
| Model interface | Provider-neutral `ModelProvider` + `ProviderInfo` (label, model, local/external, data disclosure). `NoProvider` (default), deterministic `MockProvider` (refused in production), `OpenAICompatibleProvider` (OpenAI or self-hosted Ollama/vLLM). `ModelGateway`: configured check, privacy authorisation, redaction, input limit, monthly token/call quotas, bounded retries with backoff, `model_calls` usage rows (no prompt text). No fallback provider. | `api/app/engine/providers.py` |
| Strict privacy | Data reaches an external provider only with policy permission and, when required, a one-time `external_transfer` approval bound to the exact data/provider/model. No model → tasks wait, nothing sent. | `engine/policy.py` (`evaluate_model_transfer`), `engine/orchestrator.py` (`handle_plan`) |
| Planner | Model proposes goal/tool/args/expected output only; server validates (registry, Pydantic schemas with `extra=forbid`, attached files only, backward step references, step limit) and derives permissions, classifications, destinations, impact, approval need, idempotency, timeout, retries. One bounded repair. Plan versions for re-planning. | `engine/planner.py` |
| Policy engine | Default deny, `POLICY_VERSION`; baseline rules settings can't weaken; privacy modes strict/approval/custom; evaluated at planning and again before each step. | `engine/policy.py` |
| Approvals | HMAC binding over displayed fields + operation, args hash, targets, step, expiry, policy version; verified before execution incl. approver's current role; one-time (`executed`), else `invalidated` and re-requested; DB trigger keeps decisions final and execution state forward-only. | `services/approvals.py`, migration `0005` |
| Data classification & egress | public/internal/confidential/unknown (most sensitive wins); egress client with allowlist, private/metadata IP block, DNS pinning, same-host redirects, size/time caps, overall deadline; redaction of secrets/PII. | `engine/classification.py`, `engine/egress.py`, `engine/redaction.py` |
| Queue & workers | PostgreSQL job queue (SKIP LOCKED, priorities, fair share, backpressure, heartbeats/leases, stale recovery, jittered backoff, dead-letter, cancellation, ownership checks). Workers: orchestrator, tools, deletion, scheduler; graceful shutdown; heartbeats in `workers`; Compose healthchecks. | `engine/queue.py`, `workers/runtime.py`, `workers/health.py` |
| Tools & sandbox | Registry: files.read/analyze, web.inspect, seo.audit, wordpress.read, report.write, ai.summarize, code.run_python, files.request_deletion; unbuilt tools listed unavailable. Sandbox: namespaces, read-only root, hidden dirs locked via nested unprivileged user namespace, no capabilities, rlimits, output cap; fails closed. | `engine/tools/`, `engine/sandbox.py` |
| DB role separation | `steward_worker`, `steward_deleter`, `steward_readonly` (+ existing app/owner); column-limited grants; no DELETE/TRUNCATE/DDL for runtime roles. | migrations `0004`, `0005`, `deploy/db/init-roles.sh` |
| Deletion workflow | preview → approval → re-validation (binding, role, unchanged file) → transactional soft delete + trash move with recovery → audit → restore → purge after retention (tombstone). | `engine/deletion.py` |
| Integrations | WordPress read-only (public REST API, site URL only, allowlisted, worker-verified). AI provider configured by the administrator. Others honestly "not built". | `engine/integrations.py`, `engine/tools/web_tools.py` |
| Scheduler | Due automations → one task per slot (row lock + idempotency key), purge scheduling, stale-job recovery. | `engine/scheduler.py` |
| Observability | `/agent/status` (provider, worker liveness, queue depth, policy version), audit events for planning, policy blocks, binding failures, executions, deletions; structured worker logs with job ids. | `services/agent.py`, `engine/records.py` |
| Frontend | Agent status card; plan review with policy decisions, destinations, classifications and exact arguments; task results/output (escaped), artifacts; bound approvals; Recently deleted + restore; WordPress connect; copy sweep. | `web/features/*`, `web/lib/api/*` |
| Deployment | Compose: four worker services, internal `backend` network (no internet for API/deletion/scheduler), `egress` network for orchestrator/tools only, read-only root filesystems, dropped capabilities, `no-new-privileges`, resource limits for the tools worker. | `docker-compose.yml`, `.env.example` |

## 2. Required end-to-end flow — status

| Step | Evidence | Status |
|---|---|---|
| Create task → persisted | `test_full_flow_plan_approve_execute_report`, `e2e/agent-flow.mjs` | Passed |
| Planner generates a validated plan | same + planner tests | Passed |
| Policy engine evaluates each step | plan review shows decisions (screenshot `docs/images/phase3/02`) | Passed |
| User approves (plan + bound step approval) | agent-flow steps 6–8 (UI clicks) | Passed |
| Isolated worker executes a safe step | tools worker ran `seo.audit` against a local test site | Passed |
| Events and outputs persisted, UI shows result | task detail + report download | Passed |
| Audit records it | `plan.created`, `approval.approve`, `step.executed`, `task.finished` | Passed |
| Unauthorized external transfer blocked | non-allowlisted site → step blocked, never contacted; external model without permission → no call made | Passed |
| Unauthorized deletion blocked | agent can only propose; unconfirmed/forced/changed/demoted approvals refused | Passed |
| Same flow in Docker Compose | API image rebuilt; workers healthy; task planned/approved/executed/report downloaded inside containers; API container has no internet; sandbox reports unavailable (fails closed) | Passed (web container not started: port conflict with the local test server; its image was the Phase 2 build) |

## 3. Checks run (2026-10-24)

| Check | Command | Result |
|---|---|---|
| Lint / format | `uv run ruff check .` · `uv run ruff format --check .` | Passed |
| Types | `uv run mypy app` (strict, 59 files) | Passed |
| Backend tests | `uv run pytest` | **413 passed, 1 skipped** (fork-bomb limit not enforceable as real root in this dev container) |
| Frontend | `npx tsc --noEmit` · `npm run lint` · `npx vitest run` · `npm run build` | Passed (39 tests) |
| Browser e2e | `node e2e/smoke.mjs` · `node e2e/agent-flow.mjs` | 25/25 · 13/13 |
| Migrations | upgrade → downgrade → upgrade test; fresh-DB schema diff vs dev DB | Passed |
| Docker | `docker compose config`; compose up with built API image + in-container flow | Passed (see §2) |
| Dependency audit | `pip-audit -r requirements.lock` · `npm audit --omit=dev` | 0 known vulnerabilities |
| Independent security review | separate read-only agent | 11 findings; see §4 |

## 4. Security review

Recorded before fixes in [SECURITY_REVIEW.md](SECURITY_REVIEW.md) (Phase 3 section). Summary:

- **P3-SR-1 (High)** sandbox mask unmount → **Fixed** (nested unprivileged user namespace; test proves umount/remount fail, CapEff 0).
- **P3-SR-2..5 (Medium)** hidden arguments, redaction gaps, queue lease races, over-broad worker grants → **Fixed** with tests.
- **P3-SR-6 (Medium)** sandbox resource exhaustion → **Fixed (partial)**: incremental output cap; `RLIMIT_NPROC` effective only for the non-root production worker.
- **P3-SR-7..9 (Low)** → Fixed; **P3-SR-8** partial (abandoned tool threads after timeout remain); **P3-SR-10** partly fixed / accepted; **P3-SR-11** fixed except the accepted no-two-person-rule item.

## 5. Known limitations and risks (honest list)

- **No complete security claim.** Controls reduce specific risks; see [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md).
- **Sandbox** is process-level isolation on the worker host, not a VM. Docker's default seccomp blocks it, so code steps are unavailable in the default Compose deployment (by design). Hostile code needs gVisor/Firecracker.
- **Egress** is enforced in the application and by Compose network separation, but the `egress` network has no firewall/proxy; with `EGRESS_PROXY_URL` the proxy must block private ranges itself.
- **Redaction** is pattern-based and cannot catch every secret or personal datum.
- **Real LLM quality** was not exercised in automated tests (deterministic mock planner and a fake OpenAI-compatible server were used). Plan quality with a real model depends on the model; invalid plans fail visibly after one repair.
- **Queue fairness** is FIFO with a per-workspace running cap; a global pending cap is shared across tenants.
- **Timed-out tool threads** can keep running in the background until their own (bounded) timeouts end.
- **Not built:** WordPress write, email sending, Notion, cloud storage, full browser automation, malware scanning, encrypted per-workspace secret storage, hash-chained audit log, row-level security.
- **Self-approval** is possible in single-user workspaces (no two-person rule).
- **Load testing** of the engine was not performed in this phase (Phase 2 baseline only).

## 6. Steps that still require your approval

- Merging `phase-3-agent-engine` into `main`.
- Any production deployment (DNS, VPS, real secrets, a real model provider key) — not done.
- For an existing Phase 2 server: create the three new database roles before migrating (README → Deploy).
