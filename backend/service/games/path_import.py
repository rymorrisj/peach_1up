"""Server-side-path import — a second ingestion transport for Add Media.

GET /api/v1/filesystem/browse already resolves real, absolute, server-known
paths for "Locate file/folder..." (ROM pack install) and the manual
launch-target override. This module lets Add Media accept the same kind of
path as an import source, alongside (not instead of) the browser-upload
transport in service.uploads.core, the browser-upload path is used when the
source lives on the user's machine; this one is used when it already lives on
the server's filesystem, so no chunked transfer is needed.

stage_from_source stages the source into a fresh directory under
SOFTWARE_PATH. When delete_original is False it copies, so the source is
left untouched. When delete_original is True it first attempts an atomic
os.rename, which only succeeds when source and destination share a
filesystem/drive, no partial state is possible so nothing needs verifying
afterward. When source and destination are on different filesystems/drives
(rename fails with "not same device"), it falls back to the same copy the
delete_original=False path uses, runs the same post-copy integrity checks,
and only then deletes the source, never before the copy is confirmed
complete and correct. Either way this is one atomic-from-the-caller's-
perspective operation instead of a transient double-disk-usage window
followed by a separate, easy-to-get-wrong cleanup step. stage_from_source
builds the same ReassembledUpload shape service.uploads.core produces from
staged chunks, so software_games.finalize_reassembled (dedup, multi-disc
detection, cleanup-on-failure) is reused unmodified.

When the source already resolves under SOFTWARE_PATH, none of that applies:
there is nothing to copy and no disposable staging directory for
finalize_reassembled to safely delete on a duplicate or a failure, deleting
"dest_dir" in that case would delete the source itself. _import_in_place
bypasses stage_from_source/finalize_reassembled for that case and ingests the
source directly, the same treatment manual add and Scan's import step give a
path that is already in place.
"""
from __future__ import annotations

import errno
import os
import shutil
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.core.logger import get_logger
from backend.service.games import items as lib_svc
from backend.service.uploads import core as cu
from backend.service.uploads import software_games as upload_finalize
from backend.service.utils.path_utils import is_within_roots, resolve_under, safe_basename
from backend.service.utils.slug_generator import unique_slug
from backend.service.utils.upload_utils import DEFAULT_BACKGROUND_THRESHOLD_BYTES, DEFAULT_MAX_BYTES

logger = get_logger(__name__)


def source_size(source: Path) -> int:
    """Best-effort size of *source* (file or folder), for the max-size guard
    and the inline/background threshold decision. Symlinked entries are
    skipped, matching stage_from_source's copytree(symlinks=True) — they are
    never dereferenced, so their target's size must not count either. Never
    raises — an unreadable size falls back to just over the background
    threshold (routing the import to the background path rather than
    blocking the request thread on a source whose true size is unknown),
    while staying under DEFAULT_MAX_BYTES so it is not falsely rejected by
    the max-size guard."""
    try:
        if source.is_file():
            return source.stat().st_size
        total = 0
        for p in source.rglob("*"):
            try:
                if p.is_file() and not p.is_symlink():
                    total += p.stat().st_size
            except OSError:
                continue
        return total
    except OSError:
        return DEFAULT_BACKGROUND_THRESHOLD_BYTES + 1


# Windows' ERROR_NOT_SAME_DEVICE. CPython's Windows errno mapping already
# translates this to errno.EXDEV on OSError, but that mapping table isn't
# something to take on faith for a Windows-only codebase, so the winerror
# attribute (only ever set on Windows) is checked directly as a second,
# platform-native signal alongside errno.EXDEV.
_ERROR_NOT_SAME_DEVICE = 17


