"""Upload finalization for the software_media domain (the archival Media
sub-tab under Software, MediaItem/MediaItemBundle, backend/models/media.py).

Finalize creates the DB row (MED-12), like Game and App: reassemble, then
one MediaItem (asset_type and source_url null, so it counts as added by
hand) inside a new collection-of-one MediaItemBundle, the same pairing
POST /api/v1/media-items makes. If row creation fails, the directory
reassemble() created exclusively for this upload is removed, so no file
is left without a row. This supersedes the earlier locked decision that
finalize only staged bytes; the single-shot POST /api/v1/media-items/upload
still only stages.

The kind comes from the file extension. An archive (.zip, .7z) is allowed
for every kind, so its kind cannot be inferred: init rejects it before any
bytes move, and finalize re-checks rather than guessing.

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

import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from backend.core import jobs
from backend.core.logger import get_logger
from backend.service.uploads import core as cu
from backend.service.uploads.registry import UploadDomain, register_domain
from backend.service.utils.media_extensions import MEDIA_KIND_INFERABLE_EXTENSIONS, media_kind_for_extension

logger = get_logger(__name__)


def finalize_reassembled(reasm: cu.ReassembledUpload, db: Session) -> dict:
    """Create the MediaItem and its bundle for a reassembled upload.

    Raises:
        ValueError: If the media kind cannot be inferred from the extension.
    """
    from backend.models.media import MediaItem, MediaItemBundle, unique_media_slug

    try:
        if len(reasm.paths) != 1:
            raise ValueError(f"A media upload holds exactly one file, got {len(reasm.paths)}.")
        path = reasm.paths[0]
        media_kind = media_kind_for_extension(path.name)
        if media_kind is None:
            raise ValueError(
                f"Cannot tell the media kind of '{path.name}' from its extension. "
                "Archives (.zip, .7z) need their kind chosen; upload the files themselves instead."
            )
        title = reasm.title or reasm.dest_dir.name
        item_slug = unique_media_slug(title, db)
        bundle = MediaItemBundle(
            title=title,
            media_kind=media_kind,
            slug=unique_media_slug(f"{title} Collection", db),
        )
        db.add(bundle)
        db.flush()
        item = MediaItem(
            title=title,
            media_kind=media_kind,
            file_path=str(path),
            file_size_bytes=reasm.total_bytes,
            media_item_bundle_id=bundle.id,
            slug=item_slug,
        )
        db.add(item)
        db.flush()
        bundle_id, item_id = bundle.id, item.id
        db.commit()
    except Exception:
        db.rollback()
        shutil.rmtree(reasm.dest_dir, ignore_errors=True)
        raise
    return {
        "result_type": "media_upload",
        "id": bundle_id,
        "media_item_id": item_id,
        "path": str(path),
        "slug": reasm.dest_dir.name,
        "title": title,
        "size_bytes": reasm.total_bytes,
    }


def finalize_background(upload_id: str, media_root: str, job_id: str) -> None:
    """BackgroundTask entry: own DB session, report to core.jobs, never raise."""
    from backend.core.database import get_engine

    db = Session(get_engine())
    try:
        jobs.update(job_id, progress=0.0, message="Reassembling upload…")
        reasm = cu.reassemble(upload_id, Path(media_root), job_id=job_id)
        result = finalize_reassembled(reasm, db)
        jobs.complete(job_id, result=result, message=f"Added \"{result.get('title', 'upload')}\".")
    except Exception as exc:  # noqa: BLE001, background tasks must not propagate
        logger.exception("Background media upload finalize failed: upload_id=%s", upload_id)
        db.rollback()
        cu.abort(upload_id)
        jobs.fail(job_id, str(exc))
    finally:
        db.close()


def _root() -> Path:
    """MEDIA_PATH resolved. Called from POST .../complete before the
    background finalize is scheduled, so an unset or blank MEDIA_PATH fails
    that request with 503 instead of reassembling into the working directory.
    """
    from fastapi import HTTPException

    from backend.service.utils.path_utils import media_root
    try:
        return media_root()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def register() -> None:
    register_domain(
        UploadDomain(
            name="software_media",
            allowed_kinds=frozenset({"file"}),
            root_resolver=_root,
            finalize_background=finalize_background,
            # The MED-11 allowlist minus archives, whose kind cannot be
            # inferred; rejected at init, before any bytes move.
            allowed_extensions=MEDIA_KIND_INFERABLE_EXTENSIONS,
        )
    )
