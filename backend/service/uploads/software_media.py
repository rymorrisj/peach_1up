"""Upload finalization for the software_media domain (the archival Media
sub-tab under Software, MediaItem/MediaItemBundle, backend/models/media.py).

Locked decision (resolves the "does Media finalize create the DB row"
question the frontend's PROVISIONAL CONTRACT comments flagged): it does NOT.
dev_docs/v2/03_media_archive.md's route table treats item creation
(POST /api/v1/media-items) as a separate, direct step from upload, and the
already-shipped single-shot endpoint (POST /api/v1/media-items/upload in
backend/api/routes/media.py) only stages bytes and returns
{path, slug, size_bytes}, it does not touch the DB either. This chunked path
mirrors that exact contract instead of Game/App's "finalize creates the row"
shape: reassemble, return the staged path, and let the caller make its own
POST /api/v1/media-items (or /media-item-bundles) with that file_path plus
the fields only a human can supply (title, media_kind, description, ...).

Storage root is MEDIA_PATH (library/software/media/), the same setting the
existing single-shot archive upload uses, not library_domain_root("media"),
which is unrelated Software-domain vocabulary that nothing in this domain
consumes (see path_utils.py).

Media has no multi-disc or folder-bundle concept (doc 03: "standalone-item-
first, not a multi-disc collection concept like Game"), only kind="file" is
accepted; init_upload rejects "folder"/"set" for this domain via the
registry's allowed_kinds before a session is even created.
"""
from __future__ import annotations

from pathlib import Path

from backend.core import jobs
from backend.core.logger import get_logger
from backend.service.uploads import core as cu
from backend.service.uploads.registry import UploadDomain, register_domain

logger = get_logger(__name__)


def _result(reasm: cu.ReassembledUpload) -> dict:
    return {
        "result_type": "media_upload",
        "path": str(reasm.paths[0]),
        "slug": reasm.dest_dir.name,
        "title": reasm.title,
        "size_bytes": reasm.total_bytes,
    }


def finalize_background(upload_id: str, media_root: str, job_id: str) -> None:
    """BackgroundTask entry: no DB session needed (see module docstring), but
    still reports progress into core.jobs like every other domain so the nav
    bell behaves identically regardless of which domain a large upload belongs to."""
    try:
        jobs.update(job_id, progress=0.0, message="Reassembling upload…")
        reasm = cu.reassemble(upload_id, Path(media_root), job_id=job_id)
        result = _result(reasm)
        jobs.complete(job_id, result=result, message=f"Staged \"{result.get('title', 'upload')}\".")
    except Exception as exc:  # noqa: BLE001, background tasks must not propagate
        logger.exception("Background media upload finalize failed: upload_id=%s", upload_id)
        cu.abort(upload_id)
        jobs.fail(job_id, str(exc))


def _root() -> Path:
    from backend.core.settings import get_settings
    return Path(get_settings().get_env_var("MEDIA_PATH")).resolve()


def register() -> None:
    register_domain(
        UploadDomain(
            name="software_media",
            allowed_kinds=frozenset({"file"}),
            root_resolver=_root,
            finalize_background=finalize_background,
        )
    )
