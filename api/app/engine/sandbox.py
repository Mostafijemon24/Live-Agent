"""Isolated execution of short Python programs for the `code.run_python` tool.

Runs only in the tools worker, never in the API process. Each run gets:
- new user, network, mount and PID namespaces (`unshare -r -n -m -p -f --mount-proc`):
  no network interfaces except a down loopback, no view of other processes, a fresh /proc;
- a read-only root filesystem, a private size-limited /tmp, and empty tmpfs mounts over the
  application directory, file storage, mail outbox, home directories and secret mounts;
- an empty environment (no database URLs, API keys or tokens), Python in isolated mode (-I -S);
- resource limits: CPU time, address space, file size, open files, no core dumps; a wall-clock
  timeout that kills the whole process group; capped output.

If namespaces are unavailable (for example Docker's default seccomp profile blocks them) the
tool reports itself unavailable and nothing runs: it fails closed. This is defence in depth for
small programs, not a substitute for a VM-grade sandbox (gVisor/Firecracker) for hostile code.
"""

from __future__ import annotations

import contextlib
import os
import resource
import shlex
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import Settings, get_settings

PROBE_FAILED_EXIT = 97


@dataclass(frozen=True)
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool
    duration_ms: int


class SandboxUnavailable(Exception):
    pass


def _interpreter() -> str:
    base = getattr(sys, "_base_executable", None) or sys.executable
    return os.path.realpath(base)


def _hidden_paths(settings: Settings) -> list[str]:
    python_prefix = Path(_interpreter()).parent.resolve()
    candidates = [
        settings.storage_dir,
        settings.mail_outbox_dir,
        Path.cwd(),
        Path(__file__).resolve().parents[2],  # the API source tree (contains .env in development)
        Path("/home"),
        Path("/root"),
        Path("/run/secrets"),
        Path("/var/lib/postgresql"),
        Path("/var/run/postgresql"),
    ]
    out: list[str] = []
    for c in candidates:
        p = Path(c).resolve()
        if not p.exists() or not p.is_dir():
            continue
        if p == python_prefix or p in python_prefix.parents:
            continue  # never hide the interpreter itself
        s = str(p)
        if s not in out and s != "/":
            out.append(s)
    return out


def _script(settings: Settings) -> str:
    hide = " ".join(shlex.quote(p) for p in _hidden_paths(settings))
    return (
        "mount --bind / / 2>/dev/null; mount -o remount,bind,ro / 2>/dev/null; "
        f'for p in {hide}; do mount -t tmpfs -o size=1m,mode=700 none "$p" || exit {PROBE_FAILED_EXIT}; done; '
        f"mount -t tmpfs -o size=16m,mode=1777 none /tmp || exit {PROBE_FAILED_EXIT}; "
        f"if ( : > /.steward_probe ) 2>/dev/null; then echo 'sandbox: root filesystem is writable' >&2; exit {PROBE_FAILED_EXIT}; fi; "
        f"cd /tmp && exec {shlex.quote(_interpreter())} -I -S -"
    )


def _limits(settings: Settings) -> None:  # runs in the child before exec
    cpu = int(settings.sandbox_timeout_seconds) + 1
    mem = settings.sandbox_memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _command() -> list[str] | None:
    unshare = shutil.which("unshare")
    if not unshare:
        return None
    return [unshare, "-r", "-n", "-m", "-p", "-f", "--mount-proc", "--propagation", "private", "sh", "-c"]


@lru_cache(maxsize=1)
def isolation_status() -> tuple[bool, str]:
    """Whether the sandbox can run here. Cached per process."""
    settings = get_settings()
    if not settings.sandbox_enabled:
        return False, "Code execution is disabled by the administrator (SANDBOX_ENABLED=false)."
    cmd = _command()
    if cmd is None:
        return False, "The sandbox needs util-linux 'unshare', which is not installed on the tools worker."
    try:
        r = _run(
            settings,
            "import socket\ntry:\n socket.create_connection(('1.1.1.1', 53), 1)\n print('net')\nexcept OSError:\n print('nonet')\n",
        )
    except SandboxUnavailable as e:
        return False, str(e)
    if r.exit_code != 0 or r.stdout.strip() != "nonet":
        return False, "The sandbox could not be verified (network isolation check failed), so code execution is off."
    return True, "Isolated: no network, read-only system files, private /tmp, CPU/memory/time limits."


def _run(settings: Settings, code: str) -> SandboxResult:
    import time

    cmd = _command()
    if cmd is None:
        raise SandboxUnavailable("The sandbox is not installed on this worker.")
    started = time.monotonic()
    try:
        proc = subprocess.Popen(  # noqa: S603 - fixed argv; the program text goes to stdin, not a shell
            [*cmd, _script(settings)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"},  # noqa: S108 - private tmpfs inside the sandbox namespace
            cwd="/",
            close_fds=True,
            start_new_session=True,
            preexec_fn=lambda: _limits(settings),
        )
    except OSError as e:
        raise SandboxUnavailable(f"The sandbox could not start ({type(e).__name__}).") from None
    timed_out = False
    try:
        out, err = proc.communicate(code.encode(), timeout=settings.sandbox_timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        out, err = proc.communicate()
    if proc.returncode == PROBE_FAILED_EXIT and b"sandbox:" in err:
        raise SandboxUnavailable("The sandbox could not make the system read-only, so code execution is off.")
    if proc.returncode != 0 and b"unshare:" in err[:200]:
        raise SandboxUnavailable("Linux namespaces are not available on this worker, so code execution is off.")
    cap = settings.sandbox_max_output_bytes
    truncated = len(out) > cap or len(err) > cap
    return SandboxResult(
        exit_code=proc.returncode if not timed_out else -9,
        stdout=out[:cap].decode("utf-8", errors="replace"),
        stderr=err[:cap].decode("utf-8", errors="replace"),
        timed_out=timed_out,
        truncated=truncated,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


def run_python(code: str, settings: Settings | None = None) -> SandboxResult:
    s = settings or get_settings()
    ok, reason = isolation_status()
    if not ok:
        raise SandboxUnavailable(reason)
    return _run(s, code)
