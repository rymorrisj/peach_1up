"""Upload finalization — the single funnel from a reassembled upload into the
library ingester.

`finalize_inline` runs in the request (small uploads, ≤ threshold) and returns a
normalized result the route sends as 201. `finalize_background` runs as a
BackgroundTask (large uploads) with its own DB session, reporting progress into
core.jobs and reaping the destination on failure. Both call `_finalize`, so the
reassemble → dedup → ingest → cleanup sequence lives in exactly one place.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from backend.core import jobs
from backend.core.logger import get_logger
from backend.service.library import chunked_uploads as cu
from backend.service.library import folder_ingest
from backend.service.library import items as lib_svc

logger = get_logger(__name__)


def _finalize(upload_id: str, media_root: Path, db: Session) -> dict:
    """Reassemble the staged upload, ingest it, and return a normalized summary:
    ``{result_type, id, title, reused_existing_media?, disc_count?}``.

    tmp staging is dropped by reassemble(); the reassembled destination is
    removed here if ingest fails so a failed upload never leaves an orphan under
    MEDIA_PATH.
    """
    reasm = cu.reassemble(upload_id, media_root)
    try:
        if reasm.kind == "file":
            from backend.service.utils.upload_utils import find_existing_duplicate

            dest_path = reasm.paths[0]
            duplicate = find_existing_duplicate(media_root, dest_path, reasm.total_bytes)
            reused = duplicate is not None
            ingest_path = duplicate if reused else dest_path
            if reused:
                shutil.rmtree(reasm.dest_dir, ignore_errors=True)
            title = reasm.title or ingest_path.stem.replace("-", " ").title()
            item = lib_svc._ingest_media_entry(str(ingest_path), title, db)
            return {
                "result_type": "library_item",
                "id": item.id,
                "title": item.title,
                "reused_existing_media": reused,
            }

        result_type, entity = folder_ingest.ingest_folder(
            reasm.dest_dir, reasm.paths, reasm.title, db
        )
        summary = {"result_type": result_type, "id": entity.id, "title": entity.title}
        if result_type == "library_set":
            summary["disc_count"] = len(reasm.paths)
        return summary
    except Exception:
        # Reassembled bytes live under MEDIA_PATH but were never persisted — drop
        # them (reused-duplicate already removed dest_dir above; ignore_errors
        # makes the double-remove safe).
        shutil.rmtree(reasm.dest_dir, ignore_errors=True)
        raise


def finalize_inline(upload_id: str, media_root: Path, db: Session) -> dict:
    return _finalize(upload_id, media_root, db)


def finalize_background(upload_id: str, media_root: str, job_id: str) -> None:
    """BackgroundTask entry: own DB session, report to core.jobs, never raise."""
    from backend.core.database import get_engine

    db = Session(get_engine())
    try:
        jobs.update(job_id, progress=0.1, message="Reassembling upload…")
        result = _finalize(upload_id, Path(media_root), db)
        jobs.complete(job_id, result=result, message=f"Added \"{result.get('title', 'upload')}\".")
    except Exception as exc:  # noqa: BLE001 — background tasks must not propagate
        logger.exception("Background upload finalize failed: upload_id=%s", upload_id)
        db.rollback()
        cu.abort(upload_id)
        jobs.fail(job_id, str(exc))
    finally:
        db.close()
