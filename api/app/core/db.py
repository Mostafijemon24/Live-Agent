"""Database engine and session handling."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def utcnow() -> datetime:
    return datetime.now(UTC)


_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _factory
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url.get_secret_value(),
            pool_pre_ping=True,
            # Per API process. Budget: processes x (pool + overflow) + workers <= Postgres max_connections.
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            # Fail fast under overload (→ 503 service_busy) instead of queueing requests for 30 s.
            pool_timeout=settings.db_pool_timeout_seconds,
            connect_args={"options": "-c statement_timeout=15000 -c timezone=UTC"},
        )
        _factory = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


def reset_engine() -> None:
    """Used by tests after changing settings."""
    global _engine, _factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _factory = None


def get_db() -> Iterator[Session]:
    get_engine()
    assert _factory is not None
    db = _factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _factory is not None
    return _factory
