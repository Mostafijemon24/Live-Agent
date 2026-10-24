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
