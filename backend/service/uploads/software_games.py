"""Upload finalization for the software_games domain, the single funnel from
a reassembled upload into the Game library ingester.

`finalize_inline` runs in the request (small uploads, <= threshold) and returns
a normalized result the route sends as 201. `finalize_background` runs as a
BackgroundTask (large uploads) with its own DB session, reporting progress into
core.jobs and reaping the destination on failure. Both reassemble from staged
upload chunks, then call `finalize_reassembled`, so the ingest -> cleanup
sequence lives in exactly one place, `service.games.path_import` reuses
`finalize_reassembled` directly for server-side-path imports, whose "reassembly"
is a filesystem copy instead of a chunk reassembly. Anchor dedup (content-hash
reuse of an existing on-disk file) only applies to the "file" and auto-detected
"folder" kinds, not explicit "set" uploads, see the "set" branch.

Unlike software_media, this domain's finalize creates the GameItemBundle row
directly, Game ingest (era detection, multi-disc handling, dedup) has always
worked this way and doc 02 does not change that.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from backend.core import jobs
from backend.core.logger import get_logger
from backend.service.games import folder_ingest
from backend.service.games import items as lib_svc
from backend.service.uploads import core as cu
from backend.service.uploads.registry import UploadDomain, register_domain

logger = get_logger(__name__)


def finalize_reassembled(reasm: cu.ReassembledUpload, media_root: Path, db: Session) -> dict:
    """Ingest an already-staged ``ReassembledUpload`` and return a normalized
    summary: ``{result_type, id, title, reused_existing_media?, disc_count?}``.

    Shared by chunked-upload finalization (reasm comes from ``cu.reassemble``,
    staged from browser-uploaded chunks) and server-side-path import (reasm
    comes from copying a path the file browser resolved), both just need
    "some files already sitting under SOFTWARE_PATH" ingested the same way. The
    destination is removed here if ingest fails so a failed finalize never
    leaves an orphan under SOFTWARE_PATH.
    """
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
            collection = lib_svc._ingest_media_entry(str(ingest_path), title, db)
            return {
                "result_type": "game_item_bundle",
                "id": collection.id,
                "title": collection.title,
                "reused_existing_media": reused,
            }

        if reasm.kind == "set":
            # Paths are in manifest (file_index) order, disc 1 first. A disc can
            # be more than one file (e.g. .cue + .bin); select_disc_pointer_files
            # picks the .cue/.gdi pointers in that order and drops companions,
            # rather than re-sorting alphabetically as folder_ingest does.
            #
            # No anchor dedup here (unlike ingest_folder's auto-detected multi-disc
            # path): every file in a "set" upload was just written into one
            # unique-slugged reasm.dest_dir together, and must stay together.
            # Repointing disc 1 at a byte-identical file elsewhere on disk would
            # split the set across two folders.
            disc_files = folder_ingest.select_disc_pointer_files(reasm.paths)
            collection = lib_svc._create_multi_disc_collection(
                disc_files, reasm.title, db, staging_dir=reasm.dest_dir
            )
            return {
                "result_type": "game_item_bundle",
                "id": collection.id,
                "title": collection.title,
                "disc_count": len(disc_files),
            }

        result_type, collection, disc_count = folder_ingest.ingest_folder(
            reasm.dest_dir, reasm.paths, reasm.title, db, media_root
        )
        return {
            "result_type": result_type,
            "id": collection.id,
            "title": collection.title,
            "disc_count": disc_count,
        }
    except Exception:
        # Reassembled bytes live under SOFTWARE_PATH but were never persisted, drop
        # them (reused-duplicate already removed dest_dir above; ignore_errors
        # makes the double-remove safe).
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
        jobs.update(job_id, progress=0.1, message="Reassembling upload…")
        reasm = cu.reassemble(upload_id, Path(media_root))
        result = finalize_reassembled(reasm, Path(media_root), db)
        jobs.complete(job_id, result=result, message=f"Added \"{result.get('title', 'upload')}\".")
    except Exception as exc:  # noqa: BLE001, background tasks must not propagate
        logger.exception("Background upload finalize failed: upload_id=%s", upload_id)
        db.rollback()
        cu.abort(upload_id)
        jobs.fail(job_id, str(exc))
    finally:
        db.close()


def _root() -> Path:
    from backend.service.utils.path_utils import library_domain_root
    return library_domain_root("game")


def register() -> None:
    register_domain(
        UploadDomain(
            name="software_games",
            permission_flag="can_manage_game",
            allowed_kinds=frozenset({"file", "folder", "set"}),
            root_resolver=_root,
            finalize_inline=finalize_inline,
            finalize_background=finalize_background,
        )
    )
