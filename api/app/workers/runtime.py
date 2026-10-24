"""Worker processes.

    python -m app.workers orchestrator   # plans tasks, advances plans (WORKER_DATABASE_URL)
    python -m app.workers tools          # runs tools, sandbox, integration checks (WORKER_DATABASE_URL)
    python -m app.workers deletion       # executes approved deletions (DELETION_DATABASE_URL)
    python -m app.workers scheduler      # automations, purges, stale-job recovery (WORKER_DATABASE_URL)

Each process connects with its own least-privileged database role and never with the API or
owner role. Jobs run with a heartbeat; SIGTERM/SIGINT stop claiming new work and let running
jobs finish within WORKER_SHUTDOWN_GRACE_SECONDS.
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import create_engine, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import utcnow
from app.domain.enums import JobQueue
from app.engine import deletion, integrations, orchestrator, runner, scheduler
from app.engine import queue as Q
from app.engine.orchestrator import RetryLater
from app.models import WorkerHeartbeat

log = logging.getLogger("steward.worker")
VERSION = "0.3.0"

Handler = Callable[[Session, Q.ClaimedJob], None]


def make_factory(url: str) -> sessionmaker[Session]:
    eng = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=4,
        max_overflow=4,
        connect_args={"options": "-c statement_timeout=30000 -c timezone=UTC"},
    )
    return sessionmaker(bind=eng, expire_on_commit=False, autoflush=False)


def handlers_for(kind: str, settings: Settings, factory: sessionmaker[Session]) -> dict[str, Handler]:
    if kind == "orchestrator":
        return {
            "task.plan": lambda db, j: orchestrator.handle_plan(db, j, settings),
            "task.execute": lambda db, j: orchestrator.handle_execute(db, j, settings),
        }
    if kind == "tools":
        return {
            "tool.run": lambda db, j: runner.handle_tool_run(db, j, settings, factory),
            "integration.verify": lambda db, j: integrations.handle_verify(db, j, settings),
        }
    if kind == "deletion":
        return {
            "deletion.execute": lambda db, j: deletion.handle_delete(db, j, settings),
            "deletion.restore": lambda db, j: deletion.handle_restore(db, j, settings),
            "deletion.purge": lambda db, j: deletion.handle_purge(db, j, settings),
        }
    raise ValueError(f"unknown worker kind {kind}")


def dead_handler(kind: str, settings: Settings) -> Callable[[Session, Q.ClaimedJob, str], None]:
    if kind == "orchestrator":
        return orchestrator.on_dead
    if kind == "tools":
        return lambda db, j, e: runner.on_dead(db, j, e, settings)
    return lambda db, j, e: None


class Worker:
    def __init__(self, kind: str, factory: sessionmaker[Session], settings: Settings | None = None) -> None:
        self.kind = kind
        self.factory = factory
        self.settings = settings or get_settings()
        self.queue = JobQueue(kind) if kind in ("orchestrator", "tools", "deletion") else None
        self.handlers = handlers_for(kind, self.settings, factory) if self.queue else {}
        self.on_dead = dead_handler(kind, self.settings)
        self.id = f"{kind}-{socket.gethostname()[:40]}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.stop = threading.Event()
        self.done = 0
        self.failed = 0

    # ---------------- liveness row
    def _register(self) -> None:
        with self.factory() as db:
            db.execute(
                insert(WorkerHeartbeat).values(
                    id=self.id, kind=self.kind, hostname=socket.gethostname()[:120], pid=os.getpid(), version=VERSION
                )
            )
            db.commit()

    def _beat(self, stopped: bool = False) -> None:
        with self.factory() as db:
            values: dict[str, Any] = {"heartbeat_at": utcnow(), "jobs_done": self.done, "jobs_failed": self.failed}
            if stopped:
                values["stopped_at"] = utcnow()
            db.execute(update(WorkerHeartbeat).where(WorkerHeartbeat.id == self.id).values(**values))
            db.commit()

    # ---------------- one job
    def process(self, job: Q.ClaimedJob) -> str:
        handler = self.handlers.get(job.kind)
        stop_beat = threading.Event()

        def beat() -> None:
            interval = max(1.0, self.settings.job_lease_seconds / 4)
            while not stop_beat.wait(interval):
                with self.factory() as hb:
                    if not Q.heartbeat(hb, job.id, self.id):
                        return

        hb_thread = threading.Thread(target=beat, daemon=True)
        hb_thread.start()
        outcome = "succeeded"
        try:
            with self.factory() as db:
                try:
                    if handler is None:
                        raise LookupError(f"no handler for job kind {job.kind!r} on the {self.kind} queue")
                    handler(db, job)
                    Q.complete(db, job.id)
                    db.commit()
                except RetryLater as e:
                    db.rollback()
                    outcome = self._failed(job, f"retry: {e}", retryable=True)
                except LookupError as e:
                    db.rollback()
                    outcome = self._failed(job, str(e), retryable=False)
                except Exception as e:
                    db.rollback()
                    log.exception("job %s (%s) failed", job.id, job.kind)
                    outcome = self._failed(job, f"{type(e).__name__}: {str(e)[:300]}", retryable=True)
        finally:
            stop_beat.set()
            hb_thread.join(timeout=2)
        if outcome == "succeeded":
            self.done += 1
        else:
            self.failed += 1
        return outcome

    def _failed(self, job: Q.ClaimedJob, error: str, retryable: bool) -> str:
        with self.factory() as db:
            status = Q.fail(db, job, error, retryable=retryable, settings=self.settings)
            if status in ("dead", "failed"):
                try:
                    self.on_dead(db, job, error)
                except Exception:
                    log.exception("dead-letter handler failed for job %s", job.id)
                    db.rollback()
                    Q.fail(db, job, error, retryable=False, settings=self.settings)
            db.commit()
            return status

    def run_once(self) -> bool:
        assert self.queue is not None
        with self.factory() as db:
            job = Q.claim(db, self.queue, self.id, self.settings)
        if job is None:
            return False
        self.process(job)
        return True

    # ---------------- loops
    def run_forever(self) -> None:
        self._register()
        signal.signal(signal.SIGTERM, lambda *_: self.stop.set())
        signal.signal(signal.SIGINT, lambda *_: self.stop.set())
        log.info("worker %s started", self.id)
        last_beat = 0.0
        try:
            if self.kind == "scheduler":
                self._scheduler_loop()
            else:
                self._job_loop()
        finally:
            self._beat(stopped=True)
            log.info("worker %s stopped (done=%s failed=%s)", self.id, self.done, self.failed)
        del last_beat

    def _job_loop(self) -> None:
        threads: list[threading.Thread] = []
        sem = threading.Semaphore(max(1, self.settings.worker_concurrency))
        last_beat = 0.0
        while not self.stop.is_set():
            if time.monotonic() - last_beat > 10:
                self._beat()
                last_beat = time.monotonic()
            if not sem.acquire(timeout=self.settings.worker_poll_seconds):
                continue
            try:
                with self.factory() as db:
                    assert self.queue is not None
                    job = Q.claim(db, self.queue, self.id, self.settings)
            except Exception:
                log.exception("claim failed")
                sem.release()
                self.stop.wait(5)
                continue
            if job is None:
                sem.release()
                self.stop.wait(self.settings.worker_poll_seconds)
                continue

            def work(j: Q.ClaimedJob = job) -> None:
                try:
                    self.process(j)
                finally:
                    sem.release()

            t = threading.Thread(target=work, name=f"job-{job.id}", daemon=True)
            t.start()
            threads = [x for x in threads if x.is_alive()] + [t]
        deadline = time.monotonic() + self.settings.worker_shutdown_grace_seconds
        for t in threads:
            t.join(timeout=max(0.0, deadline - time.monotonic()))
        # Jobs still running past the grace period keep status=running; their lease expires and
        # the scheduler re-queues them (bounded by max_attempts).

    def _scheduler_loop(self) -> None:
        while not self.stop.is_set():
            try:
                with self.factory() as db:
                    stats = scheduler.tick(db, self.settings)
                if any(stats.values()):
                    log.info("scheduler tick %s", stats)
                self.done += 1
                self._beat()
            except Exception:
                self.failed += 1
                log.exception("scheduler tick failed")
            self.stop.wait(15)


def main(kind: str) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    s = get_settings()
    url = s.deletion_database_url if kind == "deletion" else s.worker_database_url
    if url is None:
        env = "DELETION_DATABASE_URL" if kind == "deletion" else "WORKER_DATABASE_URL"
        raise SystemExit(f"{env} is not set. Workers never fall back to the API or owner database role.")
    Worker(kind, make_factory(url.get_secret_value()), s).run_forever()
