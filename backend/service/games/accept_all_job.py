"""Background job lifecycle for Accept All (backend/service/games/media_link.py
does the apply itself).

Reuses core.jobs, the registry the upload and scan jobs use: a route creates
the job, a FastAPI BackgroundTask runs it on its own DB session, and the
client polls for status. The job holds the apply locks from the route's
pre-checks until it ends, and releases them on done, failed, cancelled or
any unexpected exception.

Failures are reported as {code, message} naming the real reason. Messages
are built here from the failure's type and status, never from raw exception
text, so no URL or provider detail beyond a status code reaches a client.
"""

from __future__ import annotations

import errno
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import urlsplit

import httpx2
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.orm import Session

from backend.core import jobs
from backend.core.logger import get_logger
from backend.service.games import media_link
from backend.service.metadata_providers import ASSET_HOST_PROVIDER_LABELS
from backend.service.utils.asset_fetch import AssetFetchFailure

if TYPE_CHECKING:
    from backend.service.games.media_link import ApplyPlan

logger = get_logger(__name__)

JOB_KIND = "metadata_apply"
_WINDOWS_DISK_FULL = 112

_STATES = {
    "cancelling": "running",
    "done": "done",
    "error": "failed",
    "cancelled": "cancelled",
}


def start(plan: "ApplyPlan", background_tasks: BackgroundTasks) -> str:
    """Create the job for *plan* and schedule it, handing it the plan's
    locks. If that fails the locks are released here instead."""
    try:
        job_id = jobs.create(
            JOB_KIND,
            message="Applying fetched images",
            meta={"done": 0, "total": len(plan.assets), "label": None, "started": False, "error": None},
        )
        background_tasks.add_task(run_job, plan, job_id)
    except BaseException:
        plan.release()
        raise
    return job_id


def run_job(plan: "ApplyPlan", job_id: str) -> None:
    """BackgroundTask entry: own DB session, report to core.jobs, always
    release the plan's locks, never raise for an ordinary failure."""
    from backend.core.database import get_engine

    db: Optional[Session] = None
    try:
        db = Session(get_engine())
        jobs.update(job_id, meta={"started": True})
        bundle = media_link.run_apply(
            plan, db,
            progress=lambda done, total, label: jobs.update(
                job_id, progress=done / total if total else 0.0,
                meta={"done": done, "total": total, "label": label},
            ),
            should_cancel=lambda: jobs.cancel_requested(job_id),
        )
        jobs.complete(
            job_id,
            result={
                "media_item_bundle_id": bundle.id if bundle is not None else None,
                "item_count": len(bundle.items) if bundle is not None else 0,
            },
            message="Fetched images applied.",
        )
    except BaseException as exc:  # noqa: BLE001, the job must always reach a terminal state
        _record_failure(job_id, exc, _provider_label(plan))
        if not isinstance(exc, Exception):
            raise
    finally:
        plan.release()
        if db is not None:
            db.close()


def _record_failure(job_id: str, exc: BaseException, provider: str) -> None:
    if isinstance(exc, media_link.ApplyFailure) and exc.code == media_link.CANCELLED_CODE:
        jobs.cancel(job_id, message=exc.message)
        return
    code, message = classify_error(exc, provider)
    if code == "internal_error":
        logger.error("Accept All job %s failed unexpectedly", job_id, exc_info=exc)
    else:
        logger.info("Accept All job %s failed: %s", job_id, code)
    jobs.update(job_id, meta={"error": {"code": code, "message": message}})
    jobs.fail(job_id, message)


def _provider_label(plan: "ApplyPlan") -> str:
    host = (urlsplit(plan.assets[0].url).hostname or "").lower() if plan.assets else ""
    return ASSET_HOST_PROVIDER_LABELS.get(host, "The image")


def classify_error(exc: BaseException, provider: str) -> tuple[str, str]:
    """(code, message) naming the real reason *exc* stopped an apply.

    Codes: cancelled, provider_error, network_error, asset_rejected,
    time_budget_exceeded, disk_full, permission_error, storage_error,
    conflict, cover_rejected, game_not_found, apply_failed, internal_error.
    """
    if isinstance(exc, media_link.ApplyFailure):
        return exc.code, exc.message
    if isinstance(exc, AssetFetchFailure):
        if exc.kind == "time_budget":
            minutes = int(media_link.ACCEPT_ALL_TIME_BUDGET_SECONDS // 60)
            return "time_budget_exceeded", f"Stopped after the {minutes} minute time limit. Nothing was added."
        if exc.kind == "upstream":
            return "provider_error", f"{provider} server returned {exc.upstream_status}. Nothing was added."
        return "network_error", f"Could not resolve the {provider} server. Nothing was added."
    if isinstance(exc, HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "The apply was refused."
        if exc.status_code == 422:
            return "asset_rejected", f"{detail} Nothing was added."
        if exc.status_code == 409:
            return "conflict", detail
        if exc.status_code == 404:
            return "game_not_found", "The game no longer exists."
        if exc.status_code == 502:
            return "provider_error", f"{provider} server sent an unusable response. Nothing was added."
        return "apply_failed", detail
    if isinstance(exc, httpx2.TimeoutException):
        return "network_error", f"Timed out waiting for the {provider} server. Nothing was added."
    if isinstance(exc, httpx2.RequestError):
        return "network_error", f"Could not reach the {provider} server. Nothing was added."
    if isinstance(exc, PermissionError):
        return "permission_error", "Permission denied writing to the media folder. Nothing was added."
    if isinstance(exc, OSError):
        if exc.errno == errno.ENOSPC or getattr(exc, "winerror", None) == _WINDOWS_DISK_FULL:
            return "disk_full", "The disk is full. Nothing was added."
        return "storage_error", f"A file operation failed ({errno.errorcode.get(exc.errno or 0, 'unknown')}). Nothing was added."
    return "internal_error", "Unexpected error. See the server log. Nothing was added."


def status(job_id: str) -> Optional[dict[str, Any]]:
    """Client-facing status of an Accept All job, or None when *job_id* is
    unknown or belongs to another kind of job."""
    job = jobs.get(job_id)
    if job is None or job["kind"] != JOB_KIND:
        return None
    meta = job["meta"]
    if job["status"] == "processing":
        state = "running" if meta.get("started") else "queued"
    else:
        state = _STATES[job["status"]]
    return {
        "job_id": job["id"],
        "state": state,
        "done": meta.get("done", 0),
        "total": meta.get("total", 0),
        "label": meta.get("label"),
        "error": meta.get("error"),
        "result": job["result"],
        "cancel_requested": job["status"] == "cancelling",
    }
