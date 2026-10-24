"""Auth and current-user routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app import schemas as S
from app.core import ratelimit as RL
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import CSRF_COOKIE, Context, client_ip, get_context, request_id, session_cookie_name
from app.core.security import new_token
from app.models import User, Workspace
from app.services import workspace as W
from app.services.auth import AuthService

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
    token = request.cookies.get(CSRF_COOKIE) or new_token()
    s = get_settings()
    # Readable by the page (double-submit), never authorises anything on its own.
    response.set_cookie(
        CSRF_COOKIE, token, httponly=False, secure=s.cookie_secure, samesite="lax", path="/", max_age=86400 * 7
    )
    return S.CsrfOut(csrf_token=token)


@router.post("/auth/register", response_model=S.Message, status_code=202)
def register(body: S.RegisterIn, request: Request, db: Session = Depends(get_db)) -> S.Message:
    RL.hit(RL.REGISTER_IP, client_ip(request) or "unknown")
    return S.Message(message=_svc(request, db).register(body.name, str(body.email), body.password))


@router.post("/auth/login", response_model=S.MeOut)
def login(body: S.LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> S.MeOut:
    RL.hit(RL.LOGIN_IP, client_ip(request) or "unknown")
    RL.hit(RL.LOGIN_EMAIL, str(body.email))
    raw, user, ws, membership = _svc(request, db).login(
        str(body.email), body.password, request.headers.get("user-agent")
    )
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
def resend(body: S.EmailIn, request: Request, db: Session = Depends(get_db)) -> S.Message:
    RL.hit(RL.RESEND_IP, client_ip(request) or "unknown")
    RL.hit(RL.RESEND_EMAIL, str(body.email))
    return S.Message(message=_svc(request, db).resend_verification(str(body.email)))


@router.post("/auth/forgot-password", response_model=S.Message, status_code=202)
def forgot(body: S.EmailIn, request: Request, db: Session = Depends(get_db)) -> S.Message:
    RL.hit(RL.FORGOT_IP, client_ip(request) or "unknown")
    RL.hit(RL.FORGOT_EMAIL, str(body.email))
    return S.Message(message=_svc(request, db).forgot_password(str(body.email)))


@router.post("/auth/reset-password", response_model=S.Message)
def reset(body: S.ResetPasswordIn, request: Request, response: Response, db: Session = Depends(get_db)) -> S.Message:
    RL.hit(RL.RESET_IP, client_ip(request) or "unknown")
    _svc(request, db).reset_password(body.token, body.password)
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
