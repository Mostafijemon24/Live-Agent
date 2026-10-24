"""Authentication, sessions, CSRF, verification and password reset."""

from __future__ import annotations

import logging
from typing import Any

from conftest import PASSWORD, Api, latest_token, new_email, outbox_messages
from sqlalchemy import text

GENERIC = "That email and password combination did not match, or the email address hasn't been verified yet."


def _register(api: Api, email: str, password: str = PASSWORD) -> Any:
    return api.post(
        "/auth/register", {"name": "Ada Lovelace", "email": email, "password": password, "accept_terms": True}
    )


def test_full_registration_verification_login_flow(app: Any, owner_engine: Any) -> None:
    api = Api(app)
    email = new_email()
    r = _register(api, email)
    assert r.status_code == 202
    assert "Check your inbox" in r.json()["message"]
    # Not signed in yet.
    assert api.get("/me").status_code == 401
    # Login before verification fails with the generic message.
    r = api.post("/auth/login", {"email": email, "password": PASSWORD})
    assert r.status_code == 401 and r.json()["error"]["message"] == GENERIC

    token = latest_token(email, "/verify-email")
    assert api.post("/auth/verify-email", {"token": token}).status_code == 200
    # Single use.
    assert api.post("/auth/verify-email", {"token": token}).json()["error"]["code"] == "invalid_or_expired_token"

    r = api.post("/auth/login", {"email": email.upper(), "password": PASSWORD})
    assert r.status_code == 200
    me = r.json()
    assert me["user"]["email"] == email and me["user"]["email_verified"] is True
    assert me["workspace"]["role"] == "owner" and me["demo"] is False
    assert api.get("/me").json()["user"]["id"] == me["user"]["id"]

    # Password is stored as an Argon2id hash, never in clear text.
    with owner_engine.connect() as c:
        h = c.execute(text("SELECT password_hash FROM users WHERE email = :e"), {"e": email}).scalar_one()
    assert h.startswith("$argon2id$") and PASSWORD not in h


def test_registration_does_not_reveal_existing_accounts(app: Any, make_user: Any) -> None:
    existing = make_user()
    api = Api(app)
    r1 = _register(api, existing.email)
    r2 = _register(api, new_email())
    assert r1.status_code == r2.status_code == 202
    assert r1.json() == r2.json()
    # The real owner is told by email instead.
    assert any("tried to create" in m["subject"] for m in outbox_messages(existing.email))
    # And the attacker cannot sign in with their own password.
    r = api.post("/auth/login", {"email": existing.email, "password": "attacker-password-1"})
    assert r.status_code == 401 and r.json()["error"]["message"] == GENERIC


def test_login_failures_are_indistinguishable(app: Any, make_user: Any) -> None:
    user = make_user()
    api = Api(app)
    wrong_pw = api.post("/auth/login", {"email": user.email, "password": "wrong-password-9"})
    unknown = api.post("/auth/login", {"email": new_email(), "password": "wrong-password-9"})
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json()["error"]["code"] == unknown.json()["error"]["code"] == "invalid_credentials"
    assert wrong_pw.json()["error"]["message"] == unknown.json()["error"]["message"] == GENERIC


def test_password_policy_and_input_validation(app: Any) -> None:
    api = Api(app)
    r = _register(api, new_email(), password="short1")
    assert r.status_code == 422
    fields = {d["field"]: d["message"] for d in r.json()["error"]["details"]}
    assert fields["password"] == "Use at least 10 characters, including a number."
    r = api.post("/auth/register", {"name": "A", "email": "not-an-email", "password": PASSWORD, "accept_terms": True})
    assert r.status_code == 422 and any(d["field"] == "email" for d in r.json()["error"]["details"])
    r = api.post("/auth/register", {"name": "A", "email": new_email(), "password": PASSWORD, "accept_terms": False})
    assert r.status_code == 422
    # Unknown fields are rejected (no mass assignment, e.g. role or workspace_id).
    r = api.post(
        "/auth/register",
        {"name": "A", "email": new_email(), "password": PASSWORD, "accept_terms": True, "role": "admin"},
    )
    assert r.status_code == 422


def test_session_cookie_flags_and_hashed_storage(app: Any, owner_engine: Any, make_user: Any) -> None:
    api = make_user()
    raw = api.c.cookies.get("stw_session")
    assert raw and len(raw) >= 40
    # Fresh login to inspect the Set-Cookie header.
    api2 = Api(app)
    r = api2.post("/auth/login", {"email": api.email, "password": PASSWORD})
    header = r.headers["set-cookie"].lower()
    assert "httponly" in header and "samesite=lax" in header and "path=/" in header
    with owner_engine.connect() as c:
        stored = c.execute(text("SELECT token_hash FROM sessions")).scalars().all()
    assert all(bytes(s) != raw.encode() for s in stored)
    assert all(len(bytes(s)) == 32 for s in stored)


