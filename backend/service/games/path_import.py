"""Server-side-path import — a second ingestion transport for Add Media.

GET /api/v1/filesystem/browse already resolves real, absolute, server-known
paths for "Locate file/folder..." (ROM pack install) and the manual
launch-target override. This module lets Add Media accept the same kind of
path as an import source, alongside (not instead of) the browser-upload
transport in chunked_uploads.py — the browser-upload path is used when the
source lives on the user's machine; this one is used when it already lives on
the server's filesystem, so no chunked transfer is needed.

stage_from_source always copies (never moves) the source into a fresh
directory under SOFTWARE_PATH, so the source is untouched until ingest has fully
succeeded. Only then, if the caller opted in, is the original deleted — never
before a confirmed successful write into the library. stage_from_source builds
the same ReassembledUpload shape service.games.chunked_uploads produces from
staged chunks, so upload_finalize.finalize_reassembled (dedup, multi-disc
detection, cleanup-on-failure) is reused unmodified.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.core.logger import get_logger
from backend.service.games import chunked_uploads as cu
from backend.service.games import upload_finalize
from backend.service.utils.path_utils import resolve_under, sanitize_filename
from backend.service.utils.slug_generator import unique_slug
from backend.service.utils.upload_utils import DEFAULT_MAX_BYTES

logger = get_logger(__name__)


def source_size(source: Path) -> int:
    """Best-effort size of *source* (file or folder), for the max-size guard
    and the inline/background threshold decision. Symlinked entries are
    skipped, matching stage_from_source's copytree(symlinks=True) — they are
    never dereferenced, so their target's size must not count either. Never
    raises — an unreadable size falls back to 0, which routes the import
    inline rather than silently dropping it."""
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
        return 0


def stage_from_source(source: Path, title: str, media_root: Path) -> cu.ReassembledUpload:
    """Copy *source* (already validated to exist and fall within the allowed
    browse roots) into a fresh, uniquely-named directory under media_root, and
    return the same ReassembledUpload shape upload_finalize expects — so
    finalize_reassembled can ingest it exactly like a chunked upload's output,
    dedup and multi-disc detection included.

    Folder copies preserve symlinks as symlinks (never follow them) so a
    symlink nested inside an otherwise-legitimate source folder can't be used
    to pull content from outside the allowed browse roots into the library.
    Original filenames are preserved verbatim for a folder source (unlike the
    browser-upload path, these are real host filenames, not untrusted
    client-supplied strings — sanitizing them would also break disc-pointer
    files like .cue that reference sibling files by exact name).
    """
    kind = "folder" if source.is_dir() else "file"
    base_title = (title or source.stem.replace("-", " ").title()).strip() or "import"
    slug = unique_slug(base_title, lambda s: (media_root / s).exists())
    media_root.mkdir(parents=True, exist_ok=True)
    dest_dir = resolve_under(media_root, slug)

    try:
        if kind == "file":
            dest_dir.mkdir(parents=True, exist_ok=False)
            dest_path = resolve_under(dest_dir, sanitize_filename(source.name))
            shutil.copy2(str(source), str(dest_path))
            paths = [dest_path]
        else:
            shutil.copytree(str(source), str(dest_dir), symlinks=True)
            paths = [p for p in dest_dir.rglob("*") if p.is_file() and not p.is_symlink()]
        total_bytes = sum(p.stat().st_size for p in paths)
    except Exception:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise

    if total_bytes > DEFAULT_MAX_BYTES:
        # Defensive re-check: source_size() already gated this in the route
        # before the copy started, but the source could have grown mid-copy.
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise HTTPException(status_code=413, detail="Import exceeds the maximum allowed size.")

    return cu.ReassembledUpload(
        kind=kind, title=base_title, dest_dir=dest_dir, paths=paths, total_bytes=total_bytes,
    )


def delete_source(source: Path) -> str | None:
    """Delete the original source after a confirmed successful import.

    Never raises — the import already succeeded by the time this runs; a
    failed cleanup of the original is logged and returned as a warning string
    (surfaced to the caller in the result), not an error that would make the
    already-successful import look like it failed.
    """
    try:
        if source.is_dir():
            shutil.rmtree(source)
        else:
            source.unlink()
        return None
    except OSError as exc:
        logger.warning("Could not delete original source '%s' after import: %s", source, exc)
        return f"Import succeeded, but the original could not be deleted: {exc}"


def import_inline(
    source: Path, title: str, media_root: Path, db: Session, delete_original: bool
) -> dict:
    reasm = stage_from_source(source, title, media_root)
    result = upload_finalize.finalize_reassembled(reasm, media_root, db)
    if delete_original:
        error = delete_source(source)
        if error:
            result["delete_original_error"] = error
    return result


def import_background(
    source_path: str, title: str, media_root: str, job_id: str, delete_original: bool,
) -> None:
    """BackgroundTask entry: own DB session, report to core.jobs, never raise."""
    from backend.core import jobs
    from backend.core.database import get_engine

    db = Session(get_engine())
    source = Path(source_path)
    root = Path(media_root)
    try:
        jobs.update(job_id, progress=0.1, message="Copying into library…")
        reasm = stage_from_source(source, title, root)
        jobs.update(job_id, progress=0.6, message="Importing…")
        result = upload_finalize.finalize_reassembled(reasm, root, db)
        if delete_original:
            error = delete_source(source)
            if error:
                result["delete_original_error"] = error
        jobs.complete(job_id, result=result, message=f"Added \"{result.get('title', 'import')}\".")
    except Exception as exc:  # noqa: BLE001 — background tasks must not propagate
        logger.exception("Background path import failed: source=%s", source)
        db.rollback()
        jobs.fail(job_id, str(exc))
    finally:
        db.close()
