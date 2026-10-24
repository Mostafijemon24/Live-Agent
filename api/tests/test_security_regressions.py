"""Regression tests for findings in SECURITY_REVIEW.md (one section per finding)."""

from __future__ import annotations

from typing import Any

from conftest import PASSWORD, Api, new_email

from app.core.config import get_settings

# ------------------------------------------------------------------ SR-1 rate-limit keys


def test_sr1_spoofed_x_forwarded_for_does_not_bypass_ip_limits(app: Any) -> None:
    """Rotating X-Forwarded-For (client-controlled through Next.js) must not create new buckets."""
    api = Api(app, ip="198.51.100.20")
    codes = []
    for i in range(7):
        r = api.c.post(
            "/api/v1/auth/register",
            json={"name": "N", "email": new_email(), "password": PASSWORD, "accept_terms": True},
            headers={"X-CSRF-Token": api.csrf, "X-Forwarded-For": f"203.0.113.{i}"},
        )
        codes.append(r.status_code)
    assert codes == [202] * 5 + [429, 429]


def test_sr1_x_real_ip_ignored_unless_proxy_trusted(app: Any, monkeypatch: Any) -> None:
    """Without a trusted proxy, client-sent X-Real-IP is ignored (all requests share the peer address)."""
    monkeypatch.setattr(get_settings(), "trust_proxy_headers", False)
    codes = []
    for i in range(6):
        api = Api(app, ip=f"192.0.2.{i + 10}")  # different X-Real-IP each time
        r = api.post("/auth/register", {"name": "N", "email": new_email(), "password": PASSWORD, "accept_terms": True})
        codes.append(r.status_code)
    assert codes == [202] * 5 + [429]


def test_sr1_register_limited_per_email(app: Any) -> None:
    email = new_email()
    codes = [
        Api(app)
        .post("/auth/register", {"name": "N", "email": email, "password": PASSWORD, "accept_terms": True})
        .status_code
        for _ in range(4)
    ]
    assert codes == [202, 202, 202, 429]


# ------------------------------------------------------------------ SR-3 upload content validation
def _zip(entries: dict[str, bytes]) -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


DOCX_OK = {"[Content_Types].xml": b"<Types/>", "word/document.xml": b"<w:document/>", "_rels/.rels": b"<r/>"}
XLSX_OK = {
    "[Content_Types].xml": b"<Types/>",
    "xl/workbook.xml": b"<workbook/>",
    "xl/printerSettings/printerSettings1.bin": b"\x00\x01",
}


def test_sr3_valid_office_documents_accepted(make_user: Any) -> None:
    from conftest import upload

    api = make_user()
    assert upload(api, "letter.docx", _zip(DOCX_OK)).status_code == 201
    assert upload(api, "sheet.xlsx", _zip(XLSX_OK)).status_code == 201


def test_sr3_bypass_payloads_refused(make_user: Any) -> None:
    from conftest import upload

    api = make_user()
    cases = {
        "report.docx": _zip({"word/x.xml": b"x", "payload.exe": b"MZ", "run.bat": b"echo"}),
        "macro.docx": _zip({**DOCX_OK, "word/vbaProject.bin": b"\x00"}),
        "evil.xlsx": _zip({"[Content_Types].xml": b"<Types/>", "evil.js": b"alert(1)"}),
        "embed.docx": _zip({**DOCX_OK, "word/embeddings/oleObject1.bin": b"\x00"}),
        "late.txt": b"a" * 600 + b"<script>alert(1)</script>",
        "notes.md": b"# Title\n\n<iframe src=https://evil.example></iframe>",
        "page.md": b"text <img src=x onerror=alert(1)>",
        "invoice.hta": b"%PDF-1.4\n<script>new ActiveXObject('WScript.Shell')</script>",
        "image.pdf": b"\x89PNG\r\n\x1a\n" + b"\x00" * 40,
        "latin1.txt": "caf\xe9".encode("latin-1"),
    }
    results = {name: upload(api, name, data).status_code for name, data in cases.items()}
    assert results == dict.fromkeys(cases, 415), results
    assert api.get("/files").json()["total"] == 0