def test_logout_revokes_session(make_user: Any) -> None:
    api = make_user()
    raw = api.c.cookies.get("stw_session")
    assert api.post("/auth/logout").status_code == 204
    assert api.get("/me").status_code == 401
    # Replaying the old cookie does not work either.
    api.c.cookies.set("stw_session", raw)
    r = api.get("/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "session_expired"


def test_session_idle_and_absolute_expiry(make_user: Any, owner_engine: Any) -> None:
    api = make_user()
    uid = api.me["user"]["id"]
    with owner_engine.begin() as c:
        c.execute(
            text("UPDATE sessions SET idle_expires_at = now() - interval '1 minute' WHERE user_id = :u"), {"u": uid}
        )
    assert api.get("/me").json()["error"]["code"] == "session_expired"

    api2 = make_user()
    uid2 = api2.me["user"]["id"]
    with owner_engine.begin() as c:
        c.execute(text("UPDATE sessions SET expires_at = now() - interval '1 minute' WHERE user_id = :u"), {"u": uid2})
    assert api2.get("/me").status_code == 401


def test_csrf_required_on_state_changes(make_user: Any, app: Any) -> None:
    api = make_user()
    body = {"prompt": "Write a summary of our pricing page", "type": "research"}
    # Missing header.
    r = api.c.post("/api/v1/tasks", json=body)
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    # Wrong token.
    r = api.c.post("/api/v1/tasks", json=body, headers={"X-CSRF-Token": "forged-token-value"})
    assert r.status_code == 403
    # Correct token but cross-site Origin.
    r = api.c.post("/api/v1/tasks", json=body, headers={"X-CSRF-Token": api.csrf, "Origin": "https://evil.example"})
    assert r.status_code == 403
    # Login is protected too (login CSRF).
    anon = Api(app)
    r = anon.c.post("/api/v1/auth/login", json={"email": api.email, "password": PASSWORD})
    assert r.status_code == 403
    # Correct token and same origin succeeds.
    r = api.c.post("/api/v1/tasks", json=body, headers={"X-CSRF-Token": api.csrf, "Origin": "http://testserver.local"})
    assert r.status_code == 201


def test_password_reset_flow_revokes_sessions(app: Any, make_user: Any, owner_engine: Any) -> None:
    api = make_user()
    other_device = Api(app)
    assert other_device.post("/auth/login", {"email": api.email, "password": PASSWORD}).status_code == 200

    anon = Api(app)
    r1 = anon.post("/auth/forgot-password", {"email": api.email})
    r2 = anon.post("/auth/forgot-password", {"email": new_email()})
    assert r1.status_code == r2.status_code == 202 and r1.json() == r2.json()

    token = latest_token(api.email, "/reset-password")
    r = anon.post("/auth/reset-password", {"token": token, "password": "new-password-77"})
    assert r.status_code == 200
    # All existing sessions are gone.
    assert api.get("/me").status_code == 401
    assert other_device.get("/me").status_code == 401
    # Token is single use.
    assert anon.post("/auth/reset-password", {"token": token, "password": "another-pass-88"}).status_code == 400
    # Old password no longer works, new one does.
    assert anon.post("/auth/login", {"email": api.email, "password": PASSWORD}).status_code == 401
    assert anon.post("/auth/login", {"email": api.email, "password": "new-password-77"}).status_code == 200


def test_expired_reset_token_rejected(app: Any, make_user: Any, owner_engine: Any) -> None:
    api = make_user()
    anon = Api(app)
    anon.post("/auth/forgot-password", {"email": api.email})
    token = latest_token(api.email, "/reset-password")
    with owner_engine.begin() as c:
        c.execute(
            text("UPDATE auth_tokens SET expires_at = now() - interval '1 second' WHERE purpose = 'reset_password'")
        )
    r = anon.post("/auth/reset-password", {"token": token, "password": "new-password-77"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_or_expired_token"


def test_tokens_and_passwords_never_logged(app: Any, caplog: Any, owner_engine: Any) -> None:
    caplog.set_level(logging.DEBUG)
    api = Api(app)
    email = new_email()
    _register(api, email)
    token = latest_token(email, "/verify-email")
    api.post("/auth/verify-email", {"token": token})
    api.post("/auth/login", {"email": email, "password": PASSWORD})
    joined = "\n".join(r.getMessage() for r in caplog.records)
    assert token not in joined
    assert PASSWORD not in joined
    assert email not in joined  # mail log masks the address
    with owner_engine.connect() as c:
        dump = " ".join(str(r) for r in c.execute(text("SELECT message, metadata::text FROM audit_events")).all())
    assert PASSWORD not in dump and token not in dump


def test_resend_verification_is_generic(app: Any, make_user: Any) -> None:
    verified = make_user()
    api = Api(app)
    pending = new_email()
    _register(api, pending)
    a = api.post("/auth/resend-verification", {"email": verified.email})
    b = api.post("/auth/resend-verification", {"email": pending})
    c = api.post("/auth/resend-verification", {"email": new_email()})
    assert a.status_code == b.status_code == c.status_code == 202
    assert a.json() == b.json() == c.json()
    assert len([m for m in outbox_messages(pending) if "Verify" in m["subject"]]) == 2
