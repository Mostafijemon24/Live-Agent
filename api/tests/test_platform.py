"""Rate limits, migrations, API contract, settings, dashboard and misc endpoints."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

import pytest
from conftest import OWNER_ADMIN_URL, PASSWORD, Api, create_task, new_email, recreate_database, run_migrations
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app import schemas as S

# ------------------------------------------------------------------ rate limiting


def test_login_rate_limited_per_email(app: Any, make_user: Any, owner_engine: Any) -> None:
    user = make_user()
    with owner_engine.begin() as c:  # forget make_user's own successful login
        c.execute(text("DELETE FROM rate_limit_buckets"))
    codes = []
    for i in range(12):
        api = Api(app, ip=f"192.0.2.{i + 1}")  # different IPs: the per-email limit applies
        codes.append(api.post("/auth/login", {"email": user.email, "password": "wrong-password-1"}).status_code)
    assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]
    # Even the right password is refused while limited.
    r = Api(app, ip="192.0.2.200").post("/auth/login", {"email": user.email, "password": PASSWORD})
    assert r.status_code == 429 and "retry-after" in r.headers
    assert r.json()["error"]["code"] == "rate_limited"


def test_register_rate_limited_per_ip(app: Any) -> None:
    api = Api(app, ip="198.51.100.7")
    codes = [api.post("/auth/register", {"name": "N", "email": new_email(), "password": PASSWORD, "accept_terms": True}).status_code for _ in range(6)]
    assert codes == [202] * 5 + [429]


def test_forgot_password_rate_limited(app: Any) -> None:
    email = new_email()
    codes = [Api(app).post("/auth/forgot-password", {"email": email}).status_code for _ in range(4)]
    assert codes == [202, 202, 202, 429]


def test_task_creation_rate_limited(make_user: Any) -> None:
    api = make_user()
    codes = [api.post("/tasks", {"prompt": f"Research item number {i} in detail", "type": "research"}).status_code for i in range(31)]
    assert codes[:30] == [201] * 30 and codes[30] == 429


# ------------------------------------------------------------------ migrations


def test_migrations_upgrade_downgrade_upgrade() -> None:
    name = "steward_migrations_test"
    recreate_database(name)
    url = make_url(OWNER_ADMIN_URL).set(database=name).render_as_string(hide_password=False)
    run_migrations(url)
    run_migrations(url, "base", downgrade=True)
    run_migrations(url)
    eng = create_engine(url)
    with eng.connect() as c:
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0002"
        tables = set(c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'")).scalars())
    eng.dispose()
    assert {"users", "workspaces", "tasks", "audit_events", "deletion_requests", "jobs", "usage_counters"} <= tables


def test_models_match_migrations(owner_engine: Any) -> None:
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.core.db import Base

    with owner_engine.connect() as c:
        diff = compare_metadata(MigrationContext.configure(c), Base.metadata)
    assert diff == [], diff


# ------------------------------------------------------------------ API contract


def test_error_envelope_and_request_id(app: Any) -> None:
    api = Api(app)
    r = api.c.get("/api/v1/me", headers={"X-Request-ID": "trace-abc-12345"})
    assert r.status_code == 401
    body = r.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message", "request_id", "details"}
    assert body["error"]["request_id"] == "trace-abc-12345" == r.headers["x-request-id"]
    r = api.get("/does-not-exist")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert len(r.headers["x-request-id"]) >= 8
    for h in ("x-content-type-options", "x-frame-options", "content-security-policy", "cache-control"):
        assert h in r.headers


def test_oversized_request_rejected(app: Any, monkeypatch: Any) -> None:
    api = Api(app)
    r = api.c.post("/api/v1/auth/login", content=b"x" * (31 * 1024 * 1024), headers={"X-CSRF-Token": api.csrf, "Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"


TS_TYPES = Path(__file__).resolve().parents[2] / "web" / "lib" / "api" / "types.ts"


def _ts_fields(name: str) -> set[str]:
    src = TS_TYPES.read_text()
    m = re.search(r"export interface " + name + r"(?: extends (\w+))?\s*\{(.*?)\n\}", src, re.S)
    assert m, name
    fields = set(re.findall(r"^\s{2}(\w+)\??:", m.group(2), re.M))
    if m.group(1):
        fields |= _ts_fields(m.group(1))
    return fields


@pytest.mark.parametrize(
    ("ts", "model"),
    [
        ("User", S.UserOut), ("Me", S.MeOut), ("TaskSummary", S.TaskSummaryOut), ("Task", S.TaskOut), ("TaskStep", S.TaskStepOut),
        ("TaskEvent", S.TaskEventOut), ("Approval", S.ApprovalOut), ("FileItem", S.FileOut), ("Automation", S.AutomationOut),
        ("Integration", S.IntegrationOut), ("ActivityEvent", S.ActivityOut), ("NotificationItem", S.NotificationOut),
        ("Dashboard", S.DashboardOut), ("SecurityStatus", S.SecurityStatusOut), ("Settings", S.SettingsOut), ("Usage", S.UsageOut),
        ("UploadLimits", S.UploadLimitsOut), ("Artifact", S.ArtifactOut), ("AccountRequest", S.AccountRequestOut),
        ("CreateTaskInput", S.CreateTaskIn), ("DecisionInput", S.DecisionIn), ("CreateAutomationInput", S.CreateAutomationIn),
    ],
)
def test_backend_schemas_match_frontend_types(ts: str, model: Any) -> None:
    assert _ts_fields(ts) == set(model.model_fields), f"{ts} differs from {model.__name__}"


def test_openapi_lists_documented_endpoints(app: Any) -> None:
    paths = Api(app).c.get("/api/v1/openapi.json").json()["paths"]
    contract = (Path(__file__).resolve().parents[2] / "API_CONTRACT.md").read_text()
    documented = set(re.findall(r"`(?:GET|POST|PATCH|PUT|DELETE) (/[^`\s]*)`", contract))
    assert documented, "API_CONTRACT.md lists no endpoints"
    for p in documented:
        assert "/api/v1" + p in paths, f"{p} documented but not implemented"
    for p in paths:
        assert p.removeprefix("/api/v1") in documented, f"{p} implemented but not documented"


# ------------------------------------------------------------------ dashboard, settings, misc


def test_dashboard_reflects_real_data(make_user: Any) -> None:
    api = make_user()
    d = api.get("/dashboard").json()
    assert d["counts"] == {"in_progress": 0, "awaiting_approval_plans": 0, "pending_actions": 0, "completed_week": 0, "needs_attention": 0}
    assert d["agent"]["status"] == "not_connected" and d["agent"]["planner"] == "not_configured"
    assert d["setup"] == {"verify_email": True, "privacy": False, "integration": False, "first_task": False}
    assert d["unread_notifications"] == 1  # welcome note
    create_task(api)
    d = api.get("/dashboard").json()
    assert d["counts"]["in_progress"] == 1 and d["setup"]["first_task"] is True and len(d["recent_tasks"]) == 1


def test_settings_preferences_and_validation(make_user: Any) -> None:
    api = make_user()
    s = api.get("/settings").json()
    assert s["enforced"] is False and s["workspace"]["can_edit"] is True and s["workspace"]["privacy_mode"] == "strict"
    r = api.patch("/me/preferences", {"name": "New Name", "timezone": "Asia/Dhaka", "notifications": {"digest": True}})
    assert r.status_code == 200 and r.json()["profile"]["name"] == "New Name" and r.json()["notifications"]["digest"] is True
    assert api.patch("/me/preferences", {"timezone": "Mars/Base"}).status_code == 422
    r = api.patch("/workspace/settings", {"allowed_domains": ["Example.com", "example.com", " docs.example.org "], "ai_rules": {"del": False}})
    assert r.status_code == 200
    assert r.json()["workspace"]["allowed_domains"] == ["example.com", "docs.example.org"]
    assert r.json()["workspace"]["ai_rules"]["del"] is False
    assert api.patch("/workspace/settings", {"allowed_domains": ["not a domain"]}).status_code == 422
    assert api.patch("/workspace/settings", {"privacy_mode": "anything"}).status_code == 422
    assert api.get("/dashboard").json()["setup"]["privacy"] is False
    api.patch("/workspace/settings", {"privacy_mode": "strict"})
    assert api.get("/dashboard").json()["setup"]["privacy"] is True


def test_member_role_cannot_change_workspace_settings(make_user: Any, owner_engine: Any) -> None:
    api = make_user()
    with owner_engine.begin() as c:
        c.execute(text("UPDATE workspace_memberships SET role = 'member' WHERE user_id = :u"), {"u": api.me["user"]["id"]})
    r = api.patch("/workspace/settings", {"name": "Hijacked"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert api.get("/settings").json()["workspace"]["can_edit"] is False


def test_onboarding_saves_preferences(make_user: Any) -> None:
    api = make_user()
    r = api.post("/me/onboarding", {"goals": ["wordpress", "research"], "where": ["workspace_files"],
                                    "ai_rules": {"share": True, "publish": True, "prod": True, "del": True, "folders": False}})
    assert r.status_code == 200 and r.json()["user"]["onboarding_completed"] is True
    assert api.get("/settings").json()["workspace"]["ai_rules"]["folders"] is False
    assert api.post("/me/onboarding", {"goals": ["Bad Label!"], "where": [], "ai_rules": {}}).status_code == 422


def test_automations_scheduled_stay_paused(make_user: Any) -> None:
    api = make_user()
    base = {"template": "SEO report", "tools": ["Agent analysis"], "file_scope": "No files", "approval_policy": "Ask before any change"}
    sched = api.post("/automations", {"name": "Weekly", "trigger": "schedule", "frequency": "weekly", "day": "Monday", "time": "08:00", **base}).json()
    assert sched["enabled"] is False and sched["schedule_text"] == "Every Monday at 08:00" and sched["ref"] == "AU-1"
    r = api.patch(f"/automations/{sched['id']}", {"enabled": True})
    assert r.status_code == 409 and r.json()["error"]["code"] == "scheduler_not_configured"
    manual = api.post("/automations", {"name": "Manual", "trigger": "manual", **base}).json()
    assert manual["enabled"] is True
    run = api.post(f"/automations/{manual['id']}/run")
    assert run.status_code == 201 and run.json()["status"] == "queued"
    assert api.post("/automations", {"name": "Bad", "trigger": "manual", **{**base, "template": "Hack"}}).status_code == 422


def test_integrations_cannot_connect_in_phase2(make_user: Any) -> None:
    api = make_user()
    items = api.get("/integrations").json()
    assert {i["key"] for i in items} == {"wordpress", "notion", "cloud_storage", "email", "browser", "ai_provider"}
    assert all(i["connectable"] is False and i["status"] in ("not_connected", "backend_required") for i in items)
    r = api.post("/integrations/wordpress/connect")
    assert r.status_code == 409 and r.json()["error"]["code"] == "integration_not_available"
    assert api.post("/integrations/unknown/connect").status_code == 404


def test_security_status_is_honest(make_user: Any) -> None:
    api = make_user()
    s = api.get("/security/status").json()
    assert s["privacy_enforced"] is False
    checks = {c["key"]: c["status"] for c in s["checklist"]}
    assert checks["csrf"] == "enforced" and checks["tenant_isolation"] == "enforced" and checks["rate_limits"] == "enforced"
    assert checks["malware_scan"] == "not_configured" and checks["egress"] == "not_configured"
    assert checks["session_cookies"] == "partial"  # no Secure flag outside production


def test_notifications_read_flow(make_user: Any) -> None:
    api = make_user()
    n = api.get("/notifications").json()
    assert n["unread"] == 1 and n["items"][0]["target"]["route"].startswith("/")
    assert api.post(f"/notifications/{n['items'][0]['id']}/read").status_code == 204
    assert api.get("/notifications", params={"unread": "true"}).json()["items"] == []
    assert api.post(f"/notifications/{uuid.uuid4()}/read").status_code == 404
    assert api.post("/notifications/read-all").status_code == 204


def test_account_requests_are_recorded_not_executed(make_user: Any) -> None:
    api = make_user()
    r = api.post("/account/deletion-request", {"reason": "Leaving"})
    assert r.status_code == 201 and r.json()["status"] == "received" and "nothing is deleted" in r.json()["message"]
    assert api.get("/me").status_code == 200  # account still exists
    assert api.post("/account/export-request").status_code == 201


def test_production_config_guards(monkeypatch: Any) -> None:
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError, match="outbox"):
        Settings(env="production", app_origin="https://app.example.com", mail_backend="outbox",
                 database_url="postgresql+psycopg://a:strong@db/x")  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="https"):
        Settings(env="production", app_origin="http://app.example.com", mail_backend="smtp",
                 database_url="postgresql+psycopg://a:strong@db/x")  # type: ignore[arg-type]
    s = Settings(env="production", app_origin="https://app.example.com", mail_backend="smtp", cookie_secure=False,
                 database_url="postgresql+psycopg://a:strong@db/x")  # type: ignore[arg-type]
    assert s.cookie_secure is True
