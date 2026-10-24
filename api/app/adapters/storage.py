"""Private local filesystem storage.

- Files live under STORAGE_DIR, which must be outside any web root and is never served statically.
- Keys are `<workspace uuid>/<random uuid>`; the client's filename is never used in a path.
- Size limit is enforced while streaming, so an oversized upload never fully lands on disk.
- Writes go to a temporary file and are renamed into place only when complete.
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

from app.core.errors import ApiError
from app.ports import StoredObject

_KEY_RE = re.compile(r"^[0-9a-f-]{36}/[0-9a-f]{32}$")
CHUNK = 1024 * 1024


class LocalPrivateFileStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.root / ".quarantine").mkdir(exist_ok=True, mode=0o700)

    def _path(self, key: str) -> Path:
        if not _KEY_RE.match(key):
            raise ValueError("invalid storage key")
        p = (self.root / key).resolve()
        if self.root not in p.parents:  # defence in depth against traversal
            raise ValueError("storage key escapes root")
        return p

    def save(self, workspace_id: uuid.UUID, stream: BinaryIO, max_bytes: int) -> StoredObject:
        key = f"{workspace_id}/{uuid.uuid4().hex}"
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = dest.with_name(dest.name + ".part")
        h = hashlib.sha256()
        size = 0
        head = b""
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as out:
                while True:
                    chunk = stream.read(CHUNK)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise ApiError(
                            413,
                            "file_too_large",
                            f"That file is larger than the {max_bytes // (1024 * 1024)} MB limit.",
                        )
                    if len(head) < 8192:
                        head += chunk[: 8192 - len(head)]
                    h.update(chunk)
                    out.write(chunk)
            if size == 0:
                raise ApiError(422, "file_empty", "That file is empty.")
            os.replace(tmp, dest)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return StoredObject(key=key, size_bytes=size, sha256=h.hexdigest(), head=head)

    def open(self, key: str) -> Iterator[bytes]:
        p = self._path(key)
        with p.open("rb") as f:
            while chunk := f.read(CHUNK):
                yield chunk

    def exists(self, key: str) -> bool:
        try:
            return self._path(key).is_file()
        except ValueError:
            return False

    def quarantine(self, key: str) -> None:
        p = self._path(key)
        target = self.root / ".quarantine" / key.replace("/", "_")
        os.replace(p, target)

    def discard_incomplete(self, key: str) -> None:
        """Remove a just-written object whose database record failed to commit (never user data)."""
        p = self._path(key)
        p.unlink(missing_ok=True)


# ---------------------------------------------------------------- type detection
# Allowlist: detected by content ("magic bytes"), not by the browser's Content-Type or file extension.
ALLOWED: dict[str, tuple[str, str]] = {
    # label: (canonical content type, extensions)
    "PDF": ("application/pdf", ".pdf"),
    "PNG": ("image/png", ".png"),
    "JPG": ("image/jpeg", ".jpg .jpeg"),
    "DOCX": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    "XLSX": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "CSV": ("text/csv", ".csv"),
    "TXT": ("text/plain", ".txt .log"),
    "MD": ("text/markdown", ".md"),
    "JSON": ("application/json", ".json"),
}


def _is_text(head: bytes) -> bool:
    if b"\x00" in head:
        return False
    try:
        head.decode("utf-8")
        return True
    except UnicodeDecodeError as e:
        # A multi-byte character may be cut at the end of the sniffed prefix.
        return e.start >= len(head) - 4


def detect_type(head: bytes, filename: str) -> tuple[str, str] | None:
    """Return (label, content_type) or None when the content is not on the allowlist."""
    ext = os.path.splitext(filename.lower())[1]
    if head.startswith(b"%PDF-"):
        return "PDF", ALLOWED["PDF"][0]
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG", ALLOWED["PNG"][0]
    if head.startswith(b"\xff\xd8\xff"):
        return "JPG", ALLOWED["JPG"][0]
    if head.startswith(b"PK\x03\x04"):
        # Office Open XML documents are zip containers; accept only when the extension says which one.
        # Arbitrary archives (.zip) are not accepted in Phase 2 because nothing can inspect them yet.
        if ext == ".docx" and b"word/" in head:
            return "DOCX", ALLOWED["DOCX"][0]
        if ext == ".xlsx" and b"xl/" in head:
            return "XLSX", ALLOWED["XLSX"][0]
        if ext in (".docx", ".xlsx") and b"[Content_Types].xml" in head:
            label = "DOCX" if ext == ".docx" else "XLSX"
            return label, ALLOWED[label][0]
        return None
    if head[:2] == b"MZ" or head[:4] == b"\x7fELF" or head[:2] == b"#!":
        return None  # executables and scripts are never accepted
    if _is_text(head):
        lowered = head[:512].lower()
        if b"<script" in lowered or b"<html" in lowered or b"<!doctype html" in lowered or b"<svg" in lowered:
            return None  # active content
        if ext == ".csv":
            return "CSV", ALLOWED["CSV"][0]
        if ext == ".md":
            return "MD", ALLOWED["MD"][0]
        if ext == ".json":
            return "JSON", ALLOWED["JSON"][0]
        if ext in (".txt", ".log", ""):
            return "TXT", ALLOWED["TXT"][0]
    return None


def safe_display_name(name: str) -> str:
    """A display-only version of the client filename (never used as a path)."""
    base = name.replace("\\", "/").split("/")[-1]
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip().strip(".")
    return (base or "unnamed")[:200]
