"""Test fixtures.

Safety: tests only ever touch databases whose name ends in `_test`. The test
database is dropped and recreated from migrations at the start of the run, using
the schema-owner role; the API under test connects as the least-privileged
application role, exactly like production.

Environment (defaults match the documented local setup):
  TEST_OWNER_URL  postgresql+psycopg://steward_owner:devowner@127.0.0.1:5432/postgres
  TEST_APP_URL    postgresql+psycopg://steward_app:devapp@127.0.0.1:5432/steward_test
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import uuid
from collections.abc import Iterator
from email import message_from_bytes
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

OWNER_ADMIN_URL = os.environ.get(
    "TEST_OWNER_URL", "postgresql+psycopg://steward_owner:devowner@127.0.0.1:5432/postgres"
)
APP_URL = os.environ.get("TEST_APP_URL", "postgresql+psycopg://steward_app:devapp@127.0.0.1:5432/steward_test")
TEST_DB = make_url(APP_URL).database or ""
if not TEST_DB.endswith("_test"):
    raise SystemExit(f"Refusing to run tests against database {TEST_DB!r}: the name must end with '_test'.")
OWNER_TEST_URL = make_url(OWNER_ADMIN_URL).set(database=TEST_DB).render_as_string(hide_password=False)


def _role_url(role: str, env: str, default_pw: str) -> str:
    return (
        make_url(APP_URL)
        .set(username=role, password=os.environ.get(env, default_pw))
        .render_as_string(hide_password=False)
    )


WORKER_URL = _role_url("steward_worker", "TEST_WORKER_PASSWORD", "devworker")
DELETER_URL = _role_url("steward_deleter", "TEST_DELETER_PASSWORD", "devdeleter")
READONLY_URL = _role_url("steward_readonly", "TEST_READONLY_PASSWORD", "devreadonly")

_tmp = Path(tempfile.mkdtemp(prefix="steward-tests-"))
os.environ.update(
    {
        "ENV": "test",
        "DATABASE_URL": APP_URL,
        "MIGRATION_DATABASE_URL": OWNER_TEST_URL,
        "APP_ORIGIN": "http://testserver.local",
        "STORAGE_DIR": str(_tmp / "storage"),
        "MAIL_OUTBOX_DIR": str(_tmp / "outbox"),
        "MAIL_BACKEND": "outbox",
        "RATE_LIMIT_ENABLED": "true",
        # Each test client sends its own X-Real-IP, as Caddy sets it for each real client.
        "TRUST_PROXY_HEADERS": "true",
        # Keeps the suite fast; the timing regression test sets a real floor.
        "AUTH_RESPONSE_FLOOR_MS": "0",
    }
)


ALL_RUNTIME_ROLES = "steward_app, steward_worker, steward_deleter, steward_readonly"


def recreate_database(name: str) -> None:
    assert name.endswith("_test"), "only *_test databases may be dropped"
    admin = create_engine(OWNER_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :d AND pid <> pg_backend_pid()"
            ),
            {"d": name},
        )
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        c.execute(text(f'CREATE DATABASE "{name}" OWNER steward_owner'))
        c.execute(text(f'REVOKE ALL ON DATABASE "{name}" FROM PUBLIC'))
        c.execute(text(f'GRANT CONNECT ON DATABASE "{name}" TO {ALL_RUNTIME_ROLES}'))
    admin.dispose()
    owner = create_engine(make_url(OWNER_ADMIN_URL).set(database=name))
    with owner.begin() as c:
        c.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
        c.execute(text(f"GRANT USAGE ON SCHEMA public TO {ALL_RUNTIME_ROLES}"))
    owner.dispose()


def run_migrations(url: str, target: str = "head", downgrade: bool = False) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    cfg.attributes["url"] = url
    if downgrade:
        command.downgrade(cfg, target)
    else:
        command.upgrade(cfg, target)


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    recreate_database(TEST_DB)
    run_migrations(OWNER_TEST_URL)
    from app.core.config import get_settings
    from app.core.db import reset_engine

    get_settings.cache_clear()
    reset_engine()
    yield
    reset_engine()
    shutil.rmtree(_tmp, ignore_errors=True)


@pytest.fixture(scope="session")
def owner_engine(_database: None) -> Iterator[Engine]:
    """Schema-owner connection for test setup/inspection only (the API never uses it)."""
    eng = create_engine(OWNER_TEST_URL)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def role_engines(_database: None) -> Iterator[dict[str, Engine]]:
    """One engine per runtime database role (app, worker, deleter, readonly)."""
    engines = {
        "app": create_engine(APP_URL),
        "worker": create_engine(WORKER_URL),
        "deleter": create_engine(DELETER_URL),
        "readonly": create_engine(READONLY_URL),
    }
    yield engines
    for e in engines.values():
        e.dispose()


@pytest.fixture(autouse=True)
def _reset_rate_limits(owner_engine: Engine) -> None:
    with owner_engine.begin() as c:
        c.execute(text("DELETE FROM rate_limit_buckets"))


@pytest.fixture(scope="session")
def app(_database: None) -> Any:
    from app.main import create_app

    return create_app()


class Api:
    """A browser-like client: own cookie jar, fetches the CSRF token, sends it on writes."""

    def __init__(self, app: Any, ip: str | None = None) -> None:
        from fastapi.testclient import TestClient

        self.ip = ip or f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"
        self.c = TestClient(app, base_url="http://testserver.local", headers={"X-Real-IP": self.ip})
        r = self.c.get("/api/v1/auth/csrf")
        assert r.status_code == 200
        self.csrf = r.json()["csrf_token"]

    def _h(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        h = {"X-CSRF-Token": self.csrf}
        h.update(extra or {})
        return h

    def get(self, path: str, **kw: Any) -> Any:
        return self.c.get("/api/v1" + path, **kw)

    def post(self, path: str, json: Any = None, headers: dict[str, str] | None = None, **kw: Any) -> Any:
        return self.c.post("/api/v1" + path, json=json, headers=self._h(headers), **kw)

    def patch(self, path: str, json: Any = None, headers: dict[str, str] | None = None) -> Any:
        return self.c.patch("/api/v1" + path, json=json, headers=self._h(headers))


def outbox_messages(to: str) -> list[dict[str, str]]:
    out = []
    box = Path(os.environ["MAIL_OUTBOX_DIR"])
    for p in sorted(box.glob("*.eml")) if box.exists() else []:
        m = message_from_bytes(p.read_bytes())
        if m["To"] == to:
            payload = m.get_payload(decode=True)
            body = payload.decode() if isinstance(payload, bytes) else str(m.get_payload())
            out.append({"subject": str(m["Subject"]), "body": body, "file": p.name})
    return out


def latest_token(to: str, path: str) -> str:
    for msg in reversed(outbox_messages(to)):
        m = re.search(re.escape(path) + r"\?token=([A-Za-z0-9_-]+)", msg["body"])
        if m:
            return m.group(1)
    raise AssertionError(f"no {path} link mailed to {to}")


PASSWORD = "correct-horse-42"


def new_email() -> str:
    return f"user-{uuid.uuid4().hex[:10]}@example.com"


@pytest.fixture
def make_user(app: Any) -> Any:
    """Register, verify and sign in a fresh user. Returns a signed-in Api client."""

    def _make(name: str = "Test User", email: str | None = None) -> Api:
        email = email or new_email()
        api = Api(app)
        r = api.post("/auth/register", {"name": name, "email": email, "password": PASSWORD, "accept_terms": True})
        assert r.status_code == 202, r.text
        token = latest_token(email, "/verify-email")
        assert api.post("/auth/verify-email", {"token": token}).status_code == 200
        r = api.post("/auth/login", {"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        api.email = email  # type: ignore[attr-defined]
        api.me = r.json()  # type: ignore[attr-defined]
        return api

    return _make


def create_task(api: Api, prompt: str = "Audit my WordPress website for SEO problems", **kw: Any) -> dict[str, Any]:
    body = {"prompt": prompt, "type": "website", "priority": "normal", "mode": "plan_only", **kw}
    r = api.post("/tasks", body)
    assert r.status_code == 201, r.text
    return dict(r.json())


def upload(api: Api, name: str = "notes.csv", content: bytes = b"a,b\n1,2\n", collection: str = "Research") -> Any:
    return api.c.post(
        "/api/v1/files",
        files={"file": (name, content, "text/csv")},
        data={"collection": collection},
        headers={"X-CSRF-Token": api.csrf},
    )


# ------------------------------------------------------------------ agent engine harness (Phase 3)
class EngineHarness:
    """Runs the real worker code in-process, each worker with its own database role."""

    def __init__(self, settings: Any, worker_factory: Any, deleter_factory: Any) -> None:
        from app.workers.runtime import Worker

        self.settings = settings
        self.worker_factory = worker_factory
        self.orchestrator = Worker("orchestrator", worker_factory, settings)
        self.tools = Worker("tools", worker_factory, settings)
        self.deletion = Worker("deletion", deleter_factory, settings)

    def drain(self, rounds: int = 60) -> int:
        processed = 0
        for _ in range(rounds):
            moved = False
            for w in (self.orchestrator, self.tools, self.deletion):
                while w.run_once():
                    processed += 1
                    moved = True
            if not moved:
                return processed
        raise AssertionError("queue did not settle")


@pytest.fixture
def engine(owner_engine: Engine, role_engines: dict[str, Engine]) -> Iterator[EngineHarness]:
    from sqlalchemy.orm import sessionmaker

    from app.engine.providers import MOCK_SCRIPT, MockProvider, set_provider_override

    with owner_engine.begin() as c:  # jobs left by earlier tests must not run here
        c.execute(text("UPDATE jobs SET status = 'cancelled' WHERE status IN ('pending', 'running')"))
    set_provider_override(MockProvider())
    MOCK_SCRIPT.clear()
    from app.core.config import get_settings

    settings = get_settings().model_copy(
        update={
            "job_backoff_base_seconds": 0.0,
            "job_backoff_max_seconds": 0.0,
            "queue_max_running_per_workspace": 5,
            "egress_allow_private_networks": True,
            "egress_allow_http": True,
            "egress_timeout_seconds": 3.0,
            "model_timeout_seconds": 3.0,
        }
    )
    wf = sessionmaker(bind=role_engines["worker"], expire_on_commit=False, autoflush=False)
    df = sessionmaker(bind=role_engines["deleter"], expire_on_commit=False, autoflush=False)
    yield EngineHarness(settings, wf, df)
    set_provider_override(None)
    MOCK_SCRIPT.clear()


class _Site:
    def __init__(self) -> None:
        self.routes: dict[str, tuple[int, dict[str, str], bytes]] = {}
        self.hits: list[str] = []
        self.url = ""

    def add(self, path: str, body: str | bytes, status: int = 200, headers: dict[str, str] | None = None) -> None:
        data = body.encode() if isinstance(body, str) else body
        self.routes[path] = (status, {"Content-Type": "text/html; charset=utf-8", **(headers or {})}, data)


@pytest.fixture
def site() -> Iterator[_Site]:
    """A tiny local website for egress/web-tool tests (127.0.0.1, random port)."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    s = _Site()

    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            s.hits.append(self.path)
            status, headers, body = s.routes.get(
                self.path.split("?")[0], (404, {"Content-Type": "text/plain"}, b"nope")
            )
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a: Any) -> None:
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    s.url = f"http://127.0.0.1:{srv.server_address[1]}"
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield s
    srv.shutdown()


def set_workspace(owner_engine: Engine, api: Api, **cols: Any) -> None:
    """Set workspace policy columns directly (e.g. an IP allowlist entry the API validator rejects)."""
    import json as _json

    sets = ", ".join(f"{k} = :{k}" for k in cols)
    params = {k: (_json.dumps(v) if isinstance(v, list | dict) else v) for k, v in cols.items()}
    with owner_engine.begin() as c:
        c.execute(text(f"UPDATE workspaces SET {sets} WHERE id = :w"), {**params, "w": api.me["workspace"]["id"]})  # noqa: S608
