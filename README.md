# Steward — AI Agent Workspace

A private, approval-first workspace where a non-technical user describes tasks in plain language, reviews the plan, and approves every sensitive action.

**Status: Phase 2 — full-stack foundation.** Accounts, workspaces, tasks, approvals, files, the audit log and settings are real and persisted in PostgreSQL. **The AI agent engine (planner, workers, model providers, integrations, scheduler) is not installed yet — that is Phase 3.** New tasks are saved and queued, and the UI says plainly that nothing is executed.

| Document | What it covers |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Architecture decisions, layout, request lifecycle |
| [API_CONTRACT.md](API_CONTRACT.md) | Every endpoint, error codes, rate limits |
| [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md) | What is enforced and tested, and what is not yet |
| [PHASE2_REPORT.md](PHASE2_REPORT.md) | Completed work, commands run, results, remaining Phase 3 work |
| [web/FRONTEND_GUIDE.md](web/FRONTEND_GUIDE.md) | Conventions for screens and the API adapter |
| `project/`, `chats/`, [docs/DESIGN_HANDOFF.md](docs/DESIGN_HANDOFF.md) | The approved Phase 1 design (visual source of truth) |

## Stack

| Layer | Choice (pinned) |
|---|---|
| Web | Next.js 16.4.3, React 19.3.1, TypeScript 5.9.3, Tailwind CSS 4.3.3, TanStack Query 5.104.5, lucide-react 1.61.0 |
| API | Python 3.13, FastAPI 0.162.0, SQLAlchemy 2.0.55, Alembic 1.20.1, psycopg 3.3.6, Pydantic 2.14.1, argon2-cffi 25.1.0 |
| Database | PostgreSQL 16 |
| Tooling | uv, ruff 0.17.2, mypy 2.4.0, pytest 9.1.1, ESLint 9 + eslint-config-next, Vitest 5.0.5, Playwright (e2e) |
| Deploy | Docker Compose (db, migrate, api, web, optional Caddy for HTTPS) |

Exact Python versions: `api/uv.lock` / `api/requirements.lock`. Exact npm versions: `web/package-lock.json`.

## Quick start with Docker (recommended)

```bash
cp .env.example .env
# Replace every replace-me value (3 passwords + APPROVAL_SIGNING_KEY), e.g. `openssl rand -base64 32`
docker compose up -d --build
open http://localhost:3000
```

The first start creates the database roles (`deploy/db/init-roles.sh`), runs migrations as the schema-owner role, then starts the API as the restricted application role. Only port 3000 is published, bound to 127.0.0.1. PostgreSQL and the API are not reachable from outside the Docker network.

**Email in development:** with `MAIL_BACKEND=outbox`, verification and reset emails are written as `.eml` files instead of being sent. Read them with:

```bash
docker compose exec api sh -c 'ls -t /data/mail-outbox | head -1 | xargs -I{} cat /data/mail-outbox/{}'
```

Open the link in the email to verify your address, then sign in.

## Run locally without Docker

Requires PostgreSQL 16, Python 3.13 with [uv](https://docs.astral.sh/uv/), and Node 22.

```bash
# 1. Database roles + database (once, as a PostgreSQL superuser)
sudo -u postgres STEWARD_OWNER_PASSWORD=devowner STEWARD_APP_PASSWORD=devapp bash deploy/db/init-roles.sh

# 2. API
cd api
uv sync
cat > .env <<'EOF'
ENV=development
DATABASE_URL=postgresql+psycopg://steward_app:devapp@127.0.0.1:5432/steward
MIGRATION_DATABASE_URL=postgresql+psycopg://steward_owner:devowner@127.0.0.1:5432/steward
APP_ORIGIN=http://localhost:3000
EOF
uv run alembic upgrade head
uv run uvicorn app.main:app --port 8000 --no-proxy-headers   # OpenAPI docs: http://localhost:8000/api/v1/docs

# 3. Web (new terminal)
cd web
npm ci
npm run dev                                  # http://localhost:3000 (proxies /api to :8000)
```

Dev emails land in `api/var/mail-outbox/`.

### Demo mode (no backend)

`NEXT_PUBLIC_DEMO_MODE=true npm run dev` runs the original Phase 1 sample data entirely in the browser. It makes no network calls and shows a "DEMO MODE" strip. It is off by default and in the Docker image.

## Checks

```bash
cd api
uv run ruff check app migrations tests && uv run ruff format --check app migrations
uv run mypy app
uv run pytest          # needs the local roles from step 1; creates and drops only *_test databases

cd ../web
npm run lint && npm run typecheck && npm test && npm run build

# End-to-end against the real backend (API on :8000, `npm run build && npm start` on :3000)
cd .. && MAIL_OUTBOX_DIR=api/var/mail-outbox node e2e/smoke.mjs
```

The tests connect as `steward_owner` to create a throwaway `steward_test` database. They refuse to run against any database whose name doesn't end in `_test`. Override the connections with `TEST_OWNER_URL` and `TEST_APP_URL`.

## Deploying to a Hostinger VPS (outline)

1. Point your domain's DNS at the VPS. This repository never changes DNS.
2. Install Docker, then clone the repo and create `.env` with `APP_ENV=production`, `TRUST_PROXY_HEADERS=true`, `APP_ORIGIN=https://<your domain>`, `DOMAIN=<your domain>`, strong passwords, and `MAIL_BACKEND=smtp` with SMTP settings. The API refuses to start in production with the dev mail adapter, plain HTTP, placeholder secrets, a short signing key or `TRUST_PROXY_HEADERS=false`.
3. Run `docker compose --profile tls up -d --build`. Caddy obtains TLS certificates and is the only service listening publicly (ports 80 and 443).
4. Schedule `deploy/db/backup.sh` (database) and back up the `storage` volume (uploaded files). Test restores regularly.
5. Firewall: allow only 22, 80 and 443.

HTTPS is assumed in production: cookies are `Secure` and use the `__Host-` prefix, and HSTS is sent. Don't run production over plain HTTP.

## Repository layout

```
api/        FastAPI service (app/, migrations/, tests/)
web/        Next.js app (app/ routes, features/ screens, components/, lib/api adapter)
deploy/     db role bootstrap, backup script, Caddyfile
e2e/        browser smoke test
project/    Phase 1 design prototype + its docs
```
