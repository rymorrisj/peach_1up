"""Folder → library-collection ingest logic.

Extracted from the upload-folder route so both the (removed) synchronous route
path and the chunked/background finalizer share one implementation. This is a
helper imported by service.uploads.software_games (the orchestration entry
point); it funnels into the shared collection ingester in service.games.items. Every upload,
single disc or multi-disc, becomes a GameItemBundle (single-disc is a
collection-of-one).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.service.games import items as lib_svc
from backend.service.games.items import _ItemAlreadyExists
from backend.service.utils.file_types import all_supported_extensions

# Priority order matches _EXECUTABLE_PRIORITY in profile_builder.py: .gdi > .cue > .chd.
# Shared by detect_disc_files and select_disc_pointer_files so folder uploads and
# "set" uploads classify the same file list as disc-pointers identically.
_DISC_POINTER_EXTS: tuple[str, ...] = (".gdi", ".cue", ".chd")


def detect_disc_files(files: list[Path]) -> list[Path]:
    """Return a sorted list of disc-pointer files (.gdi/.cue/.chd) when 2+ of one
    kind exist (multi-disc signal), else []. Raises 422 when more than one
    disc-pointer format is present (ambiguous, implies different consoles)."""
    groups = {ext: sorted(f for f in files if f.suffix.lower() == ext) for ext in _DISC_POINTER_EXTS}
    present = [ext for ext, group in groups.items() if group]

    if len(present) > 1:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Folder contains more than one disc-pointer format ({', '.join(present)}). "
                "These formats imply different consoles and cannot be mixed in one multi-disc set. "
                "Upload only one format at a time."
            ),
        )

    disc_files = groups[".gdi"] or groups[".cue"] or groups[".chd"]
    if len(disc_files) <= 1:
        return []
    return disc_files


def select_disc_pointer_files(files: list[Path]) -> list[Path]:
    """Order-preserving, companion-aware disc selection for explicit multi-disc
    "set" uploads, where a disc can be more than one file (e.g. .cue + .bin).

    Returns the .gdi/.cue/.chd pointer files in their original (client-declared)
    order when any are present, every other file rides along in the shared
    destination folder unregistered as a companion. Falls back to returning
    *files* unchanged when none of those are present (each file is already its
    own disc, e.g. .iso). Raises 422 for a mixed disc-pointer-format upload,
    same as detect_disc_files, unlike that function, this one does not sort,
    since the caller must preserve the client's declared disc order.
    """
    groups = {ext: [f for f in files if f.suffix.lower() == ext] for ext in _DISC_POINTER_EXTS}
    present = [ext for ext, group in groups.items() if group]

    if len(present) > 1:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Upload contains more than one disc-pointer format ({', '.join(present)}). "
                "These formats imply different consoles and cannot be mixed in one multi-disc set. "
                "Upload only one format at a time."
            ),
        )

    pointer_files = groups[".gdi"] or groups[".cue"] or groups[".chd"]
    return pointer_files if pointer_files else files


def pick_folder_launch_file(files: list[Path]) -> Path:
    """Confirm at least one recognizable launch file exists; raise 422 otherwise.

    This is a pre-flight validation gate only, the specific file it returns is
    not used for launch-file selection (see _EXECUTABLE_PRIORITY in
    profile_builder.py for the order-sensitive picker), so a plain membership
    check against the full supported-extension set is sufficient here.
    """
    supported = all_supported_extensions()
    hit = next((f for f in files if f.suffix.lower() in supported), None)
    if hit:
        return hit
    raise HTTPException(
        status_code=422,
        detail=(
            "No recognizable launch file found in the uploaded folder. "
            f"Expected one of: {', '.join(sorted(supported))}."
        ),
    )


def dedup_disc_anchor(media_root: Path, anchor: Path, db: Session) -> Path:
    """Consult the content-hash index for *anchor* (the disc-1 pointer/media file
    of a multi-disc upload) and repoint at an existing byte-identical file when
    one exists on disk, avoiding a redundant copy, the same treatment a
    ``kind == "file"`` upload already gets via ``find_existing_duplicate``.

    The multi-disc ingest stages carry no existing-file_path guard the way
    ``_prepare_item`` does for single items, so a duplicate that is still a
    live ``GameItem.file_path`` is rejected here with ``_ItemAlreadyExists``
    (same exception the file-kind path raises, caught by the upload route as a
    409) rather than being silently repointed, that would create a second
    tracked row sharing one file_path with an existing collection. Only a
    duplicate that is an *orphan* (physically on disk, not referenced by any
    live item, e.g. left behind after its item was deleted, per
    ``find_existing_duplicate``'s own docstring) is reused.
    """
    from backend.models.game import GameItemBundle, GameItem
    from backend.service.utils.upload_utils import find_existing_duplicate

    duplicate = find_existing_duplicate(media_root, anchor, anchor.stat().st_size)
    if duplicate is None:
        return anchor

    live_leaf = db.query(GameItem).filter(GameItem.file_path == str(duplicate)).first()
    if live_leaf is not None:
        raise _ItemAlreadyExists(db.get(GameItemBundle, live_leaf.game_item_bundle_id))

    anchor.unlink(missing_ok=True)
    return duplicate


def ingest_folder(
    dest_dir: Path, written_paths: list[Path], title: str, db: Session, media_root: Path
):
    """Multi-disc collection when 2+ disc files are present, else a collection-of-one.

    Returns ``(result_type, collection, disc_count)`` where result_type is always
    ``"game_item_bundle"`` and disc_count is the number of discs (1 for a
    collection-of-one). Raises the same 4xx HTTPExceptions as the ingester
    on a duplicate/collision, callers translate those (inline route) or mark the
    job failed (background finalizer).

    This function owns the multi-disc transaction: it drives the ingest stages
    itself and commits. On failure ``_ingest_transaction`` rolls the session
    back and replays the staging stage's undo callables, which is what renames
    ``dest_dir`` back from its slug name so this module's caller
    (``software_games.finalize_reassembled``) can still find and remove it by
    the pre-rename path it holds. The collection-of-one branch below delegates
    to ``_ingest_media_entry``, which runs the identical sequence internally.
    """
    disc_files = detect_disc_files(written_paths)
    if disc_files:
        disc_files[0] = dedup_disc_anchor(media_root, disc_files[0], db)
        clean_title = title.strip()
        undo_ops: list = []
        with lib_svc._ingest_transaction(
            db,
            undo_ops,
            slug_collision_detail=lib_svc.multi_disc_slug_collision_detail(clean_title, disc_files),
        ):
            collection_fields, leaf_rows = lib_svc._prepare_multi_disc(
                disc_files, clean_title, db, staging_dir=dest_dir, undo_stack=undo_ops
            )
            collection = lib_svc._persist_multi_disc_collection(collection_fields, leaf_rows, db)
            db.commit()
        db.refresh(collection)
        return "game_item_bundle", collection, len(disc_files)

    pick_folder_launch_file(written_paths)
    collection = lib_svc._ingest_media_entry(str(dest_dir), title.strip(), db)
    return "game_item_bundle", collection, 1
