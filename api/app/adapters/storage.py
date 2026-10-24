"""Private local filesystem storage.

- Files live under STORAGE_DIR, which must be outside any web root and is never served statically.
- Keys are `<workspace uuid>/<random uuid>`; the client's filename is never used in a path.
- Size limit is enforced while streaming, so an oversized upload never fully lands on disk.
- Writes go to a temporary file and are renamed into place only when complete.
"""

from __future__ import annotations

import codecs
import hashlib
import os
import re
import unicodedata
import uuid
import zipfile
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

    def local_path(self, key: str) -> Path:
        """Filesystem path for server-side inspection only (never exposed)."""
        return self._path(key)

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


_EXTENSIONS = {label: tuple(exts.split()) for label, (_ct, exts) in ALLOWED.items()}
_EXTENSIONS["TXT"] = (".txt", ".log")

# Markers of content a browser or OS could execute/render actively. Checked across the WHOLE file.
_ACTIVE_MARKERS = (
    b"<script",
    b"<html",
    b"<!doctype html",
    b"<svg",
    b"<iframe",
    b"<object",
    b"<embed",
    b"<form",
    b"<meta",
    b"<link",
    b"<base",
    b"javascript:",
    b"vbscript:",
    b"onerror=",
    b"onload=",
)
_DANGEROUS_ZIP_ENTRY = re.compile(
    r"(\.(exe|dll|bat|cmd|com|scr|msi|ps1|vbs|vbe|js|jse|wsf|wsh|hta|jar|sh|lnk|app)$)|vbaproject|activex|embeddings/.*\.bin$",
    re.I,
)
MAX_ZIP_ENTRIES = 2000
MAX_ZIP_UNCOMPRESSED = 200 * 1024 * 1024


def _ext_ok(label: str, ext: str) -> bool:
    return ext in _EXTENSIONS.get(label, ())


def detect_type(head: bytes, filename: str) -> tuple[str, str] | None:
    """Return (label, content_type) or None. The extension must match the detected content,
    so a file is always served back with an extension that matches what it really is."""
    ext = os.path.splitext(filename.lower())[1]
    if head.startswith(b"%PDF-"):
        label = "PDF"
    elif head.startswith(b"\x89PNG\r\n\x1a\n"):
        label = "PNG"
    elif head.startswith(b"\xff\xd8\xff"):
        label = "JPG"
    elif head.startswith(b"PK\x03\x04"):
        # Office Open XML containers only; the full structure is checked by validate_stored().
        # Arbitrary archives (.zip) are not accepted in Phase 2 because nothing can inspect them yet.
        label = {".docx": "DOCX", ".xlsx": "XLSX"}.get(ext, "")
    elif head[:2] == b"MZ" or head[:4] == b"\x7fELF" or head[:2] == b"#!":
        return None  # executables and scripts are never accepted
    elif _is_text(head):
        label = {".csv": "CSV", ".md": "MD", ".json": "JSON", ".txt": "TXT", ".log": "TXT"}.get(ext, "")
    else:
        return None
    if not label or not _ext_ok(label, ext):
        return None
    return label, ALLOWED[label][0]


def validate_stored(path: Path, label: str) -> str | None:
    """Full-content checks after the upload landed in private storage. Returns a rejection reason or None."""
    if label in ("DOCX", "XLSX"):
        required = "word/document.xml" if label == "DOCX" else "xl/workbook.xml"
        try:
            with zipfile.ZipFile(path) as zf:
                infos = zf.infolist()
                if len(infos) > MAX_ZIP_ENTRIES:
                    return "too many entries"
                if sum(i.file_size for i in infos) > MAX_ZIP_UNCOMPRESSED:
                    return "expands too much"
                names = {i.filename for i in infos}
                if "[Content_Types].xml" not in names or required not in names:
                    return "not a valid Office document"
                for n in names:
                    if n.startswith("/") or ".." in n.split("/") or _DANGEROUS_ZIP_ENTRY.search(n):
                        return "contains executable content or macros"
        except (zipfile.BadZipFile, OSError):
            return "not a valid Office document"
        return None
    if label in ("CSV", "TXT", "MD", "JSON"):
        overlap = max(len(m) for m in _ACTIVE_MARKERS)
        tail = b""
        decoder = codecs.getincrementaldecoder("utf-8")()
        with path.open("rb") as f:
            while chunk := f.read(CHUNK):
                if b"\x00" in chunk:
                    return "not a text file"
                try:
                    decoder.decode(chunk)
                except UnicodeDecodeError:
                    return "not valid UTF-8 text"
                window = (tail + chunk).lower()
                if any(m in window for m in _ACTIVE_MARKERS):
                    return "contains active web content"
                tail = window[-overlap:]
        try:
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            return "not valid UTF-8 text"
    return None


def strip_invisible(text: str) -> str:
    """Remove control, format (bidi overrides, zero-width) and line/paragraph-separator characters,
    which can disguise a name (e.g. 'invoice\u202efdp.hta' renders as 'invoiceath.pdf')."""
    return "".join(ch for ch in text if unicodedata.category(ch) not in ("Cc", "Cf", "Zl", "Zp", "Cs", "Co", "Cn"))


def safe_display_name(name: str) -> str:
    """A display-only version of the client filename (never used as a path)."""
    base = name.replace("\\", "/").split("/")[-1]
    base = strip_invisible(base).strip().strip(".")
    return (base or "unnamed")[:200]
