"""File upload validation, private storage, access controls and deletion requests."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from conftest import upload
from sqlalchemy import text

from app.core.config import get_settings

PDF = b"%PDF-1.7\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def test_upload_csv_is_private_unscanned_and_unclassified(make_user: Any, owner_engine: Any) -> None:
    api = make_user()
    r = upload(api, "crawl.csv", b"url,status\n/,200\n")
    assert r.status_code == 201, r.text
    f = r.json()
    assert f["status"] == "unscanned" and f["scan_status"] == "not_configured"
    assert f["classification"] == "unknown" and f["type_label"] == "CSV" and f["size_bytes"] == 17
    with owner_engine.connect() as c:
        key = c.execute(text("SELECT storage_key FROM files WHERE id = :i"), {"i": f["id"]}).scalar_one()
    root = Path(os.environ["STORAGE_DIR"]).resolve()
    stored = root / key
    assert stored.is_file() and "crawl" not in key  # random internal name
    assert oct(stored.stat().st_mode)[-3:] == "600"
    usage = {i["key"]: i["used"] for i in api.get("/usage").json()["items"]}
    assert usage["storage_bytes"] == 17 and usage["files_uploaded"] == 1


def test_content_is_sniffed_not_trusted(make_user: Any) -> None:
    api = make_user()
    assert upload(api, "report.pdf", PDF).status_code == 201
    # Text pretending to be a PDF.
    assert upload(api, "fake.pdf", b"hello I am not a pdf").status_code == 415
    # Windows executable renamed to .csv.
    r = upload(api, "invoice.csv", b"MZ\x90\x00\x03" + b"\x00" * 100)
    assert r.status_code == 415 and r.json()["error"]["code"] == "unsupported_file_type"
    # HTML / script content renamed to .txt.
    assert upload(api, "notes.txt", b"<html><script>alert(1)</script></html>").status_code == 415
    # Plain zip archive.
    assert upload(api, "bundle.zip", b"PK\x03\x04" + b"\x00" * 50).status_code == 415
    # Empty file.
    assert upload(api, "empty.csv", b"").status_code == 422
    # Rejected uploads leave nothing behind.
    assert api.get("/files").json()["total"] == 1


def test_size_limit_enforced(make_user: Any, monkeypatch: Any) -> None:
    api = make_user()
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 1024)
    r = upload(api, "big.csv", b"a," * 2000)
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"
    assert api.get("/files").json()["total"] == 0
    root = Path(os.environ["STORAGE_DIR"])
    assert not list(root.rglob("*.part"))


def test_path_traversal_names_are_neutralised(make_user: Any) -> None:
    api = make_user()
    r = upload(api, "../../../../etc/passwd.txt", b"just text")
    assert r.status_code == 201
    assert r.json()["name"] == "passwd.txt"
    assert not Path("/etc/passwd.txt").exists()


def test_download_is_attachment_with_nosniff(make_user: Any) -> None:
    api = make_user()
    f = upload(api, 'we"ird.csv', b"a,b\n1,2\n").json()
    r = api.get(f"/files/{f['id']}/download")
    assert r.status_code == 200 and r.content == b"a,b\n1,2\n"
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["x-content-type-options"] == "nosniff"
    cd = r.headers["content-disposition"]
    assert cd.startswith('attachment; filename="') and cd.count('"') == 2  # client name can't break the header
    assert "sandbox" in r.headers["content-security-policy"]


def test_classification_change_is_audited(make_user: Any) -> None:
    api = make_user()
    f = upload(api).json()
    r = api.patch(f"/files/{f['id']}", {"classification": "confidential"})
    assert r.json()["classification"] == "confidential"
    assert api.patch(f"/files/{f['id']}", {"classification": "secret"}).status_code == 422
    acts = api.get("/activity", params={"type": "security"}).json()["items"]
    assert any(a["action"] == "privacy.classification_changed" for a in acts)


def test_deletion_approval_only_queues_the_deletion_service(make_user: Any, owner_engine: Any) -> None:
    api = make_user()
    f = upload(api, "old.csv").json()
    r = api.post(f"/files/{f['id']}/deletion-request", {"reason": "Not used anymore"})
    assert r.status_code == 201
    appr = r.json()
    assert (
        appr["category"] == "record_deletion" and appr["affected_items"] == ["old.csv"] and appr["status"] == "pending"
    )
    assert api.get(f"/files/{f['id']}").json()["deletion_requested"] is True
    assert api.post(f"/files/{f['id']}/deletion-request", {"reason": "again"}).status_code == 409
    # The request records target, scope, expected records, reason, requester and approval link.
    with owner_engine.connect() as c:
        dr = c.execute(
            text(
                "SELECT target_type, target_id, scope, expected_affected, reason, requested_by, approval_id, status FROM deletion_requests"
            )
        ).all()
    mine = next(d for d in dr if str(d.target_id) == f["id"])
    assert mine.target_type == "file" and mine.reason == "Not used anymore" and str(mine.approval_id) == appr["id"]
    assert mine.expected_affected[0]["name"] == "old.csv" and mine.status == "pending_approval"
    # Approving records the decision and queues the separate deletion service; the API deletes nothing.
    r = api.post(
        f"/approvals/{appr['id']}/decision",
        {"decision": "approve", "acknowledged": True, "confirmed_items": ["old.csv"]},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "approved" and r.json()["execution_state"] == "pending_execution"
    assert r.json()["operation"] == "deletion.execute" and r.json()["targets"] == [f"file:{f['id']}"]
    # The file and its bytes still exist until the deletion service runs.
    assert api.get(f"/files/{f['id']}").status_code == 200
    assert api.get(f"/files/{f['id']}/download").status_code == 200
    with owner_engine.connect() as c:
        status = c.execute(
            text("SELECT status FROM deletion_requests WHERE approval_id = :a"), {"a": appr["id"]}
        ).scalar_one()
        job = c.execute(
            text(
                "SELECT kind, queue, status FROM jobs WHERE payload->>'deletion_request_id' IS NOT NULL ORDER BY created_at DESC LIMIT 1"
            )
        ).one()
    assert status == "approved"
    assert (job.kind, job.queue, job.status) == ("deletion.execute", "deletion", "pending")


def test_upload_requires_known_collection_and_auth(make_user: Any, app: Any) -> None:
    api = make_user()
    assert upload(api, collection="../etc").status_code == 422
    from conftest import Api

    anon = Api(app)
    assert upload(anon).status_code == 401


def test_anonymous_multipart_is_refused_before_the_body_is_read(app: Any) -> None:
    """The middleware answers 401 without consuming the body, so anonymous clients cannot make the API spool uploads."""
    import asyncio

    from app.core.middleware import RequestContextMiddleware

    reached: list[bool] = []
    reads: list[bool] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        reached.append(True)

    async def receive() -> dict[str, Any]:
        reads.append(True)
        return {"type": "http.request", "body": b"x" * 1024, "more_body": True}

    sent: list[dict[str, Any]] = []

    async def send(msg: dict[str, Any]) -> None:
        sent.append(msg)

    mw = RequestContextMiddleware(inner, max_body_bytes=10_000_000, hsts=False, session_cookie="stw_session")
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/files",
        "headers": [(b"content-type", b"multipart/form-data; boundary=x"), (b"cookie", b"stw_csrf=abc")],
    }
    asyncio.run(mw(scope, receive, send))
    assert sent[0]["status"] == 401 and b"not_authenticated" in sent[1]["body"]
    assert not reached and not reads
    # With a session cookie the request reaches the app (the route still validates the session).
    scope["headers"] = [(b"content-type", b"multipart/form-data; boundary=x"), (b"cookie", b"stw_session=abc")]
    asyncio.run(mw(scope, receive, send))
    assert reached
