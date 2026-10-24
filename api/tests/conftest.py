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
        c.execute(text(f'GRANT CONNECT ON DATABASE "{name}" TO steward_app'))
    admin.dispose()
    owner = create_engine(make_url(OWNER_ADMIN_URL).set(database=name))
    with owner.begin() as c:
        c.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
        c.execute(text("GRANT USAGE ON SCHEMA public TO steward_app"))
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
