"""Auth and current-user routes."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from sqlalchemy.orm import Session

from app import schemas as S
from app.core import ratelimit as RL
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import Context, client_ip, csrf_cookie_name, get_context, request_id, session_cookie_name
from app.core.security import new_token
from app.models import User, Workspace
from app.services import workspace as W
from app.services.auth import AuthService, deliver_mail

router = APIRouter()


def me_out(user: User, ws: Workspace, role: str) -> S.MeOut:
    return S.MeOut(
        user=S.UserOut(
            id=user.id,
            name=user.name,
            email=user.email,
            email_verified=user.email_verified_at is not None,
            onboarding_completed=user.onboarding_completed_at is not None,
            created_at=user.created_at,
        ),
        workspace=S.WorkspaceSummaryOut(id=ws.id, name=ws.name, role=role),
    )


def _svc(request: Request, db: Session) -> AuthService:
    return AuthService(db, client_ip(request), request_id(request))


@contextmanager
def _constant_time(svc: AuthService, background: BackgroundTasks) -> Iterator[None]:
    """Account-existence-sensitive endpoints: queue mail for after the response and pad every
    outcome to the same minimum duration, so neither timing nor mail failures reveal anything."""
    started = time.monotonic()
    try:
        yield
        if svc.pending_mail:
            background.add_task(deliver_mail, svc.settings, list(svc.pending_mail))
    finally:
        remaining = get_settings().auth_response_floor_ms / 1000 - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(remaining)


def _set_session_cookie(response: Response, raw: str) -> None:
    s = get_settings()
    response.set_cookie(
        session_cookie_name(s),
        raw,
        max_age=s.session_absolute_days * 86400,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(session_cookie_name(s), path="/", secure=s.cookie_secure, httponly=True, samesite="lax")


@router.get("/auth/csrf", response_model=S.CsrfOut)
def csrf(request: Request, response: Response) -> S.CsrfOut:
    s = get_settings()
    name = csrf_cookie_name(s)
    token = request.cookies.get(name) or new_token()
    # Readable by the page (double-submit), never authorises anything on its own.
    response.set_cookie(
        name, token, httponly=False, secure=s.cookie_secure, samesite="lax", path="/", max_age=86400 * 7
    )
    return S.CsrfOut(csrf_token=token)


@router.post("/auth/register", response_model=S.Message, status_code=202)
def register(
    body: S.RegisterIn, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
) -> S.Message:
    RL.hit(RL.REGISTER_IP, client_ip(request) or "unknown")
    RL.hit(RL.REGISTER_EMAIL, str(body.email))
    svc = _svc(request, db)
    with _constant_time(svc, background):
        msg = svc.register(body.name, str(body.email), body.password)
    return S.Message(message=msg)


@router.post("/auth/login", response_model=S.MeOut)
def login(body: S.LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> S.MeOut:
    RL.hit(RL.LOGIN_IP, client_ip(request) or "unknown")
    RL.hit(RL.LOGIN_EMAIL, str(body.email))
    svc = _svc(request, db)
    raw, user, ws, membership = svc.login(str(body.email), body.password, request.headers.get("user-agent"))
    # Never keep two sessions alive in one browser: revoke the one this browser presented, if any.
    previous = request.cookies.get(session_cookie_name(get_settings()))
    if previous and len(previous) <= 100:
        svc.revoke_presented_session(previous)
    _set_session_cookie(response, raw)
    return me_out(user, ws, membership.role)


@router.post("/auth/logout", status_code=204)
def logout(response: Response, ctx: Context = Depends(get_context)) -> Response:
    AuthService(ctx.db, ctx.ip, ctx.request_id).logout(ctx.session, ctx.user, ctx.workspace.id)
    _clear_session_cookie(response)
    response.status_code = 204
    return response


@router.post("/auth/verify-email", response_model=S.Message)
def verify_email(body: S.TokenIn, request: Request, db: Session = Depends(get_db)) -> S.Message:
    RL.hit(RL.VERIFY_IP, client_ip(request) or "unknown")
    _svc(request, db).verify_email(body.token)
    return S.Message(message="Your email address is verified. You can sign in now.")


@router.post("/auth/resend-verification", response_model=S.Message, status_code=202)
def resend(body: S.EmailIn, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)) -> S.Message:
    RL.hit(RL.RESEND_IP, client_ip(request) or "unknown")
    RL.hit(RL.RESEND_EMAIL, str(body.email))
    svc = _svc(request, db)
    with _constant_time(svc, background):
        msg = svc.resend_verification(str(body.email))
    return S.Message(message=msg)


@router.post("/auth/forgot-password", response_model=S.Message, status_code=202)
def forgot(body: S.EmailIn, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)) -> S.Message:
    RL.hit(RL.FORGOT_IP, client_ip(request) or "unknown")
    RL.hit(RL.FORGOT_EMAIL, str(body.email))
    svc = _svc(request, db)
    with _constant_time(svc, background):
        msg = svc.forgot_password(str(body.email))
    return S.Message(message=msg)


@router.post("/auth/reset-password", response_model=S.Message)
def reset(
    body: S.ResetPasswordIn,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> S.Message:
    RL.hit(RL.RESET_IP, client_ip(request) or "unknown")
    svc = _svc(request, db)
    svc.reset_password(body.token, body.password)
    background.add_task(deliver_mail, svc.settings, list(svc.pending_mail))
    _clear_session_cookie(response)
    return S.Message(
        message="Your password was changed and every session was signed out. Sign in with your new password."
    )


@router.get("/me", response_model=S.MeOut)
def me(ctx: Context = Depends(get_context)) -> S.MeOut:
    return me_out(ctx.user, ctx.workspace, ctx.role.value)


@router.post("/me/onboarding", response_model=S.MeOut)
def onboarding(body: S.OnboardingIn, ctx: Context = Depends(get_context)) -> S.MeOut:
    W.complete_onboarding(ctx, body)
    return me_out(ctx.user, ctx.workspace, ctx.role.value)
