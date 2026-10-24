"""Cross-tenant isolation: user B must never read or change user A's data by guessing IDs."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from conftest import create_task, upload
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def two_tenants(make_user: Any, owner_engine: Any) -> dict[str, Any]:
    a = make_user("Alice A")
    b = make_user("Bob B")
    task = create_task(a, "Audit Alice's WordPress website for SEO problems")
    f = upload(a, "alice-secret.csv", b"name,salary\nalice,100\n").json()
    appr = a.post(f"/files/{f['id']}/deletion-request", {"reason": "No longer needed"}).json()
    auto = a.post(
        "/automations",
        {
            "name": "Alice weekly",
            "trigger": "manual",
            "template": "SEO report",
            "tools": [],
            "file_scope": "No files",
            "approval_policy": "Ask before any change",
        },
    ).json()
    notes = a.get("/notifications").json()["items"]
    # Give Alice a report + artifact so the Reports view has something to leak.
    with owner_engine.begin() as c:
        c.execute(
            text(
                'UPDATE tasks SET report = \'{"summary":"secret","open_issues":"x","next_step":"y"}\'::jsonb WHERE id = :t'
            ),
            {"t": task["id"]},
        )
        ws = c.execute(text("SELECT workspace_id FROM tasks WHERE id = :t"), {"t": task["id"]}).scalar_one()
        c.execute(
            text(
                "INSERT INTO artifacts (workspace_id, task_id, name, kind, provenance) VALUES (:w, :t, 'alice-report.pdf', 'Report', 'ai_generated')"
            ),
            {"w": ws, "t": task["id"]},
        )
    return {
        "a": a,
        "b": b,
        "task": task,
        "file": f,
        "approval": appr,
        "automation": auto,
        "notification": notes[0],
        "ws_a": ws,
    }


def _is_not_found(r: Any) -> None:
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "not_found"


def test_tasks_are_isolated(two_tenants: dict[str, Any]) -> None:
    b, tid = two_tenants["b"], two_tenants["task"]["id"]
    _is_not_found(b.get(f"/tasks/{tid}"))
    _is_not_found(b.get(f"/tasks/{tid}/events"))
    _is_not_found(b.post(f"/tasks/{tid}/cancel", {}))
    _is_not_found(b.post(f"/tasks/{tid}/pause"))
    _is_not_found(b.post(f"/tasks/{tid}/messages", {"text": "hi", "kind": "question"}))
    _is_not_found(b.post(f"/tasks/{tid}/plan/approve", {"selected_step_ids": [str(uuid.uuid4())]}))
    assert all(t["id"] != tid for t in b.get("/tasks").json()["items"])
    assert b.get("/tasks", params={"q": "Alice"}).json()["total"] == 0
    # Alice's task is untouched.
    assert two_tenants["a"].get(f"/tasks/{tid}").json()["status"] == "queued"


def test_files_are_isolated(two_tenants: dict[str, Any]) -> None:
    b, fid = two_tenants["b"], two_tenants["file"]["id"]
    _is_not_found(b.get(f"/files/{fid}"))
    _is_not_found(b.get(f"/files/{fid}/download"))
    _is_not_found(b.patch(f"/files/{fid}", {"classification": "public"}))
    _is_not_found(b.post(f"/files/{fid}/deletion-request", {"reason": "steal"}))
    assert b.get("/files").json()["total"] == 0
    # Cannot attach someone else's file to your own task.
    r = b.post(
        "/tasks",
        {"prompt": "Summarise the attached spreadsheet", "type": "file_analysis", "attachment_file_ids": [fid]},
    )
    _is_not_found(r)
    assert two_tenants["a"].get(f"/files/{fid}").json()["classification"] == "unknown"


def test_approvals_are_isolated(two_tenants: dict[str, Any]) -> None:
    b, aid = two_tenants["b"], two_tenants["approval"]["id"]
    _is_not_found(b.get(f"/approvals/{aid}"))
    _is_not_found(b.post(f"/approvals/{aid}/decision", {"decision": "reject"}))
    lst = b.get("/approvals", params={"status": "all"}).json()
    assert lst["total"] == 0 and lst["pending_count"] == 0
    assert two_tenants["a"].get(f"/approvals/{aid}").json()["status"] == "pending"


def test_reports_are_isolated(two_tenants: dict[str, Any]) -> None:
    b, a = two_tenants["b"], two_tenants["a"]
    rb = b.get("/reports").json()
    assert rb == {"artifacts": [], "reports": []}
    ra = a.get("/reports").json()
    assert len(ra["artifacts"]) == 1 and len(ra["reports"]) == 1


def test_integrations_are_isolated(two_tenants: dict[str, Any], owner_engine: Any) -> None:
    a, b = two_tenants["a"], two_tenants["b"]
    with owner_engine.begin() as c:
        c.execute(
            text("INSERT INTO integrations (workspace_id, key, status) VALUES (:w, 'notion', 'connected')"),
            {"w": two_tenants["ws_a"]},
        )
    status = {i["key"]: i["status"] for i in a.get("/integrations").json()}
    assert status["notion"] == "connected"
    status_b = {i["key"]: i["status"] for i in b.get("/integrations").json()}
    assert status_b["notion"] == "not_connected"
    # B cannot disconnect A's integration (B's own is not connected).
    r = b.post("/integrations/notion/disconnect")
    assert r.status_code == 409
    assert {i["key"]: i["status"] for i in a.get("/integrations").json()}["notion"] == "connected"


def test_activity_and_audit_are_isolated(two_tenants: dict[str, Any]) -> None:
    a, b = two_tenants["a"], two_tenants["b"]
    a_ids = {e["id"] for e in a.get("/activity", params={"page_size": 100}).json()["items"]}
    b_items = b.get("/activity", params={"page_size": 100}).json()["items"]
    assert a_ids and not (a_ids & {e["id"] for e in b_items})
    assert all("Alice" not in e["message"] for e in b_items)


def test_notifications_and_automations_are_isolated(two_tenants: dict[str, Any]) -> None:
    b = two_tenants["b"]
    _is_not_found(b.post(f"/notifications/{two_tenants['notification']['id']}/read"))
    auto_id = two_tenants["automation"]["id"]
    _is_not_found(b.patch(f"/automations/{auto_id}", {"enabled": False}))
    _is_not_found(b.post(f"/automations/{auto_id}/run"))
    assert b.get("/automations").json() == []


def test_denied_access_is_audited_for_the_requester(two_tenants: dict[str, Any]) -> None:
    b = two_tenants["b"]
    b.get(f"/tasks/{two_tenants['task']['id']}")
    events = b.get("/activity", params={"type": "security"}).json()["items"]
    assert any(e["action"] == "authz.denied" for e in events)
    # The denial is not written into the victim's workspace log.
    a_events = two_tenants["a"].get("/activity", params={"type": "security"}).json()["items"]
    assert not any(e["action"] == "authz.denied" for e in a_events)


def test_malformed_ids_and_client_supplied_workspace_are_ignored(two_tenants: dict[str, Any]) -> None:
    b = two_tenants["b"]
    _is_not_found(b.get("/tasks/not-a-uuid"))
    # A workspace_id in the body is rejected (unknown field), never trusted.
    r = b.post(
        "/tasks", {"prompt": "Do something useful please", "type": "custom", "workspace_id": str(two_tenants["ws_a"])}
    )
    assert r.status_code == 422
    # Query parameters cannot widen scope either.
    assert b.get("/tasks", params={"workspace_id": str(two_tenants["ws_a"])}).json()["total"] == 0


def test_database_rejects_cross_tenant_child_rows(two_tenants: dict[str, Any], owner_engine: Any) -> None:
    """Composite foreign keys: a child row cannot point at another workspace's parent."""
    b_ws = two_tenants["b"].me["workspace"]["id"]
    with pytest.raises(IntegrityError), owner_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO task_events (workspace_id, task_id, level, kind, message) VALUES (:w, :t, 'info', 'x', 'x')"
            ),
            {"w": b_ws, "t": two_tenants["task"]["id"]},
        )