def test_sr3_marker_split_across_read_chunks_is_caught(make_user: Any) -> None:
    from conftest import upload

    from app.adapters.storage import CHUNK

    api = make_user()
    data = b"a" * (CHUNK - 3) + b"<script>x</script>"
    assert upload(api, "big.txt", data).status_code == 415


# ------------------------------------------------------------------ SR-4 / SR-5 account enumeration
def _median_ms(fn: Any, n: int = 9) -> float:
    import statistics
    import time

    out = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t) * 1000)
    return statistics.median(out)


def test_sr4_register_and_forgot_timing_do_not_reveal_accounts(
    app: Any, make_user: Any, owner_engine: Any, monkeypatch: Any
) -> None:
    from sqlalchemy import text

    existing = make_user()
    monkeypatch.setattr(get_settings(), "auth_response_floor_ms", 300)

    def call(path: str, email: str) -> None:
        with owner_engine.begin() as c:
            c.execute(text("DELETE FROM rate_limit_buckets"))
        body = {"email": email}
        if path == "/auth/register":
            body = {"name": "N", "email": email, "password": PASSWORD, "accept_terms": True}
        assert Api(app).post(path, body).status_code == 202

    for path in ("/auth/register", "/auth/forgot-password", "/auth/resend-verification"):
        known = _median_ms(lambda p=path: call(p, existing.email))
        unknown = _median_ms(lambda p=path: call(p, new_email()))
        assert known >= 300 and unknown >= 300, (path, known, unknown)
        assert abs(known - unknown) < 25, (path, known, unknown)


