"""Approval decision rules, append-only records, audit logging and database privileges."""

from __future__ import annotations

from typing import Any

import pytest
from conftest import APP_URL, upload
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.services.audit import scrub


@pytest.fixture
def deletion_approval(make_user: Any) -> tuple[Any, dict[str, Any]]:
    api = make_user()
    f = upload(api, "media.csv").json()
    appr = api.post(f"/files/{f['id']}/deletion-request", {"reason": "cleanup"}).json()
    return api, appr


def test_approve_requires_acknowledgement_and_exact_items(deletion_approval: Any) -> None:
    api, a = deletion_approval
    r = api.post(f"/approvals/{a['id']}/decision", {"decision": "approve"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "acknowledgement_required"
    r = api.post(
        f"/approvals/{a['id']}/decision",
        {"decision": "approve", "acknowledged": True, "confirmed_items": ["other.csv"]},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "confirmation_mismatch"
    r = api.post(f"/approvals/{a['id']}/decision", {"decision": "approve", "acknowledged": True})
    assert r.status_code == 422
    assert api.get(f"/approvals/{a['id']}").json()["status"] == "pending"


def test_request_changes_needs_note_and_decisions_are_final(deletion_approval: Any) -> None:
    api, a = deletion_approval
    assert api.post(f"/approvals/{a['id']}/decision", {"decision": "request_changes"}).status_code == 422
    r = api.post(f"/approvals/{a['id']}/decision", {"decision": "request_changes", "note": "Keep the logo"})
    assert (
        r.status_code == 200
        and r.json()["status"] == "changes_requested"
        and r.json()["decision_note"] == "Keep the logo"
    )
    r = api.post(
        f"/approvals/{a['id']}/decision",
        {"decision": "approve", "acknowledged": True, "confirmed_items": ["media.csv"]},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "approval_already_decided"
    lst = api.get("/approvals", params={"status": "decided"}).json()
    assert lst["total"] == 1 and lst["pending_count"] == 0


def test_expired_approval_cannot_be_approved(deletion_approval: Any, owner_engine: Any) -> None:
    api, a = deletion_approval
    with owner_engine.begin() as c:
        c.execute(
            text("UPDATE approval_requests SET expires_at = now() - interval '1 minute' WHERE id = :i"), {"i": a["id"]}
        )
    r = api.post(f"/approvals/{a['id']}/decision", {"decision": "reject"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "approval_expired"
    assert api.get(f"/approvals/{a['id']}").json()["status"] == "expired"


def test_tampered_approval_payload_is_refused(deletion_approval: Any, owner_engine: Any) -> None:
    api, a = deletion_approval
    with owner_engine.begin() as c:
        c.execute(
            text("UPDATE approval_requests SET affected_items = '[\"everything\"]'::jsonb WHERE id = :i"),
            {"i": a["id"]},
        )
    r = api.post(
        f"/approvals/{a['id']}/decision",
        {"decision": "approve", "acknowledged": True, "confirmed_items": ["everything"]},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "approval_payload_changed"


def test_decision_is_recorded_and_audited(deletion_approval: Any, owner_engine: Any) -> None:
    api, a = deletion_approval
    api.post(f"/approvals/{a['id']}/decision", {"decision": "reject", "note": "No"})
    with owner_engine.connect() as c:
        rows = c.execute(
            text("SELECT decision, note, decided_by FROM approval_decisions WHERE approval_id = :i"), {"i": a["id"]}
        ).all()
    assert len(rows) == 1 and rows[0].decision == "reject" and str(rows[0].decided_by) == api.me["user"]["id"]
    actions = [e["action"] for e in api.get("/activity", params={"type": "approval"}).json()["items"]]
    assert "approval.requested" in actions and "approval.reject" in actions


def test_security_events_are_audited(make_user: Any, app: Any) -> None:
    from conftest import Api

    api = make_user()
    Api(app).post("/auth/login", {"email": api.email, "password": "wrong-password-1"})
    api.patch("/workspace/settings", {"privacy_mode": "approval"})
    actions = [e["action"] for e in api.get("/activity", params={"page_size": 100}).json()["items"]]
    for expected in (
        "auth.registered",
        "auth.email_verified",
        "auth.login",
        "auth.login_failed",
        "privacy.mode_changed",
    ):
        assert expected in actions, expected


def test_audit_metadata_is_scrubbed() -> None:
    out = scrub(
        {"password": "x", "nested": {"api_key": "k", "Session-Token": "t", "ok": "fine"}, "list": [{"csrf": "c"}]}
    )
    assert out == {
        "password": "[REDACTED]",
        "nested": {"api_key": "[REDACTED]", "Session-Token": "[REDACTED]", "ok": "fine"},
        "list": [{"csrf": "[REDACTED]"}],
    }


# ------------------------------------------------------------------ database privileges
@pytest.fixture
def app_engine(_database: None) -> Any:
    eng = create_engine(APP_URL)
    yield eng
    eng.dispose()


@pytest.mark.parametrize(
    "table", ["tasks", "files", "users", "approval_requests", "deletion_requests", "workspaces", "sessions"]
)
def test_app_role_cannot_delete(app_engine: Any, table: str, make_user: Any) -> None:
    make_user()
    with pytest.raises(ProgrammingError, match="permission denied"), app_engine.begin() as c:
        c.execute(text(f"DELETE FROM {table}"))  # noqa: S608 - fixed table names


@pytest.mark.parametrize(
    "stmt", ["TRUNCATE tasks", "DROP TABLE tasks", "CREATE TABLE x (id int)", "ALTER TABLE tasks ADD COLUMN x int"]
)
def test_app_role_cannot_run_ddl_or_truncate(app_engine: Any, stmt: str) -> None:
    with pytest.raises(ProgrammingError), app_engine.begin() as c:
        c.execute(text(stmt))


@pytest.mark.parametrize("table", ["audit_events", "approval_decisions", "task_events"])
def test_append_only_tables_for_app_role(app_engine: Any, table: str, make_user: Any) -> None:
    make_user()
    with pytest.raises(ProgrammingError, match="permission denied"), app_engine.begin() as c:
        c.execute(text(f"UPDATE {table} SET id = id"))  # noqa: S608 - fixed table names


def test_audit_log_append_only_even_for_owner(owner_engine: Any, make_user: Any) -> None:
    make_user()
    with pytest.raises(DBAPIError, match="append-only"), owner_engine.begin() as c:
        c.execute(text("UPDATE audit_events SET message = 'tampered'"))
    with pytest.raises(DBAPIError, match="append-only"), owner_engine.begin() as c:
        c.execute(text("DELETE FROM audit_events"))
    with pytest.raises(DBAPIError, match="append-only"), owner_engine.begin() as c:
        c.execute(text("TRUNCATE audit_events"))
