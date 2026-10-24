"""Stable error envelope: {"error": {"code", "message", "request_id", "details"}}."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("steward.errors")


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers or {}


def not_found(what: str = "item") -> ApiError:
    # Same response whether the item does not exist or belongs to another workspace.
    return ApiError(404, "not_found", f"That {what} was not found in your workspace.")


def conflict(code: str, message: str) -> ApiError:
    return ApiError(409, code, message)


def _rid(request: Request) -> str:
    return str(getattr(request.state, "request_id", "-"))


def _body(request: Request, code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "request_id": _rid(request), "details": details}}


_FIELD_MESSAGES = {
    "missing": "This field is required.",
    "string_too_short": "This is too short.",
    "string_too_long": "This is too long.",
    "value_error": "This value is not valid.",
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            _body(request, exc.code, exc.message, exc.details), status_code=exc.status, headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = []
        for e in exc.errors():
            loc = [str(p) for p in e.get("loc", []) if p not in ("body", "query", "path")]
            msg = e.get("msg", "Invalid value")
            if e.get("type") in _FIELD_MESSAGES and e.get("type") != "value_error":
                msg = _FIELD_MESSAGES[e["type"]]
            elif msg.startswith("Value error, "):
                msg = msg.removeprefix("Value error, ")
            details.append({"field": ".".join(loc) or "body", "message": msg})
        return JSONResponse(_body(request, "validation_error", "Some fields need attention.", details), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed", 413: "payload_too_large"}.get(
            exc.status_code, "http_error"
        )
        msg = exc.detail if isinstance(exc.detail, str) else "Request failed."
        if exc.status_code == 404:
            msg = "Not found."
        return JSONResponse(_body(request, code, msg), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Never leak stack traces or internals to clients.
        log.exception("unhandled error request_id=%s", _rid(request))
        return JSONResponse(
            _body(request, "internal_error", "The server had a problem. Nothing was changed. Please try again."),
            status_code=500,
        )
