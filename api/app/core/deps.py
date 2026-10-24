"""Request dependencies: client IP, CSRF, and the authenticated tenant context.

The active workspace comes from the server-side session row — never from a
header, query parameter or body field supplied by the client.
"""

from __future__ import annotations

import ipaddress
import uuid
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db, utcnow
from app.core.errors import ApiError
from app.core.security import constant_time_equals, token_hash
from app.domain.enums import WorkspaceRole
from app.models import AuthSession, User, Workspace, WorkspaceMembership
from app.ports import AuditRecord
from app.services.audit import DbAuditLogger

CSRF_COOKIE = "stw_csrf"
CSRF_HEADER = "x-csrf-token"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def csrf_cookie_name(settings: Settings) -> str:
    # __Host- stops sibling subdomains from planting ("tossing") a CSRF cookie in production.
    return "__Host-stw_csrf" if settings.cookie_secure else CSRF_COOKIE


def session_cookie_name(settings: Settings) -> str:
    # The __Host- prefix makes browsers refuse the cookie unless it is Secure, host-only and Path=/.
    return "__Host-stw_session" if settings.cookie_secure else "stw_session"


def client_ip(request: Request) -> str | None:
    """The client's IP for rate limiting and audit.

    X-Forwarded-For is never used: the Next.js proxy forwards whatever the client
    sent. With TRUST_PROXY_HEADERS=true, the API reads only X-Real-IP, which the
    outermost reverse proxy (Caddy, deploy/Caddyfile) overwrites with the real
    peer address on every request.
    """
    settings = get_settings()
    candidate: str | None = None
    if settings.trust_proxy_headers:
        candidate = request.headers.get("x-real-ip", "").strip() or None
    if not candidate and request.client:
        candidate = request.client.host
    try:
        return str(ipaddress.ip_address(candidate)) if candidate else None
    except ValueError:
        return None


def request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", ""))


def verify_csrf(request: Request) -> None:
    """Double-submit token check plus Origin check for every state-changing request."""
    if request.method not in UNSAFE_METHODS:
        return
    settings = get_settings()
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != settings.app_origin.rstrip("/"):
        raise ApiError(403, "csrf_failed", "This request came from an unexpected site and was blocked.")
    cookie = request.cookies.get(csrf_cookie_name(settings), "")
    header = request.headers.get(CSRF_HEADER, "")
    if not cookie or not header or not constant_time_equals(cookie, header):
        raise ApiError(
            403, "csrf_failed", "Your security token is missing or out of date. Refresh the page and try again."
        )


@dataclass
class Context:
    db: Session
    user: User
    workspace: Workspace
    role: WorkspaceRole
    session: AuthSession
    ip: str | None
    request_id: str

    @property
    def audit(self) -> DbAuditLogger:
        return DbAuditLogger(self.db)

    def log(self, action: str, category: str, message: str, **kw: object) -> None:
        self.audit.record(
            AuditRecord(
                action=action,
                category=category,
                message=message,
                workspace_id=self.workspace.id,
                actor_user_id=self.user.id,
                ip=self.ip,
                request_id=self.request_id,
                **kw,  # type: ignore[arg-type]
            )
        )

    def deny(self, target_type: str, target_id: object, what: str) -> ApiError:
        """Record an authorization failure and return the 404 to raise (no existence oracle).

        Probing is rate limited (429 after the limit) so it can't flood the append-only audit log.
        """
        from app.core import ratelimit as RL

        RL.hit(RL.DENIED_USER, str(self.user.id))
        self.log(
            "authz.denied",
            "security",
            f"Access to a {target_type} outside this workspace was blocked",
            target_type=target_type,
            target_id=str(target_id)[:64],
        )
        # Commit the audit row even though the request fails.
        self.db.commit()
        return ApiError(404, "not_found", f"That {what} was not found in your workspace.")

    def require_role(self, *roles: WorkspaceRole) -> None:
        if self.role not in roles:
            self.log("authz.role_denied", "security", "An action needing a higher workspace role was blocked")
            self.db.commit()
            raise ApiError(403, "forbidden", "Only workspace owners and admins can change this.")


def _load_session(request: Request, db: Session) -> tuple[AuthSession, User, Workspace, WorkspaceMembership]:
    settings = get_settings()
    raw = request.cookies.get(session_cookie_name(settings))
    if not raw or len(raw) > 100:
        raise ApiError(401, "not_authenticated", "Please sign in to continue.")
    now = utcnow()
    row = db.execute(
        select(AuthSession, User, Workspace, WorkspaceMembership)
        .join(User, User.id == AuthSession.user_id)
        .join(Workspace, Workspace.id == AuthSession.workspace_id)
        .join(
            WorkspaceMembership,
            (WorkspaceMembership.workspace_id == AuthSession.workspace_id)
            & (WorkspaceMembership.user_id == AuthSession.user_id),
        )
        .where(AuthSession.token_hash == token_hash(raw))
    ).first()
    if row is None:
        raise ApiError(401, "not_authenticated", "Please sign in to continue.")
    sess, user, ws, membership = row
    if sess.revoked_at is not None or sess.expires_at <= now or sess.idle_expires_at <= now:
        raise ApiError(401, "session_expired", "Your session has ended. Please sign in again.")
    # Sliding idle timeout, capped by the absolute expiry. Throttled to one write per minute.
    if (now - sess.last_seen_at) > timedelta(minutes=1):
        sess.last_seen_at = now
        sess.idle_expires_at = min(sess.expires_at, now + timedelta(hours=settings.session_idle_hours))
    return sess, user, ws, membership


def get_context(request: Request, db: Session = Depends(get_db)) -> Context:
    sess, user, ws, membership = _load_session(request, db)
    return Context(
        db=db,
        user=user,
        workspace=ws,
        role=WorkspaceRole(membership.role),
        session=sess,
        ip=client_ip(request),
        request_id=request_id(request),
    )


def parse_uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise ApiError(404, "not_found", f"That {what} was not found in your workspace.") from None