def test_sr5_mail_outage_does_not_change_auth_responses(app: Any, make_user: Any, monkeypatch: Any) -> None:
    existing = make_user()
    s = get_settings()
    monkeypatch.setattr(s, "mail_backend", "smtp")
    monkeypatch.setattr(s, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(s, "smtp_port", 1)  # nothing listens: every send fails
    for email in (existing.email, new_email()):
        api = Api(app)
        assert api.post("/auth/forgot-password", {"email": email}).status_code == 202
        assert api.post("/auth/resend-verification", {"email": email}).status_code == 202
        r = api.post("/auth/register", {"name": "N", "email": email, "password": PASSWORD, "accept_terms": True})
        assert r.status_code == 202


# ------------------------------------------------------------------ SR-12 untrusted names
def test_sr12_registrant_name_not_echoed_in_verification_email(app: Any) -> None:
    from conftest import outbox_messages

    email = new_email()
    Api(app).post(
        "/auth/register",
        {
            "name": "https://steward-support.evil.example/verify",
            "email": email,
            "password": PASSWORD,
            "accept_terms": True,
        },
    )
    body = outbox_messages(email)[-1]["body"]
    assert "evil.example" not in body


def test_sr12_invisible_characters_removed_from_names(make_user: Any) -> None:
    from conftest import upload

    from app.adapters.storage import safe_display_name

    assert safe_display_name("invoice‮fdp.txt") == "invoicefdp.txt"
    assert safe_display_name("a​b\u0085c⁦.txt") == "abc.txt"
    api = make_user()
    r = upload(api, "report‮txt.csv", b"a,b\n")
    assert r.status_code == 201 and r.json()["name"] == "reporttxt.csv"
    r = api.patch("/me/preferences", {"name": "Eve‮​"})
    assert r.status_code == 200 and r.json()["profile"]["name"] == "Eve"
    assert api.patch("/me/preferences", {"name": "​‮"}).status_code == 422


# ------------------------------------------------------------------ SR-6 role matrix
import pytest  # noqa: E402


@pytest.mark.parametrize("role", ["viewer", "member"])
def test_sr6_role_matrix_on_write_endpoints(make_user: Any, owner_engine: Any, role: str) -> None:
    from conftest import create_task, upload
    from sqlalchemy import text

    api = make_user()
    task = create_task(api)
    f = upload(api).json()
    auto = api.post(
        "/automations",
        {
            "name": "A",
            "trigger": "manual",
            "template": "SEO report",
            "tools": [],
            "file_scope": "No files",
            "approval_policy": "Ask before any change",
        },
    ).json()
    with owner_engine.begin() as c:
        c.execute(
            text("UPDATE workspace_memberships SET role = :r WHERE user_id = :u"),
            {"r": role, "u": api.me["user"]["id"]},
        )

    admin_only = [
        ("PATCH", f"/files/{f['id']}", {"classification": "public"}),
        ("POST", f"/tasks/{task['id']}/plan/approve", {"selected_step_ids": []}),
        ("POST", f"/tasks/{task['id']}/plan/reject", {}),
        (
            "POST",
            "/automations",
            {
                "name": "B",
                "trigger": "manual",
                "template": "SEO report",
                "tools": ["Email"],
                "file_scope": "No files",
                "approval_policy": "Ask before any change",
            },
        ),
        ("PATCH", f"/automations/{auto['id']}", {"enabled": False}),
        ("POST", f"/automations/{auto['id']}/run", None),
        ("POST", "/integrations/notion/connect", None),
        ("PATCH", "/workspace/settings", {"name": "X"}),
    ]
    member_ok = [
        ("POST", "/tasks", {"prompt": "Research competitor pricing pages", "type": "research"}),
        ("POST", f"/files/{f['id']}/deletion-request", {"reason": "cleanup please"}),
        ("POST", f"/tasks/{task['id']}/messages", {"text": "hello", "kind": "question"}),
    ]

    def call(method: str, path: str, body: Any) -> int:
        return int((api.patch(path, body) if method == "PATCH" else api.post(path, body)).status_code)

    for m, p, b in admin_only:
        assert call(m, p, b) == 403, (role, p)
    for m, p, b in member_ok:
        code = call(m, p, b)
        assert (code == 403) if role == "viewer" else (code in (200, 201)), (role, p, code)
    # Reads and own preferences stay available to every role.
    assert api.get("/tasks").status_code == 200
    assert api.patch("/me/preferences", {"timezone": "UTC"}).status_code == 200


# ------------------------------------------------------------------ SR-7 composite tenant FKs
@pytest.mark.parametrize(
    "stmt",
    [
        "INSERT INTO jobs (workspace_id, kind, task_id) VALUES (:wb, 'x', :task_a)",
        "INSERT INTO audit_events (workspace_id, action, category, message, task_id) VALUES (:wb, 'x', 'task', 'x', :task_a)",
        "UPDATE tasks SET automation_id = :auto_a WHERE workspace_id = :wb",
        "INSERT INTO deletion_requests (workspace_id, target_type, target_id, scope, expected_affected, reason, requested_by, approval_id)"
        " VALUES (:wb, 'file', :file_a, 's', '[]', 'r', :user_b, :appr_b)",
    ],
)
def test_sr7_database_rejects_cross_tenant_references(make_user: Any, owner_engine: Any, stmt: str) -> None:
    from conftest import create_task, upload
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    a, b = make_user("A"), make_user("B")
    task_a = create_task(a)
    file_a = upload(a).json()
    auto_a = a.post(
        "/automations",
        {
            "name": "A",
            "trigger": "manual",
            "template": "SEO report",
            "tools": [],
            "file_scope": "No files",
            "approval_policy": "Ask before any change",
        },
    ).json()
    create_task(b)
    fb = upload(b).json()
    appr_b = b.post(f"/files/{fb['id']}/deletion-request", {"reason": "own file"}).json()
    params = {
        "wb": b.me["workspace"]["id"],
        "task_a": task_a["id"],
        "file_a": file_a["id"],
        "auto_a": auto_a["id"],
        "user_b": b.me["user"]["id"],
        "appr_b": appr_b["id"],
    }
    with pytest.raises(IntegrityError), owner_engine.begin() as c:
        c.execute(text(stmt), params)


# ------------------------------------------------------------------ SR-8 keyed approval binding
@pytest.mark.parametrize(
    "tamper",
    [
        "UPDATE approval_requests SET risk = 'low' WHERE id = :i",
        "UPDATE approval_requests SET data_leaves_workspace = true WHERE id = :i",
        "UPDATE approval_requests SET title = 'Harmless' WHERE id = :i",
        "UPDATE approval_requests SET consequences = 'None' WHERE id = :i",
        "UPDATE approval_requests SET destination = 'Somewhere else',"
        " payload_hash = encode(sha256(convert_to('forged', 'UTF8')), 'hex') WHERE id = :i",
    ],
)
def test_sr8_tampering_with_any_displayed_field_is_refused(make_user: Any, owner_engine: Any, tamper: str) -> None:
    from conftest import upload
    from sqlalchemy import text

    api = make_user()
    f = upload(api, "x.csv").json()
    a = api.post(f"/files/{f['id']}/deletion-request", {"reason": "cleanup"}).json()
    with owner_engine.begin() as c:
        c.execute(text(tamper), {"i": a["id"]})
    r = api.post(
        f"/approvals/{a['id']}/decision", {"decision": "approve", "acknowledged": True, "confirmed_items": ["x.csv"]}
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "approval_payload_changed"


def test_sr8_untampered_approval_still_works(make_user: Any) -> None:
    from conftest import upload

    api = make_user()
    f = upload(api, "y.csv").json()
    a = api.post(f"/files/{f['id']}/deletion-request", {"reason": "cleanup"}).json()
    r = api.post(
        f"/approvals/{a['id']}/decision", {"decision": "approve", "acknowledged": True, "confirmed_items": ["y.csv"]}
    )
    assert r.status_code == 200


# ------------------------------------------------------------------ SR-9 audit-flooding limits
def test_sr9_denied_probes_are_rate_limited(make_user: Any) -> None:
    import uuid

    api = make_user()
    codes = [api.get(f"/tasks/{uuid.uuid4()}").status_code for _ in range(32)]
    assert codes[:30] == [404] * 30 and codes[30:] == [429, 429]
    denials = [
        e
        for e in api.get("/activity", params={"type": "security", "page_size": 100}).json()["items"]
        if e["action"] == "authz.denied"
    ]
    assert len(denials) == 30  # nothing logged once limited


def test_sr9_integration_connect_is_rate_limited(make_user: Any, monkeypatch: Any) -> None:
    from app.core import ratelimit as RL

    monkeypatch.setattr(RL, "WRITE_USER", RL.Limit("write_user_test", 5, 60))
    api = make_user()
    codes = [api.post("/integrations/notion/connect").status_code for _ in range(7)]
    assert codes == [409] * 5 + [429, 429]


# ------------------------------------------------------------------ SR-13 hardening items
def test_sr13_login_revokes_the_previous_browser_session(app: Any, make_user: Any) -> None:
    api = make_user()
    old = api.c.cookies.get("stw_session")
    assert api.post("/auth/login", {"email": api.email, "password": PASSWORD}).status_code == 200
    new = api.c.cookies.get("stw_session")
    assert new and new != old
    probe = Api(app)
    probe.c.cookies.set("stw_session", old)
    assert probe.get("/me").status_code == 401
    assert api.get("/me").status_code == 200


def test_sr13_csrf_cookie_is_host_prefixed_when_secure(monkeypatch: Any) -> None:
    from app.core.deps import csrf_cookie_name, session_cookie_name

    s = get_settings()
    monkeypatch.setattr(s, "cookie_secure", True)
    assert csrf_cookie_name(s) == "__Host-stw_csrf" and session_cookie_name(s) == "__Host-stw_session"


def test_sr13_task_events_have_deterministic_order(make_user: Any) -> None:
    from conftest import create_task

    api = make_user()
    for _ in range(5):
        t = create_task(api)
        kinds = [e["kind"] for e in api.get(f"/tasks/{t['id']}/events").json()["items"]]
        assert kinds == ["task.created", "task.waiting"]
