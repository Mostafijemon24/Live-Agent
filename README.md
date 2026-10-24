<p align="center">
  <img src="docs/images/banner.png" alt="Steward — Live Agent: a private, approval-first AI agent workspace" width="100%">
</p>

<h1 align="center">Steward · Live Agent</h1>

<p align="center">
  <b>A private, approval-first AI agent workspace.</b><br>
  Describe a task in plain language → review the plan → approve every sensitive action → see exactly what happened.
</p>

<p align="center">
  <a href="README.bn.md"><b>বাংলায় পড়ুন (Bangla guide)</b></a> ·
  <a href="#-quick-start-5-minutes">Quick start</a> ·
  <a href="#%EF%B8%8F-deploy-on-a-hostinger-vps-step-by-step">Deploy on Hostinger</a> ·
  <a href="#%EF%B8%8F-screens">Screens</a> ·
  <a href="#-what-the-agent-can-and-cannot-do">Capabilities &amp; limits</a> ·
  <a href="API_CONTRACT.md">API</a> ·
  <a href="SECURITY_AND_PRIVACY.md">Security</a>
</p>

<p align="center">
  <img alt="status" src="https://img.shields.io/badge/status-Phase%202%20foundation-3448C5">
  <img alt="tests" src="https://img.shields.io/badge/backend%20tests-252%20passing-16803C">
  <img alt="e2e" src="https://img.shields.io/badge/e2e-25%2F25-16803C">
  <img alt="stack" src="https://img.shields.io/badge/Next.js%2016%20·%20FastAPI%20·%20PostgreSQL%2016-172033">
  <a href="LICENSE"><img alt="license" src="https://img.shields.io/badge/license-MIT-16803C"></a>
</p>

> [!IMPORTANT]
> **Current status: Phase 2 — the full-stack foundation is complete; the AI "brain" is not installed yet.**
> Accounts, private workspaces, tasks, approvals, files, the audit log, settings and security are **real, persisted and tested**.
> The autonomous engine (AI planner, workers, model providers, real integrations, scheduler) is **Phase 3**.
> The app is honest about this everywhere: new tasks are saved and show *"Queued — waiting for the planning service"*, and approving something records your decision but runs nothing.
> A **demo mode** shows the complete experience with sample data (screenshots marked *Demo*).

"Steward" is a placeholder product name; the repository is called **Live-Agent**.

---

## Table of contents

