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
JobStatus = Literal["processing", "cancelling", "done", "error", "cancelled"]

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}

# Cancellation flags, keyed by job_id. Kept out of the _jobs dict itself since
# threading.Event isn't JSON-serializable and job dicts are returned as-is by
# the /api/v1/jobs routes.
_cancel_events: dict[str, threading.Event] = {}

# Finished (done/error/cancelled) jobs linger this long so the UI can show the
# final state and the user can open/dismiss it, then they're swept to bound memory.
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
        _cancel_events[job_id] = threading.Event()
    return job_id


def request_cancel(job_id: str) -> dict[str, Any] | None:
    """Flag *job_id* for cooperative cancellation and mark it 'cancelling'.

    Returns the updated job dict, or None if the job doesn't exist or is no
    longer in flight (cancellation only applies to a 'processing' job — it is
    not retroactive against one that already finished).
    """
    with _lock:
        job = _jobs.get(job_id)
        if job is None or job["status"] != "processing":
            return None
        job["status"] = "cancelling"
        job["message"] = f"{job['message']} — cancelling…" if job["message"] else "Cancelling…"
        job["updated_at"] = time.time()
        result = dict(job)
    event = _cancel_events.get(job_id)
    if event is not None:
        event.set()
    return result


def cancel_requested(job_id: str) -> bool:
    """Cheap, non-blocking check a running job loop calls periodically."""
    event = _cancel_events.get(job_id)
    return event.is_set() if event is not None else False


def cancel(job_id: str, message: str | None = None) -> None:
    """Mark *job_id* as cancelled (terminal state). Called by the job's own
    loop once it has actually stopped work — mirrors complete()/fail()."""
    _finish(job_id, "cancelled", message=message)


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
        _cancel_events.pop(jid, None)
