"""Task CRUD, the state machine, validation, idempotency and pagination."""

from __future__ import annotations

import itertools
from typing import Any

import pytest
from conftest import create_task
from sqlalchemy import text

from app.core.errors import ApiError
from app.domain.enums import TaskStatus
from app.domain.task_states import ACTIONS, TERMINAL, TRANSITIONS, allowed_actions, assert_transition, can_transition


def test_create_task_is_persisted_and_waits_for_planner(make_user: Any, owner_engine: Any) -> None:
    api = make_user()
    t = create_task(api, "Audit my WordPress website for performance and SEO problems, prepare a report.")
    assert t["ref"] == "T-1001"
    assert t["status"] == "queued" and t["waiting_for"] == "planning_service"
    assert t["plan"] is None and t["report"] is None
    assert t["allowed_actions"] == ["cancel"]
    assert t["title"].startswith("Audit my WordPress website")
    # Persisted: reading it back returns the same record.
    again = api.get(f"/tasks/{t['id']}").json()
    assert again["id"] == t["id"] and again["prompt"] == t["prompt"]
    # Timeline explains why nothing is happening.
    events = api.get(f"/tasks/{t['id']}/events").json()["items"]
    assert [e["kind"] for e in events] == ["task.created", "task.waiting"]
    assert "not installed" in events[1]["message"]
    # Background-job contract: recorded in the outbox, never dispatched.
    with owner_engine.connect() as c:
        job = c.execute(text("SELECT kind, status FROM jobs WHERE task_id = :t"), {"t": t["id"]}).one()
    assert tuple(job) == ("task.plan", "pending")
    assert create_task(api)["ref"] == "T-1002"


def test_create_task_validation(make_user: Any) -> None:
    api = make_user()
    cases = [
        ({"prompt": "too short", "type": "research"}, "prompt"),
        ({"prompt": "Run all approved steps right now", "type": "research", "mode": "execute"}, "mode"),
        ({"prompt": "Valid prompt text here", "type": "nonsense"}, "type"),
        ({"prompt": "x" * 4001, "type": "research"}, "prompt"),
        ({"prompt": "Valid prompt text here", "type": "research", "priority": "urgent"}, "priority"),
        ({"type": "research"}, "prompt"),
    ]
    for body, field in cases:
        r = api.post("/tasks", body)
        assert r.status_code == 422, body
        assert any(d["field"] == field for d in r.json()["error"]["details"]), r.json()
    r = api.post(
        "/tasks", {"prompt": "Publish to my website please", "type": "website", "integration_key": "wordpress"}
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "integration_not_connected"


def test_idempotency_key_prevents_duplicates(make_user: Any) -> None:
    api = make_user()
    body = {"prompt": "Summarise competitor pricing pages", "type": "research"}
    r1 = api.post("/tasks", body, headers={"Idempotency-Key": "abc-123-key"})
    r2 = api.post("/tasks", body, headers={"Idempotency-Key": "abc-123-key"})
    assert r1.status_code == 201 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]
    assert api.get("/tasks").json()["total"] == 1


