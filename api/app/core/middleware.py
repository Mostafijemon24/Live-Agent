"""Request ID, security headers and request-size guard (pure ASGI, streaming-safe)."""

from __future__ import annotations

import re
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_RID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cache-control", b"no-store"),
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
    (b"cross-origin-resource-policy", b"same-origin"),
]


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int, hsts: bool, session_cookie: str = "") -> None:
        self.app = app
        self.max_body = max_body_bytes
        self.hsts = hsts
        self.session_cookie = session_cookie

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        incoming = headers.get("x-request-id", "")
        rid = incoming if _RID_RE.match(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = rid

        declared = headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > self.max_body:
            await _reject_too_large(send, rid)
            return

        # Multipart bodies are parsed (and spooled to disk) before route dependencies run, so refuse
        # uploads without a session cookie before reading any of the body. The real session check
        # still happens in the route; this only stops anonymous clients from making the API spool data.
        if (
            self.session_cookie
            and headers.get("content-type", "").lower().startswith("multipart/")
            and f"{self.session_cookie}=" not in headers.get("cookie", "")
        ):
            await _reject(send, rid, 401, b"not_authenticated", b"Please sign in to continue.")
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            msg = await receive()
            if msg["type"] == "http.request":
                received += len(msg.get("body", b""))
                if received > self.max_body:
                    raise _BodyTooLarge()
            return msg

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                h = list(message.get("headers", []))
                existing = {k.lower() for k, _ in h}
                h.append((b"x-request-id", rid.encode()))
                for k, v in SECURITY_HEADERS:
                    if k not in existing:
                        h.append((k, v))
                if self.hsts:
                    h.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                message["headers"] = h
            await send(message)

        try:
            await self.app(scope, limited_receive, send_wrapper)
        except _BodyTooLarge:
            await _reject_too_large(send, rid)


class _BodyTooLarge(Exception):
    pass


async def _reject_too_large(send: Send, rid: str) -> None:
    await _reject(send, rid, 413, b"payload_too_large", b"The request is too large.")


async def _reject(send: Send, rid: str, status: int, code: bytes, message: bytes) -> None:
    body = (
        b'{"error":{"code":"'
        + code
        + b'","message":"'
        + message
        + b'","request_id":"'
        + rid.encode()
        + b'","details":null}}'
    )
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"x-request-id", rid.encode()), *SECURITY_HEADERS],
        }
    )
    await send({"type": "http.response.body", "body": body})
