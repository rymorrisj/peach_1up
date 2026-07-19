"""Upload finalization for the software_apps domain.

App had zero prior upload/file-transport surface, apps.py's only creation
route (POST /api/v1/app-items, backend/service/apps/items.py::create_app_item_bundle)
takes a pre-existing on-disk file_path and does no ingest of its own. This
module is the first thing that actually writes uploaded bytes into an
AppItemBundle + AppItem row, mirroring the shape of
software_games.finalize_reassembled (finalize creates the DB row directly)
but deliberately simplified: apps.py's own create path already establishes
that Apps get no era detection ("the caller supplies era explicitly", per
service/apps/items.py) and no multi-disc concept, so this finalize does
not run smart_media_detector or disc-pointer selection either. era is left
"unknown" (AppItemBundleCreate's own default), the user can set it from the
detail page's edit form after upload, same as any other field a human, not a
detector, is the source of truth for here.

kind="set" is not supported for Apps (AppItem has no disc_number concept), so
it is excluded from this domain's allowed_kinds in register() below, enforced by
the route layer before a session is even created.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from backend.core import jobs
from backend.core.logger import get_logger
from backend.models.app import AppItem, AppItemBundle
from backend.service.uploads import core as cu
from backend.service.uploads.registry import UploadDomain, register_domain
from backend.service.utils.file_types import file_type_from_path
from backend.service.utils.slug_generator import unique_slug

logger = get_logger(__name__)


def _generate_app_slug(name: str, db: Session) -> str:
    return unique_slug(
        name,
        lambda s: db.query(AppItemBundle).filter(AppItemBundle.slug == s).first() is not None,
    )


def finalize_reassembled(reasm: cu.ReassembledUpload, media_root: Path, db: Session) -> dict:
    """Create an AppItemBundle from a reassembled upload. kind="file" is a
    collection-of-one; kind="folder" gets one AppItem leaf per file
    (ordered by name, Apps have no disc_number), first leaf becomes the
    launch/display disk. Every leaf's folder_path is the shared dest_dir
    reassemble() created exclusively for this upload, so folder_owned=True
    on all of them (mirrors GameItemBundle's multi-disc "set" ingest)."""
    del media_root  # dest_dir under it is already resolved on reasm
    try:
        title = reasm.title or reasm.dest_dir.name
        bundle = AppItemBundle(
            title=title,
            slug=_generate_app_slug(title, db),
            era="unknown",
        )
        db.add(bundle)
        db.flush()

        paths = sorted(reasm.paths, key=lambda p: p.name) if reasm.kind == "folder" else reasm.paths
        leaves: list[AppItem] = []
        for path in paths:
            leaf = AppItem(
                app_item_bundle_id=bundle.id,
                file_path=str(path),
                folder_path=str(reasm.dest_dir),
                folder_owned=True,
                file_type=file_type_from_path(path),
                file_size_bytes=path.stat().st_size if path.is_file() else None,
                original_name=path.name,
            )
            db.add(leaf)
            leaves.append(leaf)
        db.flush()

        leaves[0].executable_path = str(paths[0])
        bundle.launch_disk_id = leaves[0].id
        bundle.display_disk_id = leaves[0].id
        db.add(bundle)
        db.commit()
        db.refresh(bundle)
        return {
            "result_type": "app_item_bundle",
            "id": bundle.id,
            "title": bundle.title,
            "disc_count": len(leaves) if reasm.kind == "folder" else None,
        }
    except Exception:
        db.rollback()
        shutil.rmtree(reasm.dest_dir, ignore_errors=True)
        raise


def finalize_inline(upload_id: str, media_root: Path, db: Session) -> dict:
    reasm = cu.reassemble(upload_id, media_root)
    return finalize_reassembled(reasm, media_root, db)


def finalize_background(upload_id: str, media_root: str, job_id: str) -> None:
    """BackgroundTask entry: own DB session, report to core.jobs, never raise."""
    from backend.core.database import get_engine

    db = Session(get_engine())
    try:
        jobs.update(job_id, progress=0.0, message="Reassembling upload…")
        reasm = cu.reassemble(upload_id, Path(media_root), job_id=job_id)
        result = finalize_reassembled(reasm, Path(media_root), db)
        jobs.complete(job_id, result=result, message=f"Added \"{result.get('title', 'upload')}\".")
    except Exception as exc:  # noqa: BLE001, background tasks must not propagate
        logger.exception("Background app upload finalize failed: upload_id=%s", upload_id)
        db.rollback()
        cu.abort(upload_id)
        jobs.fail(job_id, str(exc))
    finally:
        db.close()


def _root() -> Path:
    from backend.service.utils.path_utils import library_domain_root
    return library_domain_root("apps")


def register() -> None:
    register_domain(
        UploadDomain(
            name="software_apps",
            permission_flag="can_manage_app",
            allowed_kinds=frozenset({"file", "folder"}),
            root_resolver=_root,
            finalize_inline=finalize_inline,
            finalize_background=finalize_background,
        )
    )
