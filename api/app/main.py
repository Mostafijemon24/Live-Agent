"""FastAPI application factory."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.deps import verify_csrf
from app.core.errors import install_error_handlers
from app.core.middleware import RequestContextMiddleware
from app.routers import auth, workspace


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    docs = not settings.is_production
    app = FastAPI(
        title="Steward API",
        version="0.2.0",
        description="Phase 2 foundation. The AI planning/execution engine is not installed (Phase 3).",
        openapi_url="/api/v1/openapi.json" if docs else None,
        docs_url="/api/v1/docs" if docs else None,
        redoc_url=None,
    )
    install_error_handlers(app)

    v1 = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_csrf)])
    v1.include_router(auth.router)
    v1.include_router(workspace.router)
    app.include_router(v1)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}

    app.add_middleware(
        RequestContextMiddleware, max_body_bytes=settings.request_max_body_bytes, hsts=settings.is_production
    )
    return app


app = create_app()