def test_cancel_and_invalid_actions(make_user: Any) -> None:
    api = make_user()
    t = create_task(api)
    r = api.post(f"/tasks/{t['id']}/pause")
    assert r.status_code == 409 and r.json()["error"]["code"] == "action_not_allowed"
    r = api.post(f"/tasks/{t['id']}/cancel", {"reason": "Changed my mind"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled" and r.json()["allowed_actions"] == []
    r = api.post(f"/tasks/{t['id']}/cancel", {})
    assert r.status_code == 409
    msgs = [e["message"] for e in api.get(f"/tasks/{t['id']}/events").json()["items"]]
    assert any("Changed my mind" in m for m in msgs)
    acts = [e["action"] for e in api.get("/activity").json()["items"]]
    assert "task.status_changed" in acts and "task.created" in acts


def test_plan_approval_flow_without_execution_engine(make_user: Any, owner_engine: Any) -> None:
    """Simulates what the Phase 3 planner will write, then checks the API never fakes execution."""
    api = make_user()
    t = create_task(api)
    with owner_engine.begin() as c:
        ws = c.execute(text("SELECT workspace_id FROM tasks WHERE id = :t"), {"t": t["id"]}).scalar_one()
        for i, (title, risk, appr) in enumerate(
            [("Read site", "read_only", False), ("Apply fixes", "production_change", True)], 1
        ):
            c.execute(
                text(
                    "INSERT INTO task_steps (workspace_id, task_id, position, title, tool, risk, requires_approval) VALUES (:w,:t,:p,:ti,'WordPress',:r,:a)"
                ),
                {"w": ws, "t": t["id"], "p": i, "ti": title, "r": risk, "a": appr},
            )
        c.execute(
            text("UPDATE tasks SET status = 'awaiting_approval', waiting_for = NULL WHERE id = :t"), {"t": t["id"]}
        )
    task = api.get(f"/tasks/{t['id']}").json()
    assert set(task["allowed_actions"]) == {"approve_plan", "reject_plan", "revise_plan", "cancel"}
    steps = task["plan"]["steps"]
    assert [s["position"] for s in steps] == [1, 2] and steps[1]["requires_approval"] is True
    # Must pick steps from this plan.
    assert api.post(f"/tasks/{t['id']}/plan/approve", {"selected_step_ids": []}).status_code == 422
    r = api.post(f"/tasks/{t['id']}/plan/approve", {"selected_step_ids": [steps[0]["id"]]})
    assert r.status_code == 200
    out = r.json()
    # Approved, but honestly waiting — not "running" or "completed".
    assert out["status"] == "queued" and out["waiting_for"] == "execution_engine"
    assert [s["state"] for s in out["plan"]["steps"]] == ["not_started", "skipped"]


def test_reject_plan_cancels(make_user: Any, owner_engine: Any) -> None:
    api = make_user()
    t = create_task(api)
    with owner_engine.begin() as c:
        ws = c.execute(text("SELECT workspace_id FROM tasks WHERE id = :t"), {"t": t["id"]}).scalar_one()
        c.execute(
            text(
                "INSERT INTO task_steps (workspace_id, task_id, position, title, tool, risk) VALUES (:w,:t,1,'s','x','read_only')"
            ),
            {"w": ws, "t": t["id"]},
        )
        c.execute(text("UPDATE tasks SET status = 'awaiting_approval' WHERE id = :t"), {"t": t["id"]})
    r = api.post(f"/tasks/{t['id']}/plan/reject", {"note": "Not now"})
    assert r.json()["status"] == "cancelled"


def test_list_filters_sort_and_pagination(make_user: Any) -> None:
    api = make_user()
    for i in range(10):
        create_task(api, f"Research topic number {i:02d} in detail", type="research" if i % 2 else "code")
    page1 = api.get("/tasks", params={"page_size": 4}).json()
    assert page1["total"] == 10 and len(page1["items"]) == 4 and page1["page"] == 1
    page3 = api.get("/tasks", params={"page_size": 4, "page": 3}).json()
    assert len(page3["items"]) == 2
    assert api.get("/tasks", params={"type": "code"}).json()["total"] == 5
    assert api.get("/tasks", params={"q": "number 07"}).json()["total"] == 1
    assert api.get("/tasks", params={"q": "T-1003"}).json()["items"][0]["ref"] == "T-1003"
    assert api.get("/tasks", params={"q": "100%_"}).json()["total"] == 0  # wildcards are escaped
    titles = [t["title"] for t in api.get("/tasks", params={"sort": "title", "page_size": 100}).json()["items"]]
    assert titles == sorted(titles)
    assert api.get("/tasks", params={"status": "queued"}).json()["total"] == 10
    assert api.get("/tasks", params={"created": "3d"}).json()["total"] == 10
    assert api.get("/tasks", params={"integration": "none"}).json()["total"] == 10
    assert api.get("/tasks", params={"status": "bogus"}).status_code == 422
    assert api.get("/tasks", params={"page_size": 1000}).status_code == 422


def test_message_kinds(make_user: Any) -> None:
    api = make_user()
    t = create_task(api)
    r = api.post(f"/tasks/{t['id']}/messages", {"text": "Which pages first?", "kind": "question"})
    assert r.status_code == 200
    assert api.post(f"/tasks/{t['id']}/messages", {"text": "Answer", "kind": "answer"}).status_code == 409
    assert api.post(f"/tasks/{t['id']}/messages", {"text": "", "kind": "question"}).status_code == 422


# ------------------------------------------------------------------ state machine (pure)
def test_every_status_has_transitions_and_actions() -> None:
    assert set(TRANSITIONS) == set(TaskStatus) == set(ACTIONS)
    for s in TERMINAL:
        assert TRANSITIONS[s] == frozenset() and ACTIONS[s] == ()


@pytest.mark.parametrize(("src", "dst"), list(itertools.product(TaskStatus, TaskStatus)))
def test_transition_matrix(src: TaskStatus, dst: TaskStatus) -> None:
    if can_transition(src, dst):
        assert_transition(src, dst)
    else:
        with pytest.raises(ApiError) as e:
            assert_transition(src, dst)
        assert e.value.code == "invalid_state_transition"


def test_no_path_to_completed_without_running() -> None:
    """A task can only become completed from running — never straight from queued/planning."""
    for src, dsts in TRANSITIONS.items():
        if TaskStatus.completed in dsts:
            assert src == TaskStatus.running


def test_plan_actions_hidden_without_plan() -> None:
    assert allowed_actions(TaskStatus.awaiting_approval, has_plan=False) == ["cancel"]
    assert "approve_plan" in allowed_actions(TaskStatus.awaiting_approval, has_plan=True)
