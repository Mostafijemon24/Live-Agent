"""Redaction of secrets and personal data before text leaves the workspace or is stored as
model-visible output. Pattern based: it reduces accidental exposure, it is not a guarantee
that every secret is found (documented in SECURITY_AND_PRIVACY.md)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("api_key", re.compile(r"\b(?:sk|pk|rk)-(?:proj-|live-|test-)?[A-Za-z0-9_-]{16,}\b")),
    ("api_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}\b")),
    ("aws_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("google_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}")),
    (
        "credential",
        re.compile(
            r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|token)\s*[:=]\s*[^\s\"'`,;&<>]+"
        ),
    ),
    ("db_url", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@]+:[^\s@/]+@[^\s/]+")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("card", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("phone", re.compile(r"(?<![\w.])\+?\d{1,3}[ .-]?\(?\d{2,4}\)?[ .-]?\d{3,4}[ .-]?\d{3,4}(?![\w.])")),
]


@dataclass(frozen=True)
class Redacted:
    text: str
    count: int
    kinds: tuple[str, ...]


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def redact(text: str, *, keep_emails: bool = False) -> Redacted:
    count = 0
    kinds: list[str] = []
    out = text
    for kind, pat in _PATTERNS:
        if kind == "email" and keep_emails:
            continue

        def _sub(m: re.Match[str], kind: str = kind) -> str:
            nonlocal count
            if kind == "card":
                digits = re.sub(r"\D", "", m.group(0))
                if not (13 <= len(digits) <= 19 and _luhn_ok(digits)):
                    return m.group(0)
            if kind == "credential":
                count += 1
                kinds.append(kind)
                return f"{m.group(1)}=[REDACTED]"
            count += 1
            kinds.append(kind)
            return f"[REDACTED:{kind}]"

        out = pat.sub(_sub, out)
    return Redacted(out, count, tuple(dict.fromkeys(kinds)))
