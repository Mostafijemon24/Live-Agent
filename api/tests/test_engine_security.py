"""Privacy, policy and approval-binding guarantees of the agent engine, exercised through the
real API and the real workers. Model output is treated as untrusted input throughout."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import text

from app.domain.enums import DataClass
from app.engine.policy import evaluate_model_transfer
from app.engine.providers import (
    MOCK_SCRIPT,
    MockProvider,
    ModelRequest,
    ModelResponse,
    ProviderInfo,
    set_provider_override,
)
from app.engine.tools.base import PlanEnv, ProviderView
from tests.conftest import create_task, set_workspace, upload

PAGE = "<html><head><title>A page with a reasonable title</title></head><body><h1>Hi</h1></body></html>"


class FakeExternalProvider:
    """Stands in for a third-party AI API; records exactly what would have been sent."""

    def __init__(self) -> None:
        self.calls: list[ModelRequest] = []
        self.info = ProviderInfo(
            key="openai_compatible",
            label="Example AI (external)",
            model="ext-model-1",
            location="external",
            configured=True,
            data_disclosure="Task text you approve is sent to Example AI.",
        )
        self._mock = MockProvider()

    def generate(self, req: ModelRequest, *, timeout: float) -> ModelResponse:
        self.calls.append(req)
        return self._mock.generate(req, timeout=timeout)


def _approve_all(api: Any, task: dict[str, Any]) -> dict[str, Any]:
    ids = [s["id"] for s in task["plan"]["steps"] if s["state"] != "blocked"]
    r = api.post(f"/tasks/{task['id']}/plan/approve", {"selected_step_ids": ids})
    assert r.status_code == 200, r.text
    return dict(r.json())


def _pending(api: Any, task_id: str) -> list[dict[str, Any]]:
    return [a for a in api.get("/approvals", params={"status": "pending"}).json()["items"] if a["task_id"] == task_id]


def _decide(api: Any, a: dict[str, Any], decision: str = "approve") -> Any:
    body: dict[str, Any] = {"decision": decision, "acknowledged": True}
    if decision == "request_changes":
        body["note"] = "change"
    return api.post(f"/approvals/{a['id']}/decision", body)


# ---------------------------------------------------------------- privacy modes & egress
def test_strict_mode_asks_before_contacting_a_site(make_user: Any, engine: Any, site: Any, owner_engine: Any) -> None:
    site.add("/", PAGE)
    api = make_user()
    set_workspace(owner_engine, api, allowed_domains=["127.0.0.1"], privacy_mode="strict")
    t = create_task(api, f"Inspect {site.url}/ and write a report.")
    engine.drain()
    t = api.get(f"/tasks/{t['id']}").json()
    first = t["plan"]["steps"][0]
    assert first["tool_id"] == "web.inspect" and first["policy"]["outcome"] == "require_approval"
    assert first["requires_approval"] is True
    _approve_all(api, t)
    engine.drain()
    t = api.get(f"/tasks/{t['id']}").json()
    assert t["status"] == "needs_input" and t["waiting_for"] == "approval"
    assert site.hits == []  # nothing was contacted before the one-time approval
    (a,) = _pending(api, t["id"])
    assert a["operation"] == "web.inspect" and a["targets"] == ["127.0.0.1"] and a["category"] == "external_transfer"
    assert a["step_id"] == first["id"] and a["policy_version"]
    assert _decide(api, a).json()["execution_state"] == "pending_execution"
    engine.drain()
    t = api.get(f"/tasks/{t['id']}").json()
    assert t["status"] == "completed" and site.hits == ["/"]
    a = api.get(f"/approvals/{a['id']}").json()
    assert a["execution_state"] == "executed"


def test_external_model_needs_approval_before_any_data_is_sent(make_user: Any, engine: Any, owner_engine: Any) -> None:
    fake = FakeExternalProvider()
    set_provider_override(fake)
    api = make_user()
    set_workspace(owner_engine, api, tool_permissions={"wp_read": True, "browser": True, "external": True})
    t = create_task(api, "Write a short report about our launch plan. api_key=sk-test-abcdefghijklmnop1234")
    engine.drain()
    t = api.get(f"/tasks/{t['id']}").json()
    assert t["status"] == "queued" and t["waiting_for"] == "approval"
    assert fake.calls == []  # nothing left the server
    (a,) = _pending(api, t["id"])
    assert a["operation"] == "model.plan" and a["data_leaves_workspace"] is True
    assert a["destination"].startswith("Example AI")
    # Declining cancels the task; still nothing sent.
    _decide(api, a, "reject")
    engine.drain()
    assert api.get(f"/tasks/{t['id']}").json()["status"] == "cancelled" and fake.calls == []

    t2 = create_task(api, "Write a short report about our launch plan. api_key=sk-test-abcdefghijklmnop1234")
    engine.drain()
    (a2,) = _pending(api, t2["id"])
    _decide(api, a2)
    engine.drain()
    t2 = api.get(f"/tasks/{t2['id']}").json()
    assert t2["status"] == "awaiting_approval", (t2["error_message"], api.get(f"/tasks/{t2['id']}/events").json())
    assert len(fake.calls) == 1
    sent = "\n".join(m.content for m in fake.calls[0].messages)
    assert "sk-test-abcdefghijklmnop1234" not in sent and "[REDACTED]" in sent  # secrets redacted first
    assert api.get(f"/approvals/{a2['id']}").json()["execution_state"] == "executed"  # used once
    with owner_engine.connect() as c:
        rows = c.execute(
            text("SELECT location, outcome, redactions FROM model_calls WHERE task_id = :t"), {"t": t2["id"]}
        ).all()
    assert [(r.location, r.outcome) for r in rows] == [("external", "ok")] and rows[0].redactions >= 1


def test_external_transfer_denied_when_switched_off(make_user: Any, engine: Any, owner_engine: Any) -> None:
    fake = FakeExternalProvider()
    set_provider_override(fake)
    api = make_user()  # default tool permissions: external = false
    t = create_task(api, "Summarise our internal roadmap for the board.")
    engine.drain()
    t = api.get(f"/tasks/{t['id']}").json()
    assert t["status"] == "failed" and "turned off" in (t["error_message"] or "")
    assert fake.calls == [] and _pending(api, t["id"]) == []
    acts = api.get("/activity", params={"type": "security"}).json()["items"]
    assert any(x["action"] == "policy.blocked" for x in acts)


def _env(**kw: Any) -> PlanEnv:
    base: dict[str, Any] = {
        "workspace_id": uuid.uuid4(),
        "task_classification": "confidential",
        "attached_files": {},
        "allowed_domains": [],
        "privacy_mode": "custom",
        "tool_permissions": {"external": True},
        "ai_rules": {"share": False},
        "provider": ProviderView(True, "external", "X"),
        "wordpress_site": None,
    }
    base.update(kw)
    return PlanEnv(**base)


@pytest.mark.parametrize(
    ("cls", "mode", "share", "outcome"),
    [
        (DataClass.unknown, "custom", False, "deny"),
        (DataClass.confidential, "custom", False, "require_approval"),
        (DataClass.internal, "strict", False, "require_approval"),
        (DataClass.internal, "approval", False, "require_approval"),
        (DataClass.internal, "custom", True, "require_approval"),  # AI rule tightens custom mode
        (DataClass.public, "custom", False, "allow"),
        (DataClass.internal, "custom", False, "allow"),
    ],
)
def test_model_transfer_policy_matrix(cls: DataClass, mode: str, share: bool, outcome: str) -> None:
    d = evaluate_model_transfer(_env(privacy_mode=mode, ai_rules={"share": share}), cls, "data")
    assert d.outcome == outcome, d.reasons


def test_local_model_keeps_data_on_your_servers() -> None:
    d = evaluate_model_transfer(_env(provider=ProviderView(True, "local", "Ollama")), DataClass.unknown, "data")
    assert d.outcome == "allow" and d.data_leaves is False


def test_domain_not_on_allowlist_is_blocked_and_never_contacted(
    make_user: Any, engine: Any, site: Any, owner_engine: Any
) -> None:
    site.add("/", PAGE)
    api = make_user()
    set_workspace(owner_engine, api, allowed_domains=["example.com"], privacy_mode="approval")
    t = create_task(api, f"Inspect {site.url}/ and write a report.")
    engine.drain()
    t = api.get(f"/tasks/{t['id']}").json()
    blocked = t["plan"]["steps"][0]
    assert blocked["state"] == "blocked" and blocked["policy"]["outcome"] == "deny"
    assert "allowed domains" in blocked["error"]
    # A blocked step can't be selected for execution.
    r = api.post(f"/tasks/{t['id']}/plan/approve", {"selected_step_ids": [blocked["id"]]})
    assert r.status_code == 422
    _approve_all(api, t)
    engine.drain()
    assert site.hits == []


def test_policy_is_rechecked_right_before_execution(make_user: Any, engine: Any, site: Any, owner_engine: Any) -> None:
    site.add("/", PAGE)
    api = make_user()
    set_workspace(owner_engine, api, allowed_domains=["127.0.0.1"], privacy_mode="approval")
    t = create_task(api, f"Inspect {site.url}/ and write a report.")
    engine.drain()
    t = api.get(f"/tasks/{t['id']}").json()
    assert t["plan"]["steps"][0]["policy"]["outcome"] == "allow"
    _approve_all(api, t)
    # The admin tightens the allowlist after approving the plan.
    api.patch("/workspace/settings", {"allowed_domains": ["example.com"]})
    engine.drain()
    t = api.get(f"/tasks/{t['id']}").json()
    assert t["plan"]["steps"][0]["state"] == "blocked" and site.hits == []
    assert t["status"] == "partially_completed"


def test_tool_switched_off_in_settings_is_blocked(make_user: Any, engine: Any, site: Any, owner_engine: Any) -> None:
    api = make_user()
    set_workspace(owner_engine, api, allowed_domains=["127.0.0.1"], privacy_mode="approval")
    api.patch("/workspace/settings", {"tool_permissions": {"browser": False}})
    t = create_task(api, f"Inspect {site.url}/ and write a report.")
    engine.drain()
    step = api.get(f"/tasks/{t['id']}").json()["plan"]["steps"]
    # The planner only offers enabled tools; the policy blocks it even if a model insists.
    assert all(s["tool_id"] != "web.inspect" or s["state"] == "blocked" for s in step)


# ---------------------------------------------------------------- approval binding
def _strict_step_approval(api: Any, engine: Any, site: Any, owner_engine: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    site.add("/", PAGE)
    site.add("/admin", PAGE)
    set_workspace(owner_engine, api, allowed_domains=["127.0.0.1"], privacy_mode="strict")
    t = create_task(api, f"Inspect {site.url}/ and write a report.")
    engine.drain()
    t = api.get(f"/tasks/{t['id']}").json()
    _approve_all(api, t)
    engine.drain()
    (a,) = _pending(api, t["id"])
    return t, a


def test_changed_arguments_after_approval_never_run(make_user: Any, engine: Any, site: Any, owner_engine: Any) -> None:
    api = make_user()
    t, a = _strict_step_approval(api, engine, site, owner_engine)
    _decide(api, a)
    with owner_engine.begin() as c:  # someone edits the stored step after approval
        c.execute(
            text("UPDATE task_steps SET args = :a WHERE id = :s"),
            {"a": json.dumps({"url": f"{site.url}/admin"}), "s": t["plan"]["steps"][0]["id"]},
        )
    engine.drain()
    step = api.get(f"/tasks/{t['id']}").json()["plan"]["steps"][0]
    assert step["state"] == "blocked" and "changed" in step["error"]
    assert site.hits == []


def test_rehashed_arguments_do_not_match_the_approval(
    make_user: Any, engine: Any, site: Any, owner_engine: Any
) -> None:
    from app.engine.canonical import args_hash

    api = make_user()
    t, a = _strict_step_approval(api, engine, site, owner_engine)
    _decide(api, a)
    new_args = {"url": f"{site.url}/admin"}
    with owner_engine.begin() as c:  # attacker keeps the step self-consistent, but the approval was for "/"
        c.execute(
            text("UPDATE task_steps SET args = :a, args_hash = :h WHERE id = :s"),
            {"a": json.dumps(new_args), "h": args_hash("web.inspect", new_args), "s": t["plan"]["steps"][0]["id"]},
        )
    engine.drain()
    t2 = api.get(f"/tasks/{t['id']}").json()
    assert site.hits == []  # never ran with the changed arguments
    assert api.get(f"/approvals/{a['id']}").json()["execution_state"] == "invalidated"
    (fresh,) = _pending(api, t["id"])  # a new approval shows the new target
    assert fresh["id"] != a["id"] and any("/admin" in x for x in fresh["affected_items"])
    assert t2["status"] == "needs_input"
    # Approving the new, visible target lets the step run — exactly once, with what was approved.
    _decide(api, fresh)
    engine.drain()
    assert site.hits == ["/admin"]
    assert api.get(f"/tasks/{t['id']}").json()["status"] == "completed"


@pytest.mark.parametrize("tamper", ["expired", "demoted", "policy_version"])
def test_stale_or_unauthorised_approvals_are_refused(
    make_user: Any, engine: Any, site: Any, owner_engine: Any, tamper: str
) -> None:
    api = make_user()
    _t, a = _strict_step_approval(api, engine, site, owner_engine)
    _decide(api, a)
    with owner_engine.begin() as c:
        if tamper == "expired":
            c.execute(
                text("UPDATE approval_requests SET expires_at = now() - interval '1 minute' WHERE id = :a"),
                {"a": a["id"]},
            )
        elif tamper == "demoted":
            c.execute(
                text("UPDATE workspace_memberships SET role = 'member' WHERE user_id = :u"), {"u": api.me["user"]["id"]}
            )
        else:
            c.execute(text("UPDATE approval_requests SET policy_version = 'old' WHERE id = :a"), {"a": a["id"]})
    engine.drain()
    assert site.hits == []
    assert api.get(f"/approvals/{a['id']}").json()["execution_state"] == "invalidated"


def test_duplicate_tool_job_runs_the_step_once(make_user: Any, engine: Any, site: Any, owner_engine: Any) -> None:
    from sqlalchemy.orm import Session

    from app.domain.enums import JobQueue
    from app.engine import queue as Q

    api = make_user()
    t, a = _strict_step_approval(api, engine, site, owner_engine)
    _decide(api, a)
    engine.drain()
    assert site.hits == ["/"]
    step_id = uuid.UUID(t["plan"]["steps"][0]["id"])
    with Session(owner_engine) as db:  # replay the same tool job
        Q.enqueue(
            db,
            workspace_id=uuid.UUID(api.me["workspace"]["id"]),
            kind="tool.run",
            queue=JobQueue.tools,
            task_id=uuid.UUID(t["id"]),
            step_id=step_id,
            settings=engine.settings,
        )
        db.commit()
    engine.drain()
    assert site.hits == ["/"]


def test_approval_cannot_be_used_in_another_workspace(make_user: Any, owner_engine: Any) -> None:
    from sqlalchemy.orm import Session

    from app.engine.policy import POLICY_VERSION
    from app.models import ApprovalRequest
    from app.services.approvals import verify_binding

    a_user, b_user = make_user(), make_user()
    f = upload(a_user, "x.csv").json()
    appr = a_user.post(f"/files/{f['id']}/deletion-request", {"reason": "cleanup"}).json()
    with Session(owner_engine) as db:
        row = db.get(ApprovalRequest, uuid.UUID(appr["id"]))
        assert row is not None
        reason = verify_binding(
            db,
            row,
            workspace_id=uuid.UUID(b_user.me["workspace"]["id"]),
            operation="deletion.execute",
            args_hash=row.args_hash,
            targets=list(row.targets),
            step_id=None,
            policy_version=POLICY_VERSION,
        )
    assert reason == "approval belongs to another workspace"
    assert (
        b_user.post(f"/approvals/{appr['id']}/decision", {"decision": "approve", "acknowledged": True}).status_code
        == 404
    )


# ---------------------------------------------------------------- untrusted model output
def test_model_cannot_skip_approval_or_choose_its_permissions(make_user: Any, engine: Any, owner_engine: Any) -> None:
    from app.engine.sandbox import isolation_status

    if not isolation_status()[0]:
        pytest.skip("sandbox unavailable on this host")
    api = make_user()
    MOCK_SCRIPT.append(
        json.dumps(
            {
                "summary": "do it",
                "steps": [
                    {
                        "goal": "Run code",
                        "tool": "code.run_python",
                        "args": {"code": "print(1)"},
                        "expected_output": "1",
                        "requires_approval": False,
                        "impact": "none",
                        "permissions": ["admin"],
                        "destinations": [],
                    }
                ],
            }
        )
    )
    t = create_task(api, "Calculate something for me please.")
    engine.drain()
    t = api.get(f"/tasks/{t['id']}").json()
    (step,) = t["plan"]["steps"]
    assert step["requires_approval"] is True and step["impact"] == "sensitive_change"
    assert step["policy"]["outcome"] == "require_approval"
    events = [e["message"] for e in api.get(f"/tasks/{t['id']}/events").json()["items"]]
    assert any("extra fields" in m for m in events)


def test_unknown_tool_gets_one_repair_then_fails_visibly(make_user: Any, engine: Any, owner_engine: Any) -> None:
    api = make_user()
    bad = json.dumps({"steps": [{"goal": "Wipe the server", "tool": "shell.exec", "args": {"cmd": "rm -rf /"}}]})
    MOCK_SCRIPT.extend([bad, bad])
    t = create_task(api, "Clean up the server for me please.")
    engine.drain()
    t = api.get(f"/tasks/{t['id']}").json()
    assert t["status"] == "failed" and "valid plan" in t["error_message"]
    with owner_engine.connect() as c:
        n = c.execute(text("SELECT count(*) FROM model_calls WHERE task_id = :t"), {"t": t["id"]}).scalar_one()
    assert n == 2  # one bounded repair attempt, no loop


def test_repair_attempt_can_fix_the_plan(make_user: Any, engine: Any) -> None:
    api = make_user()
    MOCK_SCRIPT.extend(
        [
            "Sure! Here is your plan: not json",
            json.dumps(
                {
                    "summary": "ok",
                    "steps": [{"goal": "Write the report", "tool": "report.write", "args": {"title": "R"}}],
                }
            ),
        ]
    )
    t = create_task(api, "Write me a report about nothing in particular.")
    engine.drain()
    t = api.get(f"/tasks/{t['id']}").json()
    assert t["status"] == "awaiting_approval" and [s["tool_id"] for s in t["plan"]["steps"]] == ["report.write"]


def test_plan_cannot_reference_files_that_are_not_attached(make_user: Any, engine: Any) -> None:
    owner, other = make_user(), make_user()
    foreign = upload(other, "secret.csv").json()
    step = {"goal": "Read it", "tool": "files.read", "args": {"file_id": foreign["id"]}}
    MOCK_SCRIPT.extend([json.dumps({"steps": [step]}), json.dumps({"steps": [step]})])
    t = create_task(owner, "Read the secret file from the other workspace.")
    engine.drain()
    t = owner.get(f"/tasks/{t['id']}").json()
    assert t["status"] == "failed" and "not attached" in t["error_message"]


def test_unavailable_tools_are_listed_honestly(make_user: Any) -> None:
    api = make_user()
    tools = {t["id"]: t for t in api.get("/agent/tools").json()}
    for tid in ("wordpress.write", "email.send", "browser.automation"):
        assert tools[tid]["available"] is False and tools[tid]["unavailable_reason"]
    assert tools["files.analyze"]["available"] is True
    assert tools["ai.summarize"]["available"] is False  # no model configured in this test


def test_cross_tenant_artifacts_and_tasks_are_isolated(make_user: Any, engine: Any) -> None:
    a, b = make_user(), make_user()
    t = create_task(a, "Write me a report about nothing in particular.")
    engine.drain()
    t = a.get(f"/tasks/{t['id']}").json()
    _approve_all(a, t)
    engine.drain()
    art = a.get(f"/tasks/{t['id']}").json()["artifacts"][0]
    assert b.get(f"/artifacts/{art['id']}/download").status_code == 404
    assert b.get(f"/tasks/{t['id']}").status_code == 404
