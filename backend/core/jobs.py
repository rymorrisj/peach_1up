"""In-memory background-job registry — the entry point for work that outlives
the request that started it (large upload finalization, large library scans) and
needs to surface progress in the nav-bell notification centre.

In-memory only (lost on restart), matching install_registry / process_registry /
rate_limit — the goal is live progress for the current session, not a durable
history. Thread-safe: background tasks mutate jobs from a worker thread while the
`GET /api/v1/jobs` poll reads them from the event loop.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Literal

JobKind = Literal["upload", "scan"]
JobStatus = Literal["processing", "done", "error"]

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}

# Finished (done/error) jobs linger this long so the UI can show the final state
# and the user can open/dismiss it, then they're swept to bound memory.
_RETAIN_SECONDS = 3600.0


def create(kind: JobKind, message: str = "") -> str:
    """Register a new processing job and return its id."""
    job_id = uuid.uuid4().hex
    now = time.time()
    with _lock:
        _sweep_locked(now)
        _jobs[job_id] = {
            "id": job_id,
            "kind": kind,
            "status": "processing",
            "progress": 0.0,
            "message": message,
            "result": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }
    return job_id


def update(job_id: str, *, progress: float | None = None, message: str | None = None) -> None:
    """Update progress (clamped 0..1) and/or the human-readable message. No-op if
    the job was already swept."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        if progress is not None:
            job["progress"] = max(0.0, min(1.0, progress))
        if message is not None:
            job["message"] = message
        job["updated_at"] = time.time()


def complete(job_id: str, *, result: Any = None, message: str | None = None) -> None:
    _finish(job_id, "done", result=result, message=message)


def fail(job_id: str, error: str) -> None:
    _finish(job_id, "error", error=error, message=error)


def _finish(job_id: str, status: JobStatus, *, result: Any = None,
            error: str | None = None, message: str | None = None) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job["status"] = status
        if status == "done":
            job["progress"] = 1.0
        job["result"] = result
        job["error"] = error
        if message is not None:
            job["message"] = message
        job["updated_at"] = time.time()


def get(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def list_recent() -> list[dict[str, Any]]:
    """Active jobs plus recently-finished ones, oldest first."""
    now = time.time()
    with _lock:
        _sweep_locked(now)
        return [dict(j) for j in sorted(_jobs.values(), key=lambda j: j["created_at"])]


def _sweep_locked(now: float) -> None:
    stale = [
        jid
        for jid, j in _jobs.items()
        if j["status"] != "processing" and now - j["updated_at"] > _RETAIN_SECONDS
    ]
    for jid in stale:
        _jobs.pop(jid, None)