def _rename_same_filesystem(source: Path, dest: Path) -> bool:
    """Attempt an atomic same-filesystem move via os.rename. Returns True on
    success. Returns False only when the rename failed specifically because
    *source* and *dest* are on different filesystems/drives, the one case
    that requires falling back to copy. Any other OSError (permissions, a
    name collision, etc.) is a genuine failure and propagates unchanged, it
    must not be misread as "just needs a fallback."
    """
    try:
        os.rename(str(source), str(dest))
        return True
    except OSError as exc:
        if exc.errno == errno.EXDEV or getattr(exc, "winerror", None) == _ERROR_NOT_SAME_DEVICE:
            return False
        raise


def stage_from_source(
    source: Path, title: str, domain_root: Path, move: bool = False,
) -> cu.ReassembledUpload:
    """Stage *source* (already validated to exist and fall within the allowed
    browse roots) into a fresh, uniquely-named directory under domain_root, and
    return the same ReassembledUpload shape upload_finalize expects — so
    finalize_reassembled can ingest it exactly like a chunked upload's output,
    dedup and multi-disc detection included.

    move=False (default) copies, leaving *source* untouched. move=True is for
    callers that are about to delete the original anyway (delete_original=True):

    - Same filesystem: os.rename is attempted first. It's atomic, no partial
      state can exist, so on success there is nothing left to verify or
      delete, the source is simply gone and the destination is simply there.
    - Different filesystems: os.rename always fails (cross-device rename
      isn't possible at the OS level), detected via _rename_same_filesystem
      returning False. This falls back to the same copy2/copytree used when
      move=False, runs the same post-copy integrity checks below, and only
      deletes *source* after those checks confirm the destination is a
      complete, correct copy. The source is never deleted before a copy is
      verified, so a truncated/corrupted cross-device copy cannot destroy the
      only remaining copy of the data.

    Folder copies/moves preserve symlinks as symlinks (never follow them) so a
    symlink nested inside an otherwise-legitimate source folder can't be used
    to pull content from outside the allowed browse roots into the library
    (the cross-device copy fallback uses copytree(symlinks=True) too, so this
    holds for both).
    Original filenames are preserved verbatim for a folder source (unlike the
    browser-upload path, these are real host filenames, not untrusted
    client-supplied strings — sanitizing them would also break disc-pointer
    files like .cue that reference sibling files by exact name).
    """
    kind = "folder" if source.is_dir() else "file"
    base_title = (title or source.stem.replace("-", " ").title()).strip() or "import"
    slug = unique_slug(base_title, lambda s: (domain_root / s).exists())
    domain_root.mkdir(parents=True, exist_ok=True)
    dest_dir = resolve_under(domain_root, slug)

    renamed = False
    try:
        if kind == "file":
            source_bytes = source.stat().st_size
            dest_dir.mkdir(parents=True, exist_ok=False)
            dest_path = resolve_under(dest_dir, safe_basename(source.name))
            if move:
                renamed = _rename_same_filesystem(source, dest_path)
            if not renamed:
                shutil.copy2(str(source), str(dest_path))
            paths = [dest_path]
        else:
            source_bytes = source_size(source)
            if move:
                renamed = _rename_same_filesystem(source, dest_dir)
            if not renamed:
                shutil.copytree(str(source), str(dest_dir), symlinks=True)
            paths = [p for p in dest_dir.rglob("*") if p.is_file() and not p.is_symlink()]
        total_bytes = sum(p.stat().st_size for p in paths)
        if total_bytes == 0 or total_bytes != source_bytes:
            raise ValueError(
                f"Copied '{source.name}' is {total_bytes} bytes, expected {source_bytes} "
                "bytes from the source at copy time; the source may be empty (e.g. an "
                "unsynced cloud-storage placeholder) or the copy did not complete."
            )
    except Exception:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise

    if total_bytes > DEFAULT_MAX_BYTES:
        # Defensive re-check: source_size() already gated this in the route
        # before the copy started, but the source could have grown mid-copy.
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise HTTPException(status_code=413, detail="Import exceeds the maximum allowed size.")

    if move and not renamed:
        # Cross-device fallback: the copy above is now verified complete and
        # within size limits, so it's safe to remove the original. Any
        # failure here (e.g. permissions) is left to propagate, not
        # swallowed, the destination copy is already valid and is not rolled
        # back for a failed cleanup of the source.
        if source.is_dir():
            shutil.rmtree(str(source))
        else:
            source.unlink()

    return cu.ReassembledUpload(
        kind=kind, title=base_title, dest_dir=dest_dir, paths=paths, total_bytes=total_bytes,
    )


