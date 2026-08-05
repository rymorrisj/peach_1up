"""Upload finalization for the software_games domain, the single funnel from
a reassembled upload into the Game library ingester.

`finalize_background` runs as a BackgroundTask (every upload, regardless of
size) with its own DB session, reporting progress into core.jobs and reaping
the destination on failure. It reassembles from staged upload chunks, then
calls `finalize_reassembled`, so the ingest -> cleanup sequence lives in
exactly one place, `service.games.path_import` reuses `finalize_reassembled`
directly for server-side-path imports, whose "reassembly" is a filesystem
copy instead of a chunk reassembly. Anchor dedup (content-hash reuse of an
existing on-disk file) only applies to the "file" and auto-detected "folder"
kinds, not explicit "set" uploads, see the "set" branch.

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


def finalize_reassembled(reasm: cu.ReassembledUpload, domain_root: Path, db: Session) -> dict:
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
            duplicate = find_existing_duplicate(domain_root, dest_path, reasm.total_bytes)
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
            #
            # This branch owns its transaction: it drives the ingest stages and
            # commits. _ingest_transaction rolls back and replays the staging
            # stage's undo callables on failure, which renames reasm.dest_dir
            # back from its slug name so the except clause below can still
            # rmtree it by the path it holds.
            disc_files = folder_ingest.select_disc_pointer_files(reasm.paths)
            undo_ops: list = []
            with lib_svc._ingest_transaction(
                db,
                undo_ops,
                slug_collision_detail=lib_svc.multi_disc_slug_collision_detail(
                    reasm.title, disc_files
                ),
            ):
                collection_fields, leaf_rows = lib_svc._prepare_multi_disc(
                    disc_files, reasm.title, db, staging_dir=reasm.dest_dir, undo_stack=undo_ops
                )
                collection = lib_svc._persist_multi_disc_collection(
                    collection_fields, leaf_rows, db
                )
                db.commit()
            db.refresh(collection)
            return {
                "result_type": "game_item_bundle",
                "id": collection.id,
                "title": collection.title,
                "disc_count": len(disc_files),
            }

        result_type, collection, disc_count = folder_ingest.ingest_folder(
            reasm.dest_dir, reasm.paths, reasm.title, db, domain_root
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


def finalize_background(upload_id: str, domain_root: str, job_id: str) -> None:
    """BackgroundTask entry: own DB session, report to core.jobs, never raise.

    _ItemAlreadyExists/_SlugCollision are caught ahead of the generic handler
    below so a duplicate-content or slug-collision upload gets the same clean,
    specific job error message the old inline finalize path's HTTP 409 used to
    carry (_ItemAlreadyExists in particular never sets its own message, so
    falling through to the generic `str(exc)` handler would leave the job's
    error blank, mirrors service.games.path_import.import_background's
    handling of the same exception for server-side-path imports).
    """
    from backend.core.database import get_engine

    db = Session(get_engine())
    try:
        jobs.update(job_id, progress=0.0, message="Reassembling upload…")
        reasm = cu.reassemble(upload_id, Path(domain_root), job_id=job_id)
        result = finalize_reassembled(reasm, Path(domain_root), db)
        jobs.complete(job_id, result=result, message=f"Added \"{result.get('title', 'upload')}\".")
    except lib_svc._ItemAlreadyExists:
        # Matches the fixed message the old route-level 409 used for this
        # exception (it never set its own message, see the class docstring).
        logger.info("Upload finalize skipped, already in library: upload_id=%s", upload_id)
        db.rollback()
        cu.abort(upload_id)
        jobs.fail(job_id, "This upload's content is already in the library.")
    except lib_svc._SlugCollision as exc:
        db.rollback()
        cu.abort(upload_id)
        jobs.fail(job_id, str(exc))
    except Exception as exc:  # noqa: BLE001, background tasks must not propagate
        logger.exception("Background upload finalize failed: upload_id=%s", upload_id)
        db.rollback()
        cu.abort(upload_id)
        jobs.fail(job_id, str(exc))
    finally:
        db.close()


def _root() -> Path:
    from backend.service.utils.path_utils import library_domain_root
    return library_domain_root("games")


def register() -> None:
    register_domain(
        UploadDomain(
            name="software_games",
            allowed_kinds=frozenset({"file", "folder", "set"}),
            root_resolver=_root,
            finalize_background=finalize_background,
        )
    )
