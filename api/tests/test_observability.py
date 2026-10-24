"""Liveness, readiness and metrics (Phase 4)."""

from __future__ import annotations

from typing import Any

from pydantic import SecretStr

from tests.conftest import Api, create_task


def test_liveness_and_readiness(app: Any, monkeypatch: Any) -> None:
    c = Api(app).c
    assert c.get("/livez").json() == {"status": "ok"}
    r = c.get("/readyz")
    assert r.status_code == 200 and r.json()["checks"] == {"database": "ok", "migrations": "ok", "storage": "ok"}
    assert c.get("/healthz").status_code == 200
    from app.core import observability

    monkeypatch.setattr(observability, "migration_head", lambda: "9999")
    r = c.get("/readyz")
    assert r.status_code == 503 and r.json()["checks"]["migrations"] == "pending"


def test_metrics_are_token_protected_and_aggregate_only(app: Any, make_user: Any, monkeypatch: Any) -> None:
    from app.core.config import get_settings

    api = make_user()
    t = create_task(api)
    api.get(f"/tasks/{t['id']}")
    c = Api(app).c
    assert c.get("/metrics").status_code == 404  # disabled without a token
    monkeypatch.setattr(get_settings(), "metrics_token", SecretStr("m-token-0123456789"))
    assert c.get("/metrics").status_code == 404
    assert c.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 404
    r = c.get("/metrics", headers={"Authorization": "Bearer m-token-0123456789"})
    assert r.status_code == 200
    body = r.text
    assert 'route="/tasks/{task_id}"' in body  # templates, never raw IDs
    assert t["id"] not in body and api.email not in body and api.me["workspace"]["id"] not in body
    for name in ("steward_http_requests_total", "steward_jobs{", "steward_tasks{", "steward_db_pool_checked_out"):
        assert name in body, name


def test_database_pool_exhaustion_returns_503_quickly(make_user: Any, monkeypatch: Any) -> None:
    from sqlalchemy.exc import TimeoutError as SATimeoutError

    from app.services import tasks as T

    api = make_user()

    def exhausted(*_a: Any, **_k: Any) -> None:
        raise SATimeoutError("QueuePool limit reached")

    monkeypatch.setattr(T, "list_tasks", exhausted)
    r = api.get("/tasks")
    assert r.status_code == 503 and r.headers["retry-after"] == "2"
    assert r.json()["error"]["code"] == "service_busy" and "QueuePool" not in r.text