def _import_in_place(source: Path, title: str, db: Session, delete_original: bool) -> dict:
    """Ingest *source* directly, with no copy: the same treatment Scan's
    import step (import_scan_results -> _prepare_item) already gives a path
    that is already under SOFTWARE_PATH.

    finalize_reassembled's dedup-elsewhere-and-delete-dest_dir and
    failure-cleanup rmtree(dest_dir) both assume dest_dir is disposable
    staging that stage_from_source just created, that assumption is false
    here (dest_dir would be the source itself), so this bypasses
    stage_from_source/finalize_reassembled entirely and calls the same
    ingester manual add and scan-import use directly.

    delete_original is accepted only to decide whether delete_original_note
    belongs in the result, it is never acted on here (there is no separate
    original left to delete once the source itself becomes the library item).
    """
    collection = lib_svc._ingest_media_entry(str(source), title, db)
    result = {
        "result_type": "game_item_bundle",
        "id": collection.id,
        "title": collection.title,
    }
    if delete_original:
        result["delete_original_note"] = (
            "The source was already inside the library, so nothing was copied "
            "or deleted, it was imported in place."
        )
    return result


def import_inline(
    source: Path, title: str, domain_root: Path, db: Session, delete_original: bool
) -> dict:
    in_place = is_within_roots(source, [domain_root])
    if in_place:
        # Ingesting in place adopts the source itself as the library item
        # (moving/renaming it into its canonical spot at most), there is no
        # separate "original" left over to delete afterward.
        return _import_in_place(source, title, db, delete_original)
    reasm = stage_from_source(source, title, domain_root, move=delete_original)
    return upload_finalize.finalize_reassembled(reasm, domain_root, db)


def import_background(
    source_path: str, title: str, domain_root: str, job_id: str, delete_original: bool,
) -> None:
    """BackgroundTask entry: own DB session, report to core.jobs, never raise."""
    from backend.core import jobs
    from backend.core.database import get_engine

    db = Session(get_engine())
    source = Path(source_path)
    root = Path(domain_root)
    try:
        in_place = is_within_roots(source, [root])
        if in_place:
            jobs.update(job_id, progress=0.5, message="Importing…")
            result = _import_in_place(source, title, db, delete_original)
        else:
            jobs.update(
                job_id, progress=0.1,
                message="Moving into library…" if delete_original else "Copying into library…",
            )
            reasm = stage_from_source(source, title, root, move=delete_original)
            jobs.update(job_id, progress=0.6, message="Importing…")
            result = upload_finalize.finalize_reassembled(reasm, root, db)
        jobs.complete(job_id, result=result, message=f"Added \"{result.get('title', 'import')}\".")
    except lib_svc._ItemAlreadyExists as exc:
        # A duplicate-import attempt is an expected rejection, not a real
        # failure, _ItemAlreadyExists never sets its own message (its __init__
        # only stores the colliding collection), so str(exc) is always empty
        # here, that's what previously left jobs.fail() writing an empty
        # message, and the Activity panel falling back to a bare status word.
        # This mirrors the message import_inline's own caller already builds
        # for the same exception at the route level (game_item_bundles.py).
        title = exc.collection.title if exc.collection else None
        message = f'"{title}" is already in the library.' if title else "This item is already in the library."
        logger.info("Background path import skipped, already in library: source=%s", source)
        db.rollback()
        jobs.fail(job_id, message)
    except Exception as exc:  # noqa: BLE001 — background tasks must not propagate
        logger.exception("Background path import failed: source=%s", source)
        db.rollback()
        jobs.fail(job_id, str(exc))
    finally:
        db.close()
