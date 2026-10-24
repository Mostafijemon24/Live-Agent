"""Container healthcheck for workers: exit 0 if a worker on this host heart-beat recently."""

from __future__ import annotations

import socket
import sys

from sqlalchemy import create_engine, text

from app.core.config import get_settings


def main() -> int:
    s = get_settings()
    url = s.deletion_database_url or s.worker_database_url
    if url is None or not url.get_secret_value():
        return 1
    eng = create_engine(url.get_secret_value(), pool_pre_ping=True)
    try:
        with eng.connect() as c:
            ok = c.execute(
                text(
                    "SELECT 1 FROM workers WHERE hostname = :h AND stopped_at IS NULL "
                    "AND heartbeat_at > now() - interval '60 seconds' LIMIT 1"
                ),
                {"h": socket.gethostname()[:120]},
            ).first()
        return 0 if ok else 1
    except Exception:
        return 1
    finally:
        eng.dispose()


if __name__ == "__main__":
    sys.exit(main())