1. [What is this, and who is it for?](#-what-is-this-and-who-is-it-for)
2. [How it works](#%EF%B8%8F-how-it-works)
3. [What the agent can and cannot do](#-what-the-agent-can-and-cannot-do)
4. [Rules, conditions and safety guarantees](#-rules-conditions-and-safety-guarantees)
5. [Screens](#%EF%B8%8F-screens)
6. [Quick start (5 minutes)](#-quick-start-5-minutes)
7. [Using the app — guide for everyday users](#-using-the-app--guide-for-everyday-users)
8. [Hosting requirements](#%EF%B8%8F-hosting-requirements)
9. [Deploy on a Hostinger VPS (step by step)](#%EF%B8%8F-deploy-on-a-hostinger-vps-step-by-step)
10. [Which APIs and keys are needed?](#-which-apis-and-keys-are-needed)
11. [Configuration reference](#-configuration-reference)
12. [For developers](#-for-developers)
13. [Testing and quality](#-testing-and-quality)
14. [Security and privacy](#-security-and-privacy)
15. [Roadmap](#%EF%B8%8F-roadmap)
16. [FAQ and troubleshooting](#-faq-and-troubleshooting)
17. [Documentation index](#-documentation-index)

---

## 💡 What is this, and who is it for?

**Steward is a control panel for an AI agent that does real work for you — but only with your permission.**

Most "AI agents" either just chat, or act on your accounts without telling you exactly what they will touch. Steward is built the other way round:

- **You describe a task in plain language** — e.g. *"Audit my WordPress website for performance and SEO problems, prepare a report, and show me recommended fixes before changing anything."*
- **The agent prepares a plan** — every step, which tool it uses, what data it reads, and how risky each step is.
- **You review and approve** — untick steps you don't want, ask questions, or reject the plan.
- **Every sensitive action needs its own one-time approval** — changing a live website, publishing, sending a message, deleting something, or sending data outside your workspace.
- **Everything is logged** — who did what, when, and why.

| You are… | Steward helps you… |
|---|---|
| A **business owner / non-technical user** | Hand off website maintenance, SEO, content and research without learning tools or command lines, while staying in control. |
| An **agency / freelancer** | Run repeatable website audits and content work for clients with a clear approval trail. |
| A **developer / operator** | Self-host a secure, multi-tenant agent platform with real auth, tenant isolation, an audit log and a clean API to plug the Phase 3 engine into. |

**Typical tasks it is designed for:** WordPress maintenance (plugin compatibility, broken links, speed), SEO and content (meta descriptions, content briefs, alt text), research (competitor pricing, schema options), file analysis (CSV/support tickets), code tasks (writing tests in a sandbox), and safe browser workflows (uptime/SSL checks on allowlisted sites).

---

## ⚙️ How it works

<p align="center"><img src="docs/images/how-it-works.png" alt="How a task flows: Describe, Plan, Review plan, Approve actions, Execute, Audit and report" width="100%"></p>

1. **Describe** — Create a task (prompt, type, priority, optional files, execution mode). *Works today.*
2. **Plan** — The AI planner breaks it into steps with tools, data and risk levels. *Phase 3 — until then the task waits honestly in the queue.*
3. **Review plan** — Approve all or some steps, edit, ask, or reject. *UI and API ready.*
4. **Approve actions** — High-impact steps each need a separate, one-time approval showing the exact items, destination, consequences and whether it can be undone. *Works today.*
5. **Execute** — Workers run only approved steps in isolated sandboxes. *Phase 3.*
6. **Audit & report** — Every event lands in an append-only audit log; reports and outputs are stored privately. *Audit log works today.*

### Architecture

<p align="center"><img src="docs/images/architecture.png" alt="Architecture: Browser → Caddy → Next.js web app → FastAPI API → PostgreSQL and private storage; Phase 3 agent engine attaches through a jobs outbox" width="100%"></p>

| Part | Technology | Role |
|---|---|---|
| Web app | Next.js 16, React 19, TypeScript, Tailwind CSS 4 | All 20 screens; talks to the API through one adapter |
| API | Python 3.13, FastAPI, SQLAlchemy 2, Alembic | Auth, sessions, tenant isolation, tasks, approvals, files, audit |
| Database | PostgreSQL 16 | 22 tables; app connects as a restricted role with **no DELETE** permission |
| Files | Private Docker volume | Uploads stored outside any web root under random names |
| Proxy | Caddy 2 | HTTPS certificates, security headers, real client IP |
| Phase 3 engine | Planner · workers · policy engine · model providers · tools | Plugs into ready-made interfaces (`api/app/ports`) and the `jobs` outbox table |

More detail: [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 🧠 What the agent can and cannot do

### Capabilities

| Capability | Today (Phase 2) | After Phase 3 |
|---|---|---|
| Create tasks in plain language, with type, priority, mode, files | ✅ Real, saved to the database | ✅ |
| Prepare a step-by-step plan with risk labels | ⏳ Task waits for the planner (shown honestly) | ✅ AI planner |
| Review, edit, partially approve or reject plans | ✅ UI + API (demo shows it with sample plans) | ✅ |
| One-time approvals for sensitive actions with exact scope | ✅ Real records, signed and audited | ✅ Enforced at run time |
| Upload and classify private files | ✅ Real, type-checked, private storage | ✅ + malware scanning |
| Request file deletion (via approval) | ✅ Request + approval recorded, **nothing deleted** | ✅ Soft delete + retention |
| Automations (manual / scheduled) | ✅ Saved; manual runs queue a task; schedules stay paused | ✅ Scheduler |
| Integrations (WordPress, Notion, cloud storage, email, browser, AI provider) | 🔌 Listed with permissions; connecting says "Phase 3" | ✅ Secure OAuth / server flows |
| Activity & audit log, notifications, security status, settings | ✅ Real | ✅ |
| Run AI models, browse websites, change live sites, send email | ❌ Not installed | ✅ Only after approval |

### Hard limits — what the agent will never do

- ❌ Act on anything **without an approved plan**, and never run a high-impact step without its **own** approval.
- ❌ Treat **uploading a file as permission to share it**. New files are *Unknown — sharing blocked* until you classify them.
- ❌ Send **Private** or **Unknown** files to an external AI provider.
- ❌ Ask for or store **your passwords or API keys in the browser** — integrations will use secure server-side sign-in flows.
- ❌ **Delete data directly.** Deletion is always a request listing the exact items, which must be approved; actual deletion is disabled in Phase 2.
- ❌ Pretend something worked. Failed tasks stay *Failed*; "Retry" is only offered when it is safe; simulated results are labelled as simulated.
- ❌ Access another user's workspace, files or history — even by guessing IDs (tested).
- ❌ Visit websites that are not on your allowlist (browser tool, Phase 3).

---

## 📜 Rules, conditions and safety guarantees

| Rule | What it means for you |
|---|---|
| **Approval is per action, once** | Approving "delete 4 files" covers exactly those 4 files, once. Any change needs a new request. There is no "always allow". |
| **Approvals expire** | Pending requests expire (e.g. after 24 h). Expired requests can't be approved. |
| **Approvals are tamper-proof** | Each request is cryptographically signed over everything you see (items, destination, risk, consequences). If anything changes, approval is refused. |
| **Deletion needs double confirmation** | You must tick that you reviewed the exact item list. |
| **Your workspace is private** | Every request is checked against your workspace on the server. Other users get "not found". |
| **Email verification required** | You can only sign in after verifying your email. |
| **Strong passwords** | At least 10 characters including a number. |
| **Rate limits** | Repeated sign-in attempts, sign-ups, password resets, uploads and task creation are limited to stop abuse. |
| **Quotas** (configurable) | Default: 500 tasks per month, 1 GB file storage per workspace, 25 MB per file. |
| **Allowed file types** | PDF, PNG, JPG, DOCX, XLSX, CSV, TXT, MD, JSON. Executables, scripts, HTML/SVG, archives and macro documents are refused. |
| **Roles** | Owner/Admin: everything. Member: create tasks, upload, request deletions. Viewer: read-only. |
| **Settings are preferences until Phase 3** | Privacy mode, AI rules and tool permissions are saved and logged, and clearly marked *Not enforced yet* until the policy engine is installed. |

---

## 🖼️ Screens

**Two sets of screenshots:** *Real* = what the application does today against the real backend. *Demo* = the complete designed experience with sample data (demo mode runs entirely in your browser and is labelled "DEMO MODE").

### Dashboard (Overview)

| Demo — full experience | Real — today |
|---|---|
| <img src="docs/images/demo/04-dashboard.png" alt="Dashboard in demo mode"> | <img src="docs/images/real/07-overview.png" alt="Dashboard on the real backend"> |

### Plan review and approvals — the heart of the product

| Plan review (Demo) | External data transfer warning (Demo) |
|---|---|
| <img src="docs/images/demo/07-plan-review.png" alt="Plan review with risk labels"> | <img src="docs/images/demo/12-approvals-external-transfer.png" alt="Approval for sending files externally"> |
| **Live website change (Demo)** | **Deletion needs exact-item confirmation (Demo)** |
| <img src="docs/images/demo/13-approvals-production-change.png" alt="Approval for a production website change"> | <img src="docs/images/demo/14-approval-delete-confirm.png" alt="Deletion confirmation dialog"> |
| **Task waiting honestly for the planner (Real)** | **Deletion request — decision recorded, nothing deleted (Real)** |
| <img src="docs/images/real/09-plan-waiting-for-planner.png" alt="Task waiting for the planning service"> | <img src="docs/images/real/14-approval-deletion.png" alt="Real deletion approval"> |

<details>
<summary><b>Tasks — create, list, details, logs</b> (click to expand)</summary>

| | |
|---|---|
| New task composer (Demo) <img src="docs/images/demo/05-new-task.png"> | Task list with filters (Demo) <img src="docs/images/demo/06-tasks-list.png"> |
| Task detail — summary (Demo) <img src="docs/images/demo/09-task-detail-summary.png"> | Task detail — steps (Demo) <img src="docs/images/demo/10-task-detail-steps.png"> |
| Run logs (Demo) <img src="docs/images/demo/11-task-detail-logs.png"> | Approve plan dialog (Demo) <img src="docs/images/demo/08-approve-plan-dialog.png"> |
| Task list (Real) <img src="docs/images/real/10-tasks.png"> | Task logs (Real) <img src="docs/images/real/11-task-detail-logs.png"> |
| New task (Real) <img src="docs/images/real/08-new-task.png"> | |
</details>

<details>
<summary><b>Files &amp; Knowledge</b></summary>

| | |
|---|---|
| Files (Demo) <img src="docs/images/demo/15-files.png"> | File details & classification (Demo) <img src="docs/images/demo/16-file-drawer.png"> |
| Real uploads — "Not scanned", "Unknown — sharing blocked" <img src="docs/images/real/12-files.png"> | File drawer (Real) <img src="docs/images/real/13-file-drawer.png"> |
| Approve-once dialog (Real) <img src="docs/images/real/15-approve-dialog.png"> | |
</details>

<details>
<summary><b>Automations, Integrations, Reports &amp; Activity</b></summary>

| | |
|---|---|
| Automations (Demo) <img src="docs/images/demo/17-automations.png"> | New automation wizard (Demo) <img src="docs/images/demo/18-automation-wizard.png"> |
| Integrations (Demo) <img src="docs/images/demo/19-integrations.png"> | Integration permissions drawer (Demo) <img src="docs/images/demo/20-integration-drawer.png"> |
| Reports & activity (Demo) <img src="docs/images/demo/21-reports-activity.png"> | Real audit log <img src="docs/images/real/17-activity-audit-log.png"> |
| Integrations (Real) <img src="docs/images/real/16-integrations.png"> | |
</details>

<details>
<summary><b>Security, Settings, Notifications, Help, System states</b></summary>

| | |
|---|---|
| Security & Privacy (Demo) <img src="docs/images/demo/22-security-privacy.png"> | Security status (Real — honest checklist) <img src="docs/images/real/18-security.png"> |
| AI behaviour settings (Demo) <img src="docs/images/demo/23-settings-ai.png"> | Settings (Real) <img src="docs/images/real/19-settings.png"> |
| Notifications (Demo) <img src="docs/images/demo/24-notifications.png"> | Notifications (Real) <img src="docs/images/real/20-notifications.png"> |
| Help & Getting Started (Demo) <img src="docs/images/demo/25-help.png"> | System states (Demo) <img src="docs/images/demo/26-system-states.png"> |
</details>

<details>
<summary><b>Sign-up, verification, onboarding, landing</b></summary>

| | |
|---|---|
| Landing page (Demo) <img src="docs/images/demo/01-landing.png"> | Register (Real) <img src="docs/images/real/01-register.png"> |
| Check your inbox (Real) <img src="docs/images/real/02-verify-email-sent.png"> | Email verified (Real) <img src="docs/images/real/03-email-verified.png"> |
| Sign in (Real) <img src="docs/images/real/04-login.png"> | Onboarding — goals (Real) <img src="docs/images/real/05-onboarding.png"> |
| Onboarding — safety approvals (Demo) <img src="docs/images/demo/03-onboarding-important-actions.png"> | Onboarding summary (Real) <img src="docs/images/real/06-onboarding-summary.png"> |
</details>

<details>
<summary><b>Mobile</b></summary>

| Dashboard | Navigation | Approvals |
|---|---|---|
| <img src="docs/images/demo/27-mobile-dashboard.png" width="260"> | <img src="docs/images/demo/28-mobile-navigation.png" width="260"> | <img src="docs/images/demo/29-mobile-approvals.png" width="260"> |
</details>

---

## 🚀 Quick start (5 minutes)

### Option A — Docker (recommended, works the same on your laptop and a VPS)

Requirements: [Docker](https://docs.docker.com/get-docker/) with Docker Compose v2, and Git.

```bash
git clone https://github.com/Mostafijemon24/Live-Agent.git
cd Live-Agent
cp .env.example .env
```

Open `.env` and replace **every** `replace-me` (three database passwords and `APPROVAL_SIGNING_KEY`). Generate strong values with:

```bash
openssl rand -base64 32     # run once per value
```

Start everything:

```bash
docker compose up -d --build
```

Open **http://localhost:3000** and register.

In development, emails (verification, password reset) are **not sent** — they are saved as files. Read the latest one:

```bash
docker compose exec api sh -c 'cat "/data/mail-outbox/$(ls -t /data/mail-outbox | head -1)"'
```

Copy the `http://localhost:3000/verify-email?token=…` link into your browser, then sign in.

### Option B — Demo mode only (no database, no backend)

See the full designed experience with sample data in 1 minute (requires Node.js 22):

```bash
cd web
npm ci
NEXT_PUBLIC_DEMO_MODE=true npm run dev
```

Open http://localhost:3000 and sign in with **any** email and password (use the password `error` to see the error state). Nothing is sent anywhere; data resets on reload.

### Option C — Run each part manually (for development)

<details>
<summary>Show manual setup (PostgreSQL 16 + Python 3.13 + Node 22)</summary>

```bash
# 1) Database roles + database (once, as a PostgreSQL superuser)
sudo -u postgres STEWARD_OWNER_PASSWORD=devowner STEWARD_APP_PASSWORD=devapp \
  bash deploy/db/init-roles.sh

# 2) API  (uses uv: https://docs.astral.sh/uv/)
cd api
uv sync
cat > .env <<'EOF'
ENV=development
DATABASE_URL=postgresql+psycopg://steward_app:devapp@127.0.0.1:5432/steward
MIGRATION_DATABASE_URL=postgresql+psycopg://steward_owner:devowner@127.0.0.1:5432/steward
APP_ORIGIN=http://localhost:3000
EOF
uv run alembic upgrade head
uv run uvicorn app.main:app --port 8000 --no-proxy-headers
#   API docs (development only): http://localhost:8000/api/v1/docs

# 3) Web (new terminal)
cd web
npm ci
npm run dev          # http://localhost:3000 — proxies /api/* to :8000
```
Development emails are written to `api/var/mail-outbox/`.
</details>

---

## 🙋 Using the app — guide for everyday users

1. **Create your account** — Register with your name, email and a password (10+ characters with a number). Open the link in the verification email, then sign in.
2. **Set up your workspace (2 minutes)** — Choose your goals, where the agent may work (workspace files, connected apps, approved websites) and which actions always need your approval. Safe defaults are pre-selected.
3. **Create a task** — Go to **New task** (or use **Quick task** on the Overview). Write what you need in one or two sentences. Choose:
   - **Plan only** *(safest — default)*: the agent only prepares a plan.
   - **Prepare changes for review**: drafts changes inside your workspace; nothing is applied.
   - *Execute approved steps*: disabled until Phase 3.
4. **Review the plan** — Each step shows its tool and risk (*Read only*, *Workspace only*, *Production change*, *Publish*, *External transfer*). Untick steps you don't want, ask a question, edit, approve or reject.
   *Today the plan page explains that the planner isn't installed yet; your task stays safely queued.*
5. **Handle approvals** — The **Approvals** page lists everything waiting for you, with coloured warnings (red = data leaves your workspace or deletion; amber = live change, publish, send). Check *what*, *why*, *which items*, *destination*, *consequences* and *can it be undone*, then **Approve once**, **Reject** or **Request changes**.
6. **Add files** — **Files & Knowledge → Add file.** Files stay private. Set a privacy classification (*Private*, *Approved for selected integration*, *Public*, *Unknown*). To delete, use **Request deletion** — it becomes an approval.
7. **Watch progress** — **Tasks** shows every task with filters; open one to see its plan, logs, inputs, outputs and audit events. **Reports & Activity** shows the full audit log.
8. **Stay safe** — **Security & Privacy** shows your privacy mode, what is enforced and what is not yet, recent decisions and blocked actions. **Settings** holds your profile, notifications, AI behaviour, allowed domains and usage.

**When should I use it?** Whenever you want work done on your website, content, research or files **without** giving anyone (human or AI) unchecked access — and you want a record of every decision.

---

## 🖥️ Hosting requirements

| | Minimum (Phase 2, small team) | Recommended (Phase 3 with AI engine) |
|---|---|---|
| Server | VPS with 2 vCPU, 4 GB RAM, 40 GB SSD (e.g. Hostinger **KVM 2**) | 4–8 vCPU, 8–16 GB RAM, 100+ GB SSD (Hostinger **KVM 4 / KVM 8**) |
| OS | Ubuntu 24.04 LTS (or 22.04) | Same |
| Software | Docker Engine + Docker Compose v2, Git | Same |
| Network | Public IPv4, ports 22, 80, 443 open | Same + outbound access to your AI provider |
| Domain | A domain or sub-domain pointing to the VPS (A record) | Same |
| Email | SMTP account (Hostinger Email, Google Workspace, Brevo, Amazon SES, Mailgun…) | Same |
| Backups | Daily DB dump + copy of the `storage` volume off the server | Same + tested restores |

> Shared web hosting (PHP-only) is **not** suitable — you need a VPS (or any server that runs Docker).
> The sizes above are planning estimates, not measured capacity. A local baseline (one API worker) is in [PHASE2_REPORT.md](PHASE2_REPORT.md).

---

## ☁️ Deploy on a Hostinger VPS (step by step)

1. **Buy a VPS** (KVM 2 or higher) and choose **Ubuntu 24.04**. Note the server IP.
2. **Point your domain**: in your DNS panel create an **A record** `agent.yourdomain.com → <VPS IP>`.
3. **Log in and install Docker**:
   ```bash
   ssh root@<VPS IP>
   curl -fsSL https://get.docker.com | sh
   ufw allow 22 && ufw allow 80 && ufw allow 443 && ufw --force enable
   ```
4. **Get the code**:
   ```bash
   git clone https://github.com/Mostafijemon24/Live-Agent.git /opt/live-agent
   cd /opt/live-agent
   cp .env.example .env
   nano .env
   ```
5. **Fill in `.env` for production**:
   ```ini
   POSTGRES_SUPERUSER_PASSWORD=<random>
   STEWARD_OWNER_PASSWORD=<random>
   STEWARD_APP_PASSWORD=<random>
   APPROVAL_SIGNING_KEY=<random, 32+ characters>
   APP_ENV=production
   APP_ORIGIN=https://agent.yourdomain.com
   DOMAIN=agent.yourdomain.com
   TRUST_PROXY_HEADERS=true
   MAIL_BACKEND=smtp
   MAIL_FROM=Steward <no-reply@yourdomain.com>
   SMTP_HOST=smtp.hostinger.com
   SMTP_PORT=587
   SMTP_USERNAME=no-reply@yourdomain.com
   SMTP_PASSWORD=<your mailbox password>
   ```
   The API **refuses to start** in production if a secret is still a placeholder, the signing key is short, mail isn't SMTP, the origin isn't HTTPS, or the proxy setting is missing — this is intentional.
6. **Start with automatic HTTPS (Caddy)**:
   ```bash
   docker compose --profile tls up -d --build
   docker compose ps          # db, api, web, caddy should be running/healthy
   ```
7. Open **https://agent.yourdomain.com**, register, verify your email, sign in.
8. **Backups** (daily at 03:00):
   ```bash
   crontab -e
   0 3 * * * cd /opt/live-agent && ./deploy/db/backup.sh /opt/backups >> /var/log/steward-backup.log 2>&1
   ```
   Also copy the `storage` Docker volume (uploaded files) and `/opt/backups` to another location. Test a restore regularly.
9. **Update later**:
   ```bash
   cd /opt/live-agent && git pull && docker compose --profile tls up -d --build
   ```
   Database migrations run automatically (the one-shot `migrate` service) before the API starts.

---

## 🔑 Which APIs and keys are needed?

| What | Needed now (Phase 2)? | Notes |
|---|---|---|
| Database passwords (3) | **Yes** | Generated by you, stored only in `.env` on the server |
| `APPROVAL_SIGNING_KEY` | **Yes** | Random 32+ characters; signs approval requests |
| SMTP mailbox | **Yes in production** | For verification and password-reset emails |
| Domain + DNS | **Yes in production** | For HTTPS |
| AI model provider key (OpenAI, Google Gemini, Mistral, or a local model via Ollama) | No — Phase 3 | Will be configured **on the server only**, never in the browser; files are only sent to it with per-action approval |
| WordPress connection (Application Password / OAuth) | No — Phase 3 | Read-only by default; writes need per-action approval |
| Notion, Google Drive / cloud storage, email-sending integrations | No — Phase 3 | Least-privilege scopes, encrypted storage |
| Malware scanner (e.g. ClamAV) | No — Phase 3 | Files show *Not scanned* until connected |

**This app never asks you to paste passwords or API keys into the web interface.**

---

## 🧾 Configuration reference

| Variable | Default | Purpose |
|---|---|---|
| `APP_ENV` | — (required) | `development` or `production` |
| `APP_ORIGIN` | `http://localhost:3000` | Public URL of the web app (CSRF check, email links). `https://` in production |
| `DOMAIN` | `localhost` | Domain for Caddy's HTTPS certificate |
| `POSTGRES_SUPERUSER_PASSWORD` | — | Database superuser (used only by the DB container) |
| `STEWARD_OWNER_PASSWORD` | — | Schema-owner role (runs migrations) |
| `STEWARD_APP_PASSWORD` | — | Restricted role used by the API (no DELETE, no DDL) |
| `APPROVAL_SIGNING_KEY` | — | HMAC key for approval requests (32+ chars in production) |
| `TRUST_PROXY_HEADERS` | `false` | `true` only behind Caddy (`--profile tls`) |
| `WEB_BIND` | `127.0.0.1` | Interface the web port binds to |
| `MAIL_BACKEND` | `outbox` | `outbox` (dev files) · `smtp` · `disabled` |
| `MAIL_FROM`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` | — | Outgoing email |
| `MAX_UPLOAD_BYTES` | 25 MB | Per-file limit |
| `WORKSPACE_STORAGE_QUOTA_BYTES` | 1 GB | Storage per workspace |
| `MONTHLY_TASK_QUOTA` | 500 | Tasks per workspace per month |
| `AUTH_RESPONSE_FLOOR_MS` | 400 | Minimum response time for sign-up/reset (prevents account guessing) |
| `NEXT_PUBLIC_DEMO_MODE` | `false` | Build-time: `true` = in-browser sample data only |

Full list with comments: [.env.example](.env.example).

---

## 👩‍💻 For developers

```
api/                FastAPI service
  app/core/         config, database, security, errors, CSRF/session deps, rate limits
  app/domain/       enums and the task state machine
  app/models.py     SQLAlchemy models (22 tables)
  app/schemas/      Pydantic request/response models
  app/ports/        interfaces for Phase 3 (planner, model provider, job queue, worker, tools, policy, storage, scanner, mailer)
  app/adapters/     Phase 2 implementations (safe "not configured" adapters, private storage, mail)
  app/services/     business logic, always scoped to the signed-in workspace
  app/routers/      HTTP routes (/api/v1)
  migrations/       Alembic migrations (0001 schema, 0002 privileges, 0003 tenant keys)
  tests/            pytest (isolated *_test database)
web/                Next.js app
  app/              routes (public pages + the (app) shell)
  features/         one folder per screen area
  components/       UI kit + app shell
  lib/api/          AgentApi interface, HTTP adapter, demo adapter, wire types
deploy/             DB role bootstrap, backup script, Caddyfile
e2e/                browser end-to-end smoke test
docs/images/        README screenshots, banner and diagrams
project/, chats/    the approved Phase 1 design prototype
```

**Key ideas**
- **One API adapter** (`web/lib/api`): every screen calls `api.*`. Real HTTP by default; the demo adapter is only included when built with `NEXT_PUBLIC_DEMO_MODE=true`.
- **Tenant isolation** happens server-side on every query; the workspace comes from the session, never from the request.
- **Task state machine** in `api/app/domain/task_states.py` — the only place that allows status changes (tested for all 121 combinations).
- **Plugging in Phase 3**: implement `TaskPlanner`, `JobQueue`/`Worker`, `ModelProvider`, `ToolRegistry`, `ApprovalPolicy`, `FileScanner` from `api/app/ports` and swap them in `api/app/adapters`. Workers read the `jobs` table (already filled with `task.plan` / `task.execute` jobs).
- **API reference**: [API_CONTRACT.md](API_CONTRACT.md) (50 endpoints, error codes, rate limits) and the live OpenAPI docs at `/api/v1/docs` in development.

---

## ✅ Testing and quality

```bash
# Backend
cd api
uv run ruff check app migrations tests && uv run ruff format --check app migrations tests
uv run mypy app
uv run pytest                     # 252 tests; creates and drops only *_test databases

# Frontend
cd ../web
npm run lint && npm run typecheck && npm test && npm run build

# End-to-end (API on :8000, `npm run build && npm start` on :3000)
cd .. && MAIL_OUTBOX_DIR=api/var/mail-outbox node e2e/smoke.mjs
```

Latest verified results (2026-10-24): 252 backend tests passing (three consecutive runs), 25 frontend unit tests, production build, end-to-end 25/25 steps with 0 console errors, `npm audit` and `pip-audit` with 0 known vulnerabilities. An independent security review found 13 issues; all were fixed with regression tests, except two minor items that are documented as accepted risks ([SECURITY_REVIEW.md](SECURITY_REVIEW.md)). Full report: [PHASE2_REPORT.md](PHASE2_REPORT.md).

---

## 🔒 Security and privacy

Highlights (all enforced **and** covered by automated tests):

- Argon2id password hashing · server-side sessions in HttpOnly cookies · CSRF protection · email verification · secure password reset that signs out every session
- No account guessing: identical responses and timing for existing and unknown emails
- Strict tenant isolation (server checks + database constraints) · role-based permissions
- Restricted database role with **no DELETE** · append-only audit log
- Private, type-checked file storage · safe downloads · uploads never imply sharing
- Signed, expiring, one-time approvals · deletion only via approval (disabled until Phase 3)
- Rate limits, security headers, Content-Security-Policy, production configuration guards

What is **not** enforced yet (policy engine, malware scanning, encrypted secret storage, egress control, row-level security) is listed honestly in [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md).

---

## 🗺️ Roadmap

| Phase | Status | Scope |
|---|---|---|
| **1 — Design** | ✅ Done | Clickable prototype of all 20 screens (`project/`) |
| **2 — Foundation** | ✅ Done | Real auth, workspaces, tasks, approvals, files, audit, API, tests, Docker deployment, security review |
| **3 — Agent engine** | 🔜 Next | AI planner, job workers, policy engine enforcing approvals and privacy, model providers (OpenAI / Gemini / Mistral / local), WordPress/Notion/storage/email integrations, isolated browser and code sandboxes, malware scanning, scheduler, soft-delete & retention, monitoring |

---

## ❓ FAQ and troubleshooting

<details><summary><b>I created a task but nothing happens.</b></summary>
That is expected in Phase 2. The task is saved and shows <i>Queued — waiting for the planning service</i>. The AI planner arrives in Phase 3. Use demo mode to preview the full flow.</details>

<details><summary><b>I didn't receive the verification email.</b></summary>
In development (<code>MAIL_BACKEND=outbox</code>) emails are saved as files, not sent — see the Quick start command to read them. In production check your SMTP settings and the API logs: <code>docker compose logs api</code>.</details>

<details><summary><b>"That email and password combination did not match, or the email address hasn't been verified yet."</b></summary>
For security the app never says which part is wrong. Make sure you verified your email; otherwise use <b>Forgot password</b>.</details>

<details><summary><b>"Too many attempts."</b></summary>
Rate limits protect accounts. Wait 15–60 minutes (the response includes a <code>Retry-After</code> time).</details>

<details><summary><b>The API container keeps restarting in production.</b></summary>
Run <code>docker compose logs api</code>. The most common cause is the production safety check: a <code>replace-me</code> secret, a short <code>APPROVAL_SIGNING_KEY</code>, <code>MAIL_BACKEND</code> not <code>smtp</code>, <code>APP_ORIGIN</code> not <code>https://</code>, or <code>TRUST_PROXY_HEADERS</code> not <code>true</code>.</details>

<details><summary><b>My upload was refused.</b></summary>
Only PDF, PNG, JPG, DOCX, XLSX, CSV, TXT, MD and JSON up to 25 MB are accepted, the file extension must match the real content, and files containing scripts, macros or executables are refused.</details>

<details><summary><b>Can I connect my WordPress site now?</b></summary>
Not yet — integrations arrive in Phase 3 with secure server-side sign-in. The app will never ask for your password in the browser.</details>

<details><summary><b>Is my data sent to an AI company?</b></summary>
No. No AI provider is configured in Phase 2, so nothing leaves your server. In Phase 3, files will only be sent with your explicit, per-action approval, and Private/Unknown files are blocked.</details>

---

## 📚 Documentation index

| Document | Contents |
|---|---|
| [README.bn.md](README.bn.md) | Full guide in Bangla (বাংলা) |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Architecture decisions |
| [API_CONTRACT.md](API_CONTRACT.md) | Every endpoint, error codes, rate limits, roles |
| [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md) | Enforced vs. not-yet-enforced controls |
| [SECURITY_REVIEW.md](SECURITY_REVIEW.md) | Independent security review and fixes |
| [PHASE2_REPORT.md](PHASE2_REPORT.md) | What was built, commands run, results, load baseline, Phase 3 list |
| [web/FRONTEND_GUIDE.md](web/FRONTEND_GUIDE.md) | Conventions for screens and the API adapter |
| [docs/DESIGN_HANDOFF.md](docs/DESIGN_HANDOFF.md), `project/` | The approved Phase 1 design |
| [LICENSE](LICENSE) | MIT license |

**License:** [MIT](LICENSE) © 2026 Mostafijemon24 — free to use, modify and distribute, including commercially, as long as the copyright notice is kept. Provided "as is", without warranty.
