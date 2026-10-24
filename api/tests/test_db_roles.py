"""Database role separation (Phase 3). Each runtime role gets only what its process needs;
the database refuses everything else, whatever the application code tries."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from tests.conftest import create_task, upload

DENIED = "permission denied"


def _denied(engine: Any, sql: str, **params: Any) -> None:
    with pytest.raises(ProgrammingError, match=DENIED), engine.begin() as c:
        c.execute(text(sql), params)


def _ok(engine: Any, sql: str, **params: Any) -> Any:
    with engine.begin() as c:
        return c.execute(text(sql), params).fetchall()


@pytest.fixture()
def seeded(make_user: Any) -> dict[str, Any]:
    api = make_user()
    task = create_task(api)
    f = upload(api).json()
    return {"task": task, "file": f}


@pytest.mark.parametrize("role", ["worker", "deleter", "readonly"])
@pytest.mark.parametrize(
    "table",
    [
        "tasks",
        "task_steps",
        "files",
        "jobs",
        "approval_requests",
        "deletion_requests",
        "audit_events",
        "users",
        "workspaces",
    ],
)
def test_no_runtime_role_can_delete_rows(role_engines: dict[str, Any], seeded: Any, role: str, table: str) -> None:
    _denied(role_engines[role], f"DELETE FROM {table}")  # noqa: S608 - fixed names


@pytest.mark.parametrize("role", ["app", "worker", "deleter", "readonly"])
@pytest.mark.parametrize(
    "stmt", ["TRUNCATE files", "DROP TABLE files", "CREATE TABLE x (id int)", "ALTER TABLE files ADD c int"]
)
def test_no_runtime_role_can_truncate_or_change_schema(role_engines: dict[str, Any], role: str, stmt: str) -> None:
    with pytest.raises(ProgrammingError), role_engines[role].begin() as c:
        c.execute(text(stmt))


@pytest.mark.parametrize("role", ["worker", "deleter", "readonly"])
@pytest.mark.parametrize(
    "sql", ["SELECT * FROM sessions", "SELECT * FROM auth_tokens", "SELECT password_hash FROM users"]
)
def test_secrets_are_not_readable_by_workers_or_reporting(role_engines: dict[str, Any], role: str, sql: str) -> None:
    _denied(role_engines[role], sql)


def test_public_user_columns_are_readable_by_worker(role_engines: dict[str, Any], seeded: Any) -> None:
    assert _ok(role_engines["worker"], "SELECT id, name, email FROM users LIMIT 1")


def test_only_deleter_can_soft_delete_files(role_engines: dict[str, Any], seeded: Any) -> None:
    fid = seeded["file"]["id"]
    sql = "UPDATE files SET deleted_at = now() WHERE id = :id"
    _denied(role_engines["app"], sql, id=fid)
    _denied(role_engines["worker"], sql, id=fid)
    _denied(role_engines["readonly"], sql, id=fid)
    with role_engines["deleter"].begin() as c:
        c.execute(text(sql + " AND false"), {"id": fid})  # privilege check only; changes nothing


def test_app_role_can_still_update_ordinary_file_fields(role_engines: dict[str, Any], seeded: Any) -> None:
    with role_engines["app"].begin() as c:
        c.execute(text("UPDATE files SET collection = collection WHERE id = :id"), {"id": seeded["file"]["id"]})


def test_worker_cannot_change_file_classification_or_workspace_policy(
    role_engines: dict[str, Any], seeded: Any
) -> None:
    w = role_engines["worker"]
    _denied(w, "UPDATE files SET classification = 'public'")
    _denied(w, "UPDATE workspaces SET privacy_mode = 'custom'")
    _denied(w, "UPDATE workspaces SET allowed_domains = '[]'::jsonb")
    _denied(w, "UPDATE approval_decisions SET decision = 'approve'")
    _denied(w, "INSERT INTO approval_decisions (id) VALUES (gen_random_uuid())")


def test_worker_can_run_task_bookkeeping(role_engines: dict[str, Any], seeded: Any) -> None:
    tid = seeded["task"]["id"]
    with role_engines["worker"].begin() as c:
        c.execute(text("UPDATE tasks SET updated_at = updated_at WHERE id = :id"), {"id": tid})
        c.execute(text("UPDATE jobs SET attempts = attempts WHERE task_id = :id"), {"id": tid})


def test_append_only_tables_stay_append_only_for_worker(role_engines: dict[str, Any], seeded: Any) -> None:
    for table in ("audit_events", "task_events", "model_calls"):
        _denied(role_engines["worker"], f"UPDATE {table} SET id = id")  # noqa: S608


def test_readonly_role_cannot_write(role_engines: dict[str, Any], seeded: Any) -> None:
    r = role_engines["readonly"]
    assert _ok(r, "SELECT count(*) FROM tasks")
    _denied(r, "UPDATE tasks SET title = title")
    _denied(r, "INSERT INTO audit_events (id) VALUES (gen_random_uuid())")


def _decided_approval(api: Any, owner_engine: Any) -> str:
    f = upload(api, "z.csv").json()
    a = api.post(f"/files/{f['id']}/deletion-request", {"reason": "cleanup"}).json()
    api.post(
        f"/approvals/{a['id']}/decision", {"decision": "approve", "acknowledged": True, "confirmed_items": ["z.csv"]}
    )
    with owner_engine.begin() as c:  # the deletion service consumed it
        c.execute(text("UPDATE approval_requests SET execution_state = 'executed' WHERE id = :a"), {"a": a["id"]})
    return str(a["id"])


def test_worker_cannot_revive_or_redecide_approvals(
    make_user: Any, role_engines: dict[str, Any], owner_engine: Any
) -> None:
    """P3-SR-5 regression: one-time approvals stay one-time even for a compromised worker."""
    from sqlalchemy.exc import DBAPIError

    aid = _decided_approval(make_user(), owner_engine)
    w = role_engines["worker"]
    for sql in (
        "UPDATE approval_requests SET status = 'pending' WHERE id = :a",
        "UPDATE approval_requests SET decided_by = NULL WHERE id = :a",
        "UPDATE approval_requests SET payload_hash = 'x' WHERE id = :a",
    ):
        _denied(w, sql, a=aid)
    with pytest.raises(DBAPIError, match="cannot go from executed to pending_execution"), w.begin() as c:
        c.execute(text("UPDATE approval_requests SET execution_state = 'pending_execution' WHERE id = :a"), {"a": aid})
    # Even the schema owner can't revive it (trigger applies to every role).
    with pytest.raises(DBAPIError), owner_engine.begin() as c:
        c.execute(text("UPDATE approval_requests SET status = 'rejected' WHERE id = :a"), {"a": aid})


def test_worker_cannot_weaken_task_classification(seeded: Any, role_engines: dict[str, Any]) -> None:
    w = role_engines["worker"]
    _denied(w, "UPDATE tasks SET data_classification = 'public' WHERE id = :t", t=seeded["task"]["id"])
    _denied(w, "UPDATE tasks SET prompt = 'x' WHERE id = :t", t=seeded["task"]["id"])
    with w.begin() as c:
        c.execute(text("UPDATE tasks SET updated_at = updated_at WHERE id = :t"), {"t": seeded["task"]["id"]})


def test_api_role_cannot_insert_pre_deleted_files(seeded: Any, role_engines: dict[str, Any]) -> None:
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError, match="only by the deletion service"), role_engines["app"].begin() as c:
        c.execute(
            text(
                "INSERT INTO files (workspace_id, original_name, storage_key, content_type, type_label, size_bytes, sha256,"
                " status, scan_status, classification, collection, uploaded_by, deleted_at)"
                " SELECT workspace_id, 'x', 'k', 't', 'TXT', 1, 's', 'ready', 'pending', 'unknown', 'Research', uploaded_by, now()"
                " FROM files LIMIT 1"
            )
        )
