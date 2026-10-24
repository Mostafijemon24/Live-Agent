"""Integration framework.

Only integrations that genuinely work are marked connected. The first real one is WordPress
read-only via the site's public REST API: no credentials are requested or stored, the site's
domain must be on the workspace allowlist, and the connection is verified from the tools worker
(through the egress client) before it is marked connected.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import utcnow
from app.engine import queue as Q
from app.engine.egress import EgressBlocked, EgressClient, EgressFailed, workspace_policy
from app.engine.records import audit
from app.models import IntegrationConnection, Workspace

# key -> how it works. "operational" means a real adapter exists and is tested.
INTEGRATIONS: dict[str, dict[str, Any]] = {
    "wordpress": {"operational": True, "mode": "read-only (public REST API, no credentials)"},
    "notion": {"operational": False, "mode": "not built"},
    "cloud_storage": {"operational": False, "mode": "not built"},
    "email": {"operational": False, "mode": "not built"},
    "browser": {"operational": False, "mode": "not built (use the read-only page inspection tool)"},
    "ai_provider": {"operational": True, "mode": "configured by the server administrator (environment variables)"},
}


def handle_verify(db: Session, job: Q.ClaimedJob, settings: Settings) -> None:
    key = str(job.payload.get("key"))
    conn = db.execute(
        select(IntegrationConnection)
        .where(IntegrationConnection.workspace_id == job.workspace_id, IntegrationConnection.key == key)
        .with_for_update()
    ).scalar_one_or_none()
    if conn is None or key != "wordpress":
        return
    site = str((conn.config or {}).get("site_url") or "")
    ws = db.execute(select(Workspace).where(Workspace.id == job.workspace_id)).scalar_one()
    client = EgressClient(workspace_policy(ws.allowed_domains or [], settings), settings)
    error: str | None = None
    try:
        resp = client.get(site.rstrip("/") + "/wp-json/", headers={"Accept": "application/json"})
        if resp.status >= 400:
            error = f"The site returned HTTP {resp.status} for its REST API."
        else:
            data = json.loads(resp.body)
            if not isinstance(data, dict) or "wp/v2" not in (data.get("namespaces") or []):
                error = "This does not look like a WordPress site with the REST API enabled."
    except EgressBlocked as e:
        error = e.message
    except EgressFailed as e:
        error = e.message
    except ValueError:
        error = "The site's REST API did not return JSON."
    conn.status = "error" if error else "connected"
    conn.error_message = error
    conn.last_activity_at = utcnow()
    conn.updated_at = utcnow()
    audit(
        db,
        job.workspace_id,
        "integration.verified" if not error else "integration.verify_failed",
        "integration",
        f"WordPress {'connected (read-only)' if not error else 'connection failed: ' + error}",
        target_type="integration",
        target_id=key,
        job_id=job.id,
    )
