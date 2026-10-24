"""Canonical JSON and hashing used to bind approvals to exact operations."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_hex(value: Any) -> str:
    data = value if isinstance(value, bytes) else canonical_json(value).encode()
    return hashlib.sha256(data).hexdigest()


def args_hash(tool_id: str, args: dict[str, Any]) -> str:
    return sha256_hex({"tool": tool_id, "args": args})
