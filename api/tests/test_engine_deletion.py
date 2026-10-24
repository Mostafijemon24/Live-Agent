"""Deletion workflow: preview → one-time approval → re-validation → soft delete (deletion service,
own DB role) → audit → restore during retention → purge. Unauthorised deletions never happen."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import text

from tests.conftest import create_task, upload


def _request_and_approve(api: Any, name: str = "old.csv") -> tuple[dict[str, Any], dict[str, Any]]:
    f = upload(api, name, b"a,b\n1,2\n").json()
    appr = api.post(f"/files/{f['id']}/deletion-request", {"reason": "No longer needed"}).json()
    r = api.post(
        f"/approvals/{appr['id']}/decision", {"decision": "approve", "acknowledged": True, "confirmed_items": [name]}
    )
    assert r.status_code == 200 and r.json()["execution_state"] == "pending_execution"
    return f, appr


def _stored_path(owner_engine: Any, file_id: str) -> Path:
    from app.core.config import get_settings

    with owner_engine.connect() as c:
        key = c.execute(text("SELECT storage_key FROM files WHERE id = :f"), {"f": file_id}).scalar_one()
    return Path(get_settings().storage_dir) / key


def test_approved_deletion_is_executed_by_the_deletion_service(make_user: Any, engine: Any, owner_engine: Any) -> None:
    api = make_user()
    f, appr = _request_and_approve(api)
    path = _stored_path(owner_engine, f["id"])
    assert path.exists()
    engine.drain()
    # Gone from the workspace, recoverable from "Recently deleted".
    assert api.get(f"/files/{f['id']}").status_code == 410
    assert api.get(f"/files/{f['id']}/download").status_code == 410
    assert f["id"] not in {x["id"] for x in api.get("/files").json()["items"]}
    trash = api.get("/files", params={"deleted": "true"}).json()["items"]
    assert [x["id"] for x in trash] == [f["id"]] and trash[0]["restorable_until"]
    assert not path.exists()  # moved to trash, not left in place
    a = api.get(f"/approvals/{appr['id']}").json()
    assert a["execution_state"] == "executed"
    with owner_engine.connect() as c:
        dr = c.execute(
            text("SELECT status, execution_result FROM deletion_requests WHERE approval_id = :a"), {"a": appr["id"]}
        ).one()
    assert dr.status == "executed" and dr.execution_result["soft_deleted"] is True
    acts = {x["action"] for x in api.get("/activity", params={"type": "file"}).json()["items"]}
    assert "file.deleted" in acts

    # Restore within the retention window.
    r = api.post(f"/files/{f['id']}/restore")
    assert r.status_code == 202
    engine.drain()
    assert api.get(f"/files/{f['id']}").status_code == 200
    assert api.get(f"/files/{f['id']}/download").content == b"a,b\n1,2\n"
    assert "file.restored" in {x["action"] for x in api.get("/activity", params={"type": "file"}).json()["items"]}


def test_file_changed_after_approval_is_not_deleted(make_user: Any, engine: Any, owner_engine: Any) -> None:
    api = make_user()
    f, appr = _request_and_approve(api)
    with owner_engine.begin() as c:  # the content changed after the approver saw the preview
        c.execute(text("UPDATE files SET sha256 = repeat('0', 64) WHERE id = :f"), {"f": f["id"]})
    engine.drain()
    assert api.get(f"/files/{f['id']}").status_code == 200
    assert api.get(f"/approvals/{appr['id']}").json()["execution_state"] == "invalidated"
    with owner_engine.connect() as c:
        dr = c.execute(
            text("SELECT status, execution_result FROM deletion_requests WHERE approval_id = :a"), {"a": appr["id"]}
        ).one()
    assert dr.status == "execution_refused" and "changed" in dr.execution_result["reason"]


def test_approver_who_lost_their_role_cannot_authorise_deletion(make_user: Any, engine: Any, owner_engine: Any) -> None:
    api = make_user()
    f, _ = _request_and_approve(api)
    with owner_engine.begin() as c:
        c.execute(
            text("UPDATE workspace_memberships SET role = 'member' WHERE user_id = :u"), {"u": api.me["user"]["id"]}
        )
    engine.drain()
    with owner_engine.connect() as c:
        deleted = c.execute(text("SELECT deleted_at FROM files WHERE id = :f"), {"f": f["id"]}).scalar_one()
    assert deleted is None


def test_deletion_job_replay_is_a_no_op(make_user: Any, engine: Any, owner_engine: Any) -> None:
    from sqlalchemy.orm import Session

    from app.domain.enums import JobQueue
    from app.engine import queue as Q

    api = make_user()
    f, appr = _request_and_approve(api)
    engine.drain()
    with owner_engine.connect() as c:
        dr_id, first = c.execute(
            text("SELECT id, executed_at FROM deletion_requests WHERE approval_id = :a"), {"a": appr["id"]}
        ).one()
    with Session(owner_engine) as db:
        Q.enqueue(
            db,
            workspace_id=uuid.UUID(api.me["workspace"]["id"]),
            kind="deletion.execute",
            queue=JobQueue.deletion,
            payload={"deletion_request_id": str(dr_id)},
            settings=engine.settings,
        )
        db.commit()
    engine.drain()
    with owner_engine.connect() as c:
        again = c.execute(text("SELECT executed_at FROM deletion_requests WHERE id = :d"), {"d": dr_id}).scalar_one()
        n = c.execute(
            text("SELECT count(*) FROM audit_events WHERE action = 'file.deleted' AND target_id = :f"), {"f": f["id"]}
        ).scalar_one()
    assert again == first and n == 1


def test_unapproved_deletion_request_never_executes(make_user: Any, engine: Any, owner_engine: Any) -> None:
    from sqlalchemy.orm import Session

    from app.domain.enums import JobQueue
    from app.engine import queue as Q

    api = make_user()
    f = upload(api, "keep.csv").json()
    appr = api.post(f"/files/{f['id']}/deletion-request", {"reason": "maybe"}).json()
    with owner_engine.connect() as c:
        dr_id = c.execute(
            text("SELECT id FROM deletion_requests WHERE approval_id = :a"), {"a": appr["id"]}
        ).scalar_one()
    with owner_engine.begin() as c:  # someone forces the request into "approved" without a decision
        c.execute(text("UPDATE deletion_requests SET status = 'approved' WHERE id = :d"), {"d": dr_id})
        c.execute(
            text(
                "UPDATE approval_requests SET status = 'approved', execution_state = 'pending_execution' WHERE id = :a"
            ),
            {"a": appr["id"]},
        )
    with Session(owner_engine) as db:
        Q.enqueue(
            db,
            workspace_id=uuid.UUID(api.me["workspace"]["id"]),
            kind="deletion.execute",
            queue=JobQueue.deletion,
            payload={"deletion_request_id": str(dr_id)},
            settings=engine.settings,
        )
        db.commit()
    engine.drain()
    assert api.get(f"/files/{f['id']}").status_code == 200  # no recorded decision → refused
    with owner_engine.connect() as c:
        status = c.execute(text("SELECT status FROM deletion_requests WHERE id = :d"), {"d": dr_id}).scalar_one()
    assert status == "execution_refused"


def test_agent_can_only_propose_deletions(make_user: Any, engine: Any, owner_engine: Any) -> None:
    api = make_user()
    f = upload(api, "draft.csv").json()
    t = create_task(api, "Delete the attached draft file, it is obsolete.", attachment_file_ids=[f["id"]])
    engine.drain()
    t = api.get(f"/tasks/{t['id']}").json()
    tools = [s["tool_id"] for s in t["plan"]["steps"]]
    assert "files.request_deletion" in tools
    api.post(f"/tasks/{t['id']}/plan/approve", {"selected_step_ids": [s["id"] for s in t["plan"]["steps"]]})
    engine.drain()
    t = api.get(f"/tasks/{t['id']}").json()
    assert t["status"] == "completed"
    # The file still exists; a separate approval is waiting for a human.
    assert api.get(f"/files/{f['id']}").status_code == 200
    pend = [
        a
        for a in api.get("/approvals", params={"status": "pending"}).json()["items"]
        if a["category"] == "record_deletion"
    ]
    assert len(pend) == 1 and pend[0]["affected_items"] == ["draft.csv"] and pend[0]["operation"] == "deletion.execute"
    assert "Proposed by the agent" in pend[0]["reason"]


def test_purge_after_retention_removes_bytes_and_blocks_restore(make_user: Any, engine: Any, owner_engine: Any) -> None:
    from app.engine import scheduler

    api = make_user()
    f, _ = _request_and_approve(api)
    engine.drain()
    with owner_engine.begin() as c:
        c.execute(text("UPDATE files SET purge_after = now() - interval '1 minute' WHERE id = :f"), {"f": f["id"]})
    with engine.worker_factory() as db:
        assert scheduler.schedule_purges(db, engine.settings) >= 1
    engine.drain()
    with owner_engine.connect() as c:
        row = c.execute(text("SELECT deleted_at, purge_after FROM files WHERE id = :f"), {"f": f["id"]}).one()
    assert row.deleted_at is not None and row.purge_after is None  # tombstone kept, bytes gone
    assert api.post(f"/files/{f['id']}/restore").status_code == 410
    assert "file.purged" in {x["action"] for x in api.get("/activity", params={"type": "file"}).json()["items"]}
