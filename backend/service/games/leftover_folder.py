"""Decide whether an uploaded folder is a re-upload of a leftover library folder.

A folder already under the games root with no DB row (a leftover, for example
games/armored-core-usa holding the .chd plus its cover) must be indexed in
place, never copied again next to itself. This module answers one question for
folder_ingest: "does every anchor file of this upload match a file in a single
untracked leftover folder, and is that folder safe to adopt?" It only reads. It
never writes, moves or deletes anything, and it never hashes: the match comes
from media_dup_index through find_existing_duplicate, which has already
compared size and SHA-256 once per file.

Adoption itself (DB rows only, via the directory branch or _prepare_multi_disc)
stays in folder_ingest and service.games.items.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.core.logger import get_logger
from backend.models.game import GameItem
from backend.service.games import items as lib_svc

logger = get_logger(__name__)

# Disc images and pointers only. A loose-file PC folder is not adopted on a
# single .exe/.zip match: shared installer stubs make one equal file a weak
# signal, and a wrong adoption discards the upload.
ADOPTION_ANCHOR_EXTS: frozenset[str] = frozenset({".gdi", ".cue", ".iso", ".chd", ".xiso"})


def pick_single_disc_anchor(staging_dir: Path) -> Path | None:
    """The staged file the directory branch would launch, when it is a disc
    image or pointer. None means there is nothing to match on."""
    anchor = lib_svc._pick_folder_executable(staging_dir)
    if anchor is not None and anchor.suffix.lower() in ADOPTION_ANCHOR_EXTS:
        return anchor
    return None


def lookup_matches(anchors: list[Path], games_root: Path) -> list[Path]:
    """One find_existing_duplicate call per anchor, in order, stopping at the
    first miss (an all-or-nothing caller gains nothing from hashing the rest).
    The result is shorter than *anchors* exactly when some anchor has no match.
    """
    from backend.service.utils.upload_utils import find_existing_duplicate

    matches: list[Path] = []
    for anchor in anchors:
        match = find_existing_duplicate(games_root, anchor, anchor.stat().st_size)
        if match is None:
            break
        matches.append(match)
    return matches


def _same_data_size(staged: Path, existing: Path) -> bool:
    """Stat-only guard for .cue/.gdi anchors, where only the small pointer file
    is hashed: the summed size of the tracks each one references must agree."""
    return lib_svc._disc_data_size(staged) == lib_svc._disc_data_size(existing)


def _refuse_symlinked_entries(folder: Path) -> None:
    """409 when *folder* or any direct entry of it is a symlink."""
    try:
        entries = list(folder.iterdir())
    except OSError:
        entries = []
    lib_svc._refuse_symlinks(folder, *entries)


def _is_live_leaf(path: Path, db: Session) -> bool:
    return db.query(GameItem).filter(GameItem.file_path == str(path)).first() is not None


def _shared_folder(matches: list[Path]) -> Path | None:
    """The one folder holding every distinct match, else None."""
    if len(set(matches)) != len(matches):
        return None
    parents = {m.parent for m in matches}
    return parents.pop() if len(parents) == 1 else None


def _is_direct_child(folder: Path, games_root: Path) -> bool:
    try:
        lib_svc._require_direct_child(folder, games_root)
    except HTTPException:
        return False
    return True


def find_adoptable_folder(
    anchors: list[Path],
    matches: list[Path],
    staging_dir: Path,
    games_root: Path,
    db: Session,
) -> Path | None:
    """The leftover folder to index in place, or None to import as a new folder.

    Returns a folder only when every anchor has a match, all matches are
    distinct files in one folder, that folder is a direct child of *games_root*
    outside the staging dir, no DB row tracks it, and the pointer data sizes
    agree. Anything short of that returns None (a partial or cross-folder match
    never repoints a single file).

    Raises:
        HTTPException(409): the folder or one of its direct entries is a symlink.
    """
    if not matches or len(matches) != len(anchors):
        return None
    folder = _shared_folder(matches)
    if folder is None:
        logger.info("Upload not adopted: matches span several folders or repeat a file")
        return None
    staging = staging_dir.resolve()
    if folder == staging or folder.is_relative_to(staging):
        return None
    if not _is_direct_child(folder, games_root):
        return None
    if lib_svc._folder_is_db_tracked(folder, db) or any(_is_live_leaf(m, db) for m in matches):
        return None
    _refuse_symlinked_entries(folder)
    if not all(_same_data_size(a, m) for a, m in zip(anchors, matches)):
        return None
    return folder
