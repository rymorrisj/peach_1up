from __future__ import annotations

import re
import shutil
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.constants import PC_ERAS
from backend.models.game import (
    GameItemBundle, GameItemBundleCreate, GameItemBundleUpdate,
    GameItem, GameItemReorder, GameItemUpdate, derive_item_type,
)
from backend.service.utils.confirmation_tokens import consume as _consume
from backend.service.utils.file_types import is_drive_image, file_type_from_path, resolve_media_file_from_directory
from backend.service.utils.path_utils import normalise_path, resolve_under
from backend.service.utils.slug_generator import generate_collection_slug, slugify, unique_slug

if TYPE_CHECKING:  # type-only, keeps smart_media_detector a call-time import
    from backend.service.utils.smart_media_detector.result import ScanResult

_MEDIA_SUFFIXES = {".iso", ".cue", ".exe", ".com", ".zip"}

# A folder rename can transiently fail with WinError 5 (ERROR_ACCESS_DENIED) if
# antivirus, the Windows Search indexer, RPCS3, or an open Explorer/terminal
# window briefly holds the folder (or a file inside it) open right after
# import copies files into it. Retrying the rename itself does no extra file
# I/O, unlike the re-hash avoidance in _prepare_item, so it doesn't widen the
# same AV/indexer lock window that guards against, it just gives a transient
# lock a short, bounded chance to clear.
_FOLDER_RENAME_RETRY_DELAYS: tuple[float, ...] = (0.1, 0.25, 0.5, 1.0)

# Keys in the prepared row that belong to the collection (parent) vs the leaf.
_COLLECTION_COLUMNS = {
    "title", "era", "slug", "sort_title", "category", "description", "publisher",
    "year", "external_game_id", "metadata_source", "content_rating",
    "launch_commands", "launch_review_flagged", "installed", "requires_install",
    "environment_item_id", "profile_item_id", "last_launched_at", "launch_count",
}
_LEAF_COLUMNS = {
    "file_path", "executable_path", "cover_art_path", "file_type",
    "folder_path", "detection_reason", "file_size_bytes", "original_name",
    "folder_owned", "verification_status", "verification_similarity", "sha1",
}


class _ItemAlreadyExists(Exception):
    """Raised by _prepare_item when the media path is already tracked."""
    def __init__(self, collection: GameItemBundle | None):
        self.collection = collection


class _SlugCollision(Exception):
    """Raised when a concurrent insert claimed the same slug between generation and commit."""
    def __init__(self, message: str | None = None):
        super().__init__(message or "Import collided with a concurrent change, please retry.")


# game_item_bundles.slug is the only unique column on this table (see
# ix_game_item_bundles_slug in backend/models/software.py); SQLite reports
# a violation of it as "UNIQUE constraint failed: game_item_bundles.slug"
# on the wrapped driver exception. Matching on that — instead of catching
# every IntegrityError as a slug race — keeps unrelated failures (a NOT NULL
# violation, a bad FK, etc.) from being mislabeled as a retryable collision.
_SLUG_UNIQUE_VIOLATION_MARKER = "game_item_bundles.slug"


def _is_slug_unique_violation(exc: IntegrityError) -> bool:
    return _SLUG_UNIQUE_VIOLATION_MARKER in str(exc.orig)


def _folder_is_db_tracked(folder: Path, db: Session) -> bool:
    """True if *folder* is a live GameItem's owned directory, or contains one.

    Same domain _prepare_item's dir-ingest branch already checks for a live
    duplicate (folder_path exact match, or file_path under it) — reused here
    so a target occupied on disk is only treated as a real collision when
    something in the DB actually still points at it.
    """
    path_str = str(folder)
    if db.query(GameItem).filter(GameItem.folder_path == path_str).first() is not None:
        return True
    return db.query(GameItem).filter(GameItem.file_path.like(path_str + "/%")).first() is not None


def _reconcile_folder_to_slug(
    folder: Path, slug: str, db: Session, *, undo_stack: list | None = None
) -> Path:
    """Rename *folder* so its basename is literally *slug*, in the same parent.

    Every ingest path that owns a dedicated on-disk directory must call this
    once its DB slug is final, so the on-disk folder name and the URL-facing
    slug can never diverge — regardless of which uniqueness domain (filesystem
    existence vs. DB row) produced the directory's original name. No-ops if
    *folder* is already named *slug*.

    If the target path is already occupied on disk but nothing in the DB
    tracks it (an orphaned leftover directory, e.g. from a previous failed or
    partial import), that's not a real collision — a fresh slug is generated
    via unique_slug and the rename proceeds against that instead, the same
    disambiguation _prepare_item's file-ingest branch already applies to a
    dest-path collision that turns out not to be a tracked duplicate. Only a
    target that IS DB-tracked is a genuine collision, since silently picking
    a different slug there would just rename next to someone else's live data
    instead of surfacing the conflict.

    Raises:
        HTTPException(400): slug produces an invalid/escaping target path
            (defense-in-depth — slugify() already guarantees [a-z0-9-] only).
        HTTPException(409): the target path is DB-tracked by a different item,
            a real collision, not a self-rename or an orphaned directory.
        HTTPException(500): the OS-level rename itself failed after retrying
            through _FOLDER_RENAME_RETRY_DELAYS (permissions, file lock, AV
            scan). Fails loud rather than leaving the DB slug and on-disk
            folder name silently mismatched.
    """
    try:
        target = resolve_under(folder.parent, slug)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Slug-based folder name is invalid: {exc}")
    if target == folder.resolve():
        return folder
    if target.exists():
        if _folder_is_db_tracked(target, db):
            raise HTTPException(
                status_code=409,
                detail=f"A folder named '{slug}' already exists in the media library.",
            )
        slug = unique_slug(
            slug,
            lambda s: (folder.parent / s).exists() or _folder_is_db_tracked(folder.parent / s, db),
        )
        try:
            target = resolve_under(folder.parent, slug)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Slug-based folder name is invalid: {exc}")
    rename_exc: OSError | None = None
    for delay in (0.0, *_FOLDER_RENAME_RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            folder.rename(target)
            rename_exc = None
            break
        except OSError as exc:
            rename_exc = exc
    if rename_exc is not None:
        raise HTTPException(
            status_code=500,
            detail=f"Could not rename media folder to match its slug '{slug}': {rename_exc}",
        )
    if undo_stack is not None:
        undo_stack.append(lambda _o=folder, _n=target: _n.rename(_o) if _n.exists() else None)
    return target


def _rewrite_paths_after_folder_rename(
    row: dict, fields: tuple[str, ...], old_root: Path, new_root: Path, log,
) -> None:
    """Rewrite every path in *row* that lived under *old_root* to the same
    relative location under *new_root*, after a folder rename. Never raises —
    a field that can't be rewritten keeps its stale pre-rename value and is
    logged loudly, since the file itself moved regardless of whether the DB
    row is updated to reflect it."""
    for field in fields:
        val = row.get(field)
        if not val:
            continue
        try:
            field_path = Path(val)
            if field_path == old_root or field_path.is_relative_to(old_root):
                row[field] = str(new_root / field_path.relative_to(old_root))
        except (ValueError, TypeError) as exc:
            log.warning(
                "Could not rewrite '%s' after folder rename (%s -> %s): %s. "
                "Field will keep its stale pre-rename value: %s",
                field, old_root, new_root, exc, val,
            )


def best_detect_path(folder: Path, executable_path: str | None) -> Path:
    if executable_path and Path(executable_path).suffix.lower() != ".img":
        return Path(executable_path)
    # PS3 folders (either shape: PS3_DISC.SFB disc dump, or an installed/
    # extracted dev_hdd0/game/<ID>/-style folder with no SFB marker) resolve
    # via the shared resolver instead of this function re-deriving the shape
    # itself. The folder itself, not the nested EBOOT.BIN, is returned as the
    # detection target: only directory_detect.py's structural PS3 check
    # recognizes either shape (a bare EBOOT.BIN carries no signal once
    # suffix-dispatched as a generic .bin file), and the folder is also the
    # launch target (mirrors rpcs3.launch()'s own is_dir() handling), so this
    # must run before the xex/generic-extension resolution below can apply.
    from backend.service.utils.smart_media_detector.directory_detect import resolve_ps3_target, resolve_xex_target
    ps3_target = resolve_ps3_target(folder)
    if ps3_target is not None:
        return ps3_target.launch_path
    # Extracted Xbox 360 XEX folders can contain multiple top-level .xex
    # files. Resolve those first, before the generic top-level scan below,
    # so the same file is always chosen deterministically (exact
    # default.xex, else alphabetically first) instead of whatever order
    # the generic scan's directory iteration happens to return.
    xex_target = resolve_xex_target(folder)
    if xex_target is not None:
        return xex_target.launch_path
    from backend.service.utils.file_types import all_supported_extensions
    all_exts = _MEDIA_SUFFIXES | all_supported_extensions()
    folder_name = folder.name
    try:
        hit = next(
            (
                f for f in folder.iterdir()
                if f.is_file() and f.suffix.lower() in all_exts and not is_drive_image(f, folder_name)
            ),
            None,
        )
    except OSError:
        hit = None
    return hit if hit is not None else folder


def _collection_for_leaf(leaf: GameItem | None, db: Session) -> GameItemBundle | None:
    if leaf is None:
        return None
    return db.get(GameItemBundle, leaf.game_item_bundle_id)


# ---------------------------------------------------------------------------
# The ingest pipeline: validate_source -> detect -> stage_files -> persist.
#
# Every ingest shape (single file, adopted directory, multi-disc set) runs the
# same four stages in the same order, and the caller owns the transaction in
# every case (see _ingest_transaction). The stages are deliberately separated
# by what they are allowed to touch:
#
#   validate_source  reads the filesystem and the DB, writes nothing.
#   detect           reads the filesystem, writes nothing at all. Its entire
#                    output is the _Detection record below, so a later stage
#                    never has to re-run detection to recover a value.
#   stage_files      performs every filesystem side effect (mkdir/move/rename)
#                    and picks the cover art and launch target, pushing an
#                    undo callable onto the caller's undo stack for each
#                    mutation it makes. Reads the DB, never writes it.
#   persist          adds/flushes ORM rows only. Never commits, never touches
#                    the filesystem.
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class _SourceRef:
    """A validated ingest source: an existing, normalised path that is either a
    directory or a file, and is not an OS environment image."""
    path: Path
    is_dir: bool


@dataclass(slots=True, frozen=True)
class _Detection:
    """Everything the detect stage produces. Nothing downstream of detect may
    re-derive any of these by touching the filesystem again.

    scan:
        The *winning* detection pass. For a directory this is the era-narrowed
        second pass when that pass identified an era, otherwise the broad
        first pass. era, detection_reason and requires_install are all read
        from this one record, so they can never come from different passes.
    detect_path:
        The path ``scan`` was produced from, kept for diagnostics and to let
        the era-narrowed pass decide whether re-detection is needed at all.
    media_path:
        What becomes ``file_path`` on the leaf, and the target classify(),
        detect_rating() and the size probe run against. For a PS3 disc folder
        this is the folder itself, deliberately (see _detect_directory_source).
    executable_path:
        The launch target discovered inside a folder, or the file itself for a
        single-file source. None when a folder holds no recognizable launch
        file.
    """
    scan: ScanResult
    detect_path: Path
    media_path: Path
    executable_path: Path | None


# ── Stage 1: validate_source ────────────────────────────────────────────────


def _validate_source(media_path: str, db: Session) -> _SourceRef:
    """Normalise *media_path*, confirm it exists and is a file or a directory,
    and reject OS environment images.

    Raises:
        HTTPException(400): malformed, missing, or neither-file-nor-directory.
        HTTPException(409): the path is an Environment base or working image.
    """
    from backend.models.environment import EnvironmentItem

    try:
        media_src = normalise_path(media_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"media_path: {e}")

    if not media_src.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {media_path}")

    incoming_norm = media_src.as_posix()

    for base_path, working_path in db.query(
        EnvironmentItem.base_image_path, EnvironmentItem.working_image_path
    ).all():
        if (base_path and Path(base_path).resolve().as_posix() == incoming_norm) or (
            working_path and Path(working_path).resolve().as_posix() == incoming_norm
        ):
            raise HTTPException(
                status_code=409,
                detail="Path is an OS environment image and cannot be added as a library item.",
            )

    if media_src.is_dir():
        return _SourceRef(path=media_src, is_dir=True)
    if media_src.is_file():
        return _SourceRef(path=media_src, is_dir=False)
    raise HTTPException(
        status_code=400,
        detail=f"Path is not a file or directory: {media_path}",
    )


def _guard_directory_source(folder: Path, db: Session, games_root_str: str) -> None:
    """Directory-source admission checks: containment under the games library
    root, and the live-duplicate guard (an exact folder_path match, or any
    tracked file_path underneath it).

    Kept out of _validate_source because it is directory-shaped only, the
    file-shaped equivalent is inseparable from destination-path derivation and
    lives in _stage_file_source.

    Raises:
        HTTPException(400): folder is outside library/software/games/.
        _ItemAlreadyExists: the folder, or something inside it, is tracked.
    """
    if games_root_str:
        from backend.service.utils.path_utils import library_domain_root
        media_root = library_domain_root("games")
        if not (folder == media_root or folder.is_relative_to(media_root)):
            raise HTTPException(
                status_code=400,
                detail="Folder is outside the games library (library/software/games/).",
            )

    existing = db.query(GameItem).filter(GameItem.folder_path == str(folder)).first()
    if existing:
        raise _ItemAlreadyExists(_collection_for_leaf(existing, db))
    sub = db.query(GameItem).filter(GameItem.file_path.like(str(folder) + "/%")).first()
    if sub:
        raise _ItemAlreadyExists(_collection_for_leaf(sub, db))


# ── Stage 2: detect ─────────────────────────────────────────────────────────


def _pick_folder_executable(folder: Path) -> Path | None:
    """Highest-priority launchable file directly inside *folder*, or None.

    Read-only. Lives in the detect stage rather than the staging stage because
    best_detect_path() takes it as an input, but its value is also what the
    staging stage writes to executable_path, so it is carried on _Detection
    instead of being computed twice.
    """
    from backend.service.utils.profile_builder import _EXECUTABLE_PRIORITY

    folder_name = folder.name
    try:
        candidates = [
            f for f in folder.iterdir()
            if f.is_file() and not is_drive_image(f, folder_name)
        ]
    except OSError:
        candidates = []
    for ext in _EXECUTABLE_PRIORITY:
        for f in candidates:
            if f.suffix.lower() == ext:
                return f
    return None


def _detect_directory_source(
    folder: Path,
    *,
    user_override_era: str | None,
    era_hint: str | None,
    log,
) -> _Detection:
    """Detect stage for a directory source. Performs no filesystem writes.

    Two passes, sequential and self-contained:

    1. Broad pass against best_detect_path()'s choice (the discovered launch
       file, else a PS3/XEX structural resolution, else the first supported
       file, else the folder itself).
    2. Era-narrowed pass. The era used to *select* a file is not the era this
       function returns: a user override wins, then the caller's scan-preview
       hint, then pass 1's own detection. That selection era only ever picks
       which file inside a multi-format folder is authoritative;
       resolve_media_file_from_directory() produces it, and its output becomes
       media_path whether or not the narrowed pass then identifies an era.
       Re-detection is skipped when the resolver picked the same file pass 1
       already scanned, which avoids hashing a possibly large file twice and
       widening the AV/indexer lock window right before the folder rename.

    The narrowed pass replaces ``scan`` only when it actually identified an
    era. Previously the second pass's ScanResult was bound unconditionally
    while era/reason were kept from pass 1, so a folder whose era-specific
    file failed detection persisted pass 1's era alongside pass 2's
    requires_install (always False when era is None). era, detection_reason
    and requires_install now always come from the same pass.
    """
    from backend.service.utils.smart_media_detector import detect as _smart_detect

    executable = _pick_folder_executable(folder)
    detect_path = best_detect_path(folder, str(executable) if executable is not None else None)
    scan = _smart_detect(detect_path)
    if scan.era is None and scan.warnings:
        log.warning("Media detection warnings for '%s': %s", detect_path, scan.warnings)

    media_path = folder
    resolve_era = user_override_era or era_hint or scan.era
    if resolve_era and resolve_era != "unknown":
        try:
            resolved_media = resolve_media_file_from_directory(folder, resolve_era)
            media_path = resolved_media
            if resolved_media != detect_path:
                narrowed = _smart_detect(resolved_media)
                if narrowed.era is not None:
                    scan = narrowed
                    detect_path = resolved_media
                elif narrowed.warnings:
                    log.warning(
                        "Media detection warnings for '%s': %s", resolved_media, narrowed.warnings
                    )
        except ValueError as exc:
            if resolve_era == "ps3":
                # ps3's supported_media is .iso only (config/eras.yaml), so
                # this resolver always raises for an extracted disc folder,
                # that is expected, not a failure: there is no single file
                # to resolve to, the folder itself is the correct launch
                # target (matches rpcs3.launch()'s own is_dir() handling),
                # so media_path is deliberately left pointing at the folder.
                # Only warn when the folder isn't valid PS3 content either,
                # i.e. resolution has no other explanation.
                from backend.service.utils.smart_media_detector.directory_detect import resolve_ps3_target
                if resolve_ps3_target(folder) is None:
                    log.warning(
                        "Could not find EBOOT.BIN in expected PS3 folder structure "
                        "at '%s' (expected USRDIR/EBOOT.BIN, optionally under PS3_GAME/).",
                        folder,
                    )
            else:
                log.warning("Could not resolve media file in '%s': %s", folder, exc)

    return _Detection(
        scan=scan, detect_path=detect_path, media_path=media_path, executable_path=executable,
    )


def _detect_file_source(media_file: Path, log) -> _Detection:
    """Detect stage for a single-file source. Performs no filesystem writes.

    Single-file ingest (e.g. a loose console ROM/ISO with no companion .exe to
    discover) has no folder to scan for a launch file the way a directory
    source does. The item's own media file *is* the launch target, so it is
    returned as executable_path directly. That is a "launch target" field, not
    strictly a "discovered .exe" field, and must not be left null for a
    launchable item. Mirrors the multi-disc path, which does the same for
    every disc.
    """
    from backend.service.utils.smart_media_detector import detect as _smart_detect

    scan = _smart_detect(media_file)
    if scan.era is None and scan.warnings:
        log.warning("Media detection warnings for '%s': %s", media_file, scan.warnings)
    return _Detection(
        scan=scan, detect_path=media_file, media_path=media_file, executable_path=media_file,
    )


# ── Stage 3: stage_files ────────────────────────────────────────────────────


def _stage_directory_source(row: dict, folder: Path, detection: _Detection) -> Path:
    """Staging stage for a directory source: adopt *folder* in place and write
    the detect stage's choices onto *row*.

    A directory source is adopted where it already sits, so this stage makes no
    filesystem mutation at all and pushes nothing onto an undo stack. The only
    rename a directory source ever sees is the slug reconciliation shared by
    every owned-folder path, which runs later and registers its own undo.

    Returns the owned folder root.
    """
    from backend.service.utils.profile_builder import _find_cover

    row["folder_path"] = str(folder)
    row["folder_owned"] = True
    row["file_path"] = str(detection.media_path)
    row["executable_path"] = (
        str(detection.executable_path) if detection.executable_path is not None else None
    )

    cover = _find_cover(folder)
    if cover:
        row["cover_art_path"] = str(cover)

    return folder


def _stage_file_source(
    row: dict, media_src: Path, db: Session, *, games_root_str: str, undo_stack: list | None,
) -> Path | None:
    """Staging stage for a single-file source: move or rename the file into its
    canonical per-item folder under the games library, or adopt it in place when
    SOFTWARE_PATH is unset.

    This is the only stage in the whole pipeline that mutates the filesystem
    before the slug reconciliation, and every mutation it makes registers an
    undo callable on *undo_stack*. It also carries the file-shaped duplicate
    guard, which cannot be lifted into _validate_source because it depends on
    the destination path this function derives.

    Returns the owned folder root, or None when SOFTWARE_PATH is unset (no
    dedicated directory was created, so there is nothing to reconcile).
    """
    from backend.service.utils.profile_builder import _find_cover

    if not games_root_str:
        existing_leaf = db.query(GameItem).filter(
            GameItem.file_path == str(media_src)
        ).first()
        if existing_leaf:
            raise _ItemAlreadyExists(_collection_for_leaf(existing_leaf, db))
        # No SOFTWARE_PATH configured: there is no dedicated per-item directory
        # to create, so folder_path here is just the source file's parent —
        # a directory this ingest did not create and may share with
        # unrelated files or other library items. folder_owned=False is
        # load-bearing: it tells _delete_leaf_media_folders to never rmtree
        # this path, only ever unlink the tracked file itself.
        row["folder_path"] = str(media_src.parent)
        row["folder_owned"] = False
        return None

    from backend.service.utils.path_utils import library_domain_root
    _games_root = library_domain_root("games")
    _src_parent = media_src.parent

    # Slugify the destination folder name (matches the shared slugify()
    # every other ingest path uses, service.uploads.core.reassemble(),
    # path_import.stage_from_source(), and the directory branch).
    # This is deliberately the plain slug, not unique_slug(): the
    # canonical folder name is deterministic from the stem, and an
    # existing folder at that path is a real target to rename into or
    # move into (handled below), not a collision to suffix away from.
    dest_folder = _games_root / slugify(media_src.stem)
    dest = dest_folder / media_src.name

    # Duplicate check, source side: file_path is always written as
    # str(Path(...).resolve()) by this same pipeline, so an exact match
    # against media_src itself means this literal path is already tracked.
    existing_leaf = db.query(GameItem).filter(
        GameItem.file_path == str(media_src)
    ).first()
    if existing_leaf:
        raise _ItemAlreadyExists(_collection_for_leaf(existing_leaf, db))

    # Duplicate check, destination side: dest is derived from the
    # filename stem alone, so an existing tracked leaf at dest does not
    # by itself mean the incoming file is a duplicate, it only means
    # some file already occupies that slugified name. Two different
    # files that happen to share a generic stem (setup.exe, disc.iso)
    # would otherwise collide here and get incorrectly flagged as
    # already-in-library. Disambiguate on content, using the same
    # hash-backed lookup find_existing_duplicate/media_dup_index already
    # use for "is this content already in the library", instead of a
    # second, independent duplicate check.
    dest_leaf = db.query(GameItem).filter(
        GameItem.file_path == str(dest)
    ).first()
    if dest_leaf is not None:
        from backend.service.utils.upload_utils import find_existing_duplicate

        duplicate = find_existing_duplicate(
            _games_root, media_src, media_src.stat().st_size
        )
        if duplicate is not None:
            # Genuinely the same content, reuse behavior applies.
            raise _ItemAlreadyExists(_collection_for_leaf(dest_leaf, db))
        # Different content, same slugified stem: a naming collision,
        # not a duplicate. Give the incoming file its own destination
        # instead of raising or overwriting dest_leaf's file.
        dest_folder = _games_root / unique_slug(
            media_src.stem,
            lambda s: (_games_root / s).exists()
            or db.query(GameItem).filter(
                GameItem.file_path == str(_games_root / s / media_src.name)
            ).first() is not None,
        )
        dest = dest_folder / media_src.name

    # If the file already lives in a direct subfolder of games_root that
    # only needs renaming to match the canonical slug, rename in place
    # instead of creating a new folder and moving the file out.
    if (
        _src_parent.resolve() != _games_root
        and _src_parent.parent.resolve() == _games_root
        and not dest_folder.exists()
    ):
        _src_parent.rename(dest_folder)
        if undo_stack is not None:
            undo_stack.append(lambda _o=_src_parent, _n=dest_folder: _n.rename(_o) if _n.exists() else None)
        row["folder_path"] = str(dest_folder)
        row["folder_owned"] = True
        row["file_path"] = str(dest)
    else:
        # dest_folder may already exist here (the rename-in-place branch
        # above only fires when it doesn't). Reusing it blind via
        # exist_ok=True would silently write into a stale, tampered, or
        # leftover directory. Only the exact target file is a known-safe
        # thing to find already present (crash-after-move retry, handled
        # by the dest.exists() size check below) — anything else present
        # is unexpected and must fail loud rather than be picked around.
        if dest_folder.exists() and any(f != dest for f in dest_folder.iterdir()):
            raise HTTPException(
                status_code=409,
                detail=f"Directory '{dest_folder}' already exists and contains unexpected files; refusing to reuse it.",
            )
        dest_folder.mkdir(parents=True, exist_ok=True)
        row["folder_path"] = str(dest_folder)
        row["folder_owned"] = True

        if dest.exists():
            if dest.stat().st_size == media_src.stat().st_size:
                # Identical file already in place — reuse without re-copy
                row["file_path"] = str(dest)
            else:
                raise HTTPException(
                    status_code=409,
                    detail=f"A different file named '{media_src.name}' already exists in '{dest_folder}'.",
                )
        else:
            if media_src.resolve() == dest.resolve():
                row["file_path"] = str(dest)
            else:
                shutil.move(str(media_src), str(dest))
                if undo_stack is not None:
                    undo_stack.append(lambda _s=media_src, _d=dest: shutil.move(str(_d), str(_s)) if _d.exists() else None)
                row["file_path"] = str(dest)

    cover = _find_cover(dest_folder)
    if cover:
        row["cover_art_path"] = str(cover)

    return dest_folder


def _reconcile_owned_folder(row: dict, owned_root: Path | None, db: Session, undo_stack, log) -> None:
    """Rename the ingest-owned folder to match row["slug"], then rewrite every
    path field that lived under it.

    Covers both directory ingest (folder named from the source directory) and
    file ingest with SOFTWARE_PATH configured (folder named from the file's
    stem); the two start from different source strings and different uniqueness
    checks, so without this step the folder name and row["slug"] can diverge.
    No-op when this ingest owns no directory.
    """
    if owned_root is None:
        return
    slug_folder = _reconcile_folder_to_slug(owned_root, row["slug"], db, undo_stack=undo_stack)
    row["slug"] = slug_folder.name
    if slug_folder != owned_root:
        _rewrite_paths_after_folder_rename(
            row, ("folder_path", "file_path", "executable_path", "cover_art_path"),
            owned_root, slug_folder, log,
        )


# ── Stage 3.5: shared row build (the persist-adjacent stage) ────────────────


def _target_size(path: Path) -> int | None:
    """Byte size to persist for one leaf target, or None when it cannot be
    determined.

    Directories (a PS3 disc folder is a legitimate leaf target) have no
    meaningful size and resolve to None rather than the directory entry's own
    stat size. Everything else goes through _disc_data_size, so a .cue/.gdi
    pointer reports the summed size of the tracks it references instead of the
    few hundred bytes of the pointer file itself. Single-file ingest previously
    used a bare stat() here and multi-disc used _disc_data_size; the two now
    agree.
    """
    try:
        if path.is_dir():
            return None
        return _disc_data_size(path)
    except OSError:
        return None


def _finalize_row_fields(
    title: str,
    target_paths: list[Path],
    scan: ScanResult,
    db: Session,
    *,
    user_override_era: str | None = None,
    override_profile_item_id: int | None = None,
) -> tuple[dict, list[dict]]:
    """Resolve era, then everything that depends on it, for one collection and
    its N leaf targets. Shared by single-item and multi-disc ingest so neither
    computes any of it independently.

    Era resolution has two sources, in precedence order:
        1. ``user_override_era``, a genuine user selection. Sets
           ``detection_reason`` to "Selected by user during import".
        2. ``scan``, the detect stage's winning pass against the file on disk.

    The scan-preview era a client echoes back at import time is deliberately
    not a source here. It is never re-verified against the file, so a file that
    changed between scan and import, or a stale/incorrect client value, would
    persist silently. The detect stage always runs a real pass regardless, so
    trusting that result costs nothing extra. That echoed value still reaches
    the detect stage as ``era_hint``, where it only ever selects which file
    inside a multi-format folder is authoritative.

    ``target_paths`` carries one entry per leaf: exactly one for a
    collection-of-one, one per disc for a multi-disc set. classify() runs once
    per target because Redump gives every disc of a set its own dat entry and
    therefore its own sha1; era, requires_install and content_rating are
    collection-level and are resolved once from ``scan`` and target_paths[0].

    Returns ``(collection_fields, [leaf_fields per target])``.
    """
    from backend.service.utils.era_defaults import defaults_for_era, lookup_environment_and_profile
    from backend.service.utils.rating_detect import detect_rating
    from backend.service.utils.smart_media_detector import classify as _classify

    if user_override_era is not None:
        era = user_override_era
        detection_reason = "Selected by user during import"
    elif scan.era is not None:
        era = scan.era
        detection_reason = scan.reason
    else:
        era = "unknown"
        detection_reason = None

    collection_fields: dict = {
        "era": era,
        "requires_install": scan.requires_install,
        "content_rating": detect_rating(str(target_paths[0])) or None,
        "environment_item_id": None,
        "profile_item_id": None,
    }

    if era and era != "unknown":
        _emulator_slug, _profile_era = defaults_for_era(era)
        if _emulator_slug and _profile_era:
            _def_environment_item_id, _def_profile_item_id = lookup_environment_and_profile(
                _emulator_slug, _profile_era, db
            )
            if _def_profile_item_id is not None:
                collection_fields["profile_item_id"] = _def_profile_item_id
            # Environment is strictly PC (doc 02 A5) — a console era must never
            # get environment_item_id populated, even if a system Environment
            # happens to exist for its emulator_slug (e.g. a seeded
            # DuckStation/PS1 row).
            if _def_environment_item_id is not None and era in PC_ERAS:
                collection_fields["environment_item_id"] = _def_environment_item_id

    if override_profile_item_id is not None:
        collection_fields["profile_item_id"] = override_profile_item_id

    # classify() runs after era resolution, not alongside file_type below,
    # since its fuzzy title-match tier needs the final resolved era to scope
    # its search. "unknown" is passed through as None: era is required for
    # classify() to ever reach "mismatch", and an unscoped title search across
    # every platform would make an accidental false-positive match more
    # likely, not less.
    _classify_era = era if era != "unknown" else None

    leaf_fields: list[dict] = []
    for target in target_paths:
        _classify_result = _classify(target, title, _classify_era)
        leaf_fields.append({
            "file_type": file_type_from_path(target),
            "file_size_bytes": _target_size(target),
            "detection_reason": detection_reason,
            "verification_status": _classify_result.status,
            "verification_similarity": _classify_result.similarity,
            "sha1": _classify_result.computed_sha1,
        })

    return collection_fields, leaf_fields


def _prepare_item(
    media_path: str,
    title: str,
    db: Session,
    *,
    used_slugs: set[str] | None = None,
    override_profile_item_id: int | None = None,
    detected_era: str | None = None,
    user_override_era: str | None = None,
    _undo_stack: list | None = None,
) -> dict:
    """
    Run validate_source, detect and stage_files for one media path, without
    writing to the DB, and return a mapping of all column values (collection-
    and leaf-level) for a collection-of-one. The caller runs the persist stage
    (_persist_collection_of_one) and owns the transaction.

    Filesystem side effects (folder creation, file move, slug rename) happen in
    the staging stage only, and each one registers an undo callable on
    ``_undo_stack`` so a caller can replay them in reverse on failure.

    Era resolution lives in _finalize_row_fields and has two sources, in
    precedence order: ``user_override_era``, a genuine user selection, then
    this call's own fresh detection against the file on disk.

    ``detected_era`` is still accepted, but only as a hint the detect stage
    uses when choosing which file inside a multi-format directory to run
    detection against. It never sets the persisted era or detection_reason.
    It used to: the scan importer passed its scan-preview era straight through
    and it won on precedence over this function's own detection. That value is
    echoed back by the client from an earlier request and was never re-checked
    against the file at import time, so a file that changed between scan and
    import, or a client that sent a stale or incorrect value, would silently
    persist under the wrong era. A real detection pass runs unconditionally on
    every call regardless of what the caller passes in, so trusting that fresh
    result instead of the client echo costs nothing extra.

    Raises:
        _ItemAlreadyExists: if this path is already tracked as a library leaf.
        HTTPException: for path or conflict errors.
    """
    from backend.core.logger import get_logger
    from backend.core.settings import get_settings

    log = get_logger(__name__)
    svc = get_settings()
    games_root_str = svc.get("SOFTWARE_PATH", "") or ""

    # Stage 1: validate_source.
    src = _validate_source(media_path, db)
    media_src = src.path

    row: dict = {
        "title": title,
        "era": "unknown",
        "file_path": str(media_src),
        "original_name": media_src.name,
        "slug": None,
        "sort_title": None,
        "category": None,
        "file_type": None,
        "folder_path": None,
        "folder_owned": None,
        "cover_art_path": None,
        "description": None,
        "publisher": None,
        "year": None,
        "external_game_id": None,
        "metadata_source": None,
        "content_rating": None,
        "executable_path": None,
        "launch_commands": None,
        "launch_review_flagged": False,
        "installed": False,
        "requires_install": False,
        "detection_reason": None,
        "environment_item_id": None,
        "profile_item_id": None,
        "last_launched_at": None,
        "launch_count": 0,
        "file_size_bytes": None,
        "verification_status": "unchecked",
        "verification_similarity": None,
        "sha1": None,
    }

    # _owned_folder_root is the directory this ingest owns and created or
    # renamed exclusively for this item, set by the directory branch and by the
    # file branch when SOFTWARE_PATH is configured. It is reconciled to match
    # the DB slug once that slug is final, so folder_owned rows never carry a
    # folder name that differs from their slug regardless of which branch
    # created the directory.
    if src.is_dir:
        # Stage 2: detect. Runs to completion, with zero filesystem writes,
        # before Stage 3 starts. Admission checks come first: they are cheap
        # DB and path work, and there is nothing to gain from detecting
        # against a folder that is already tracked or out of bounds.
        _guard_directory_source(media_src, db, games_root_str)
        detection = _detect_directory_source(
            media_src,
            user_override_era=user_override_era,
            era_hint=detected_era,
            log=log,
        )
        # Stage 3: stage_files.
        _owned_folder_root = _stage_directory_source(row, media_src, detection)
    else:
        # A loose file runs Stage 3 before Stage 2, deliberately. Staging can
        # resolve file_path to an already-present identical file at the
        # destination rather than to the source (the crash-after-move retry
        # case), so detection has to run against whichever file actually ends
        # up tracked, not against the source bytes. A directory source has no
        # equivalent case, which is why it is the branch that detects first.
        _owned_folder_root = _stage_file_source(
            row, media_src, db, games_root_str=games_root_str, undo_stack=_undo_stack,
        )
        detection = _detect_file_source(Path(row["file_path"]), log)
        row["executable_path"] = str(detection.executable_path)

    # Slug, using the in-memory set when batching to avoid N DB round-trips.
    if used_slugs is not None:
        row["slug"] = unique_slug(title, lambda s: s in used_slugs)
        used_slugs.add(row["slug"])
    else:
        row["slug"] = generate_collection_slug(title, db)

    _reconcile_owned_folder(row, _owned_folder_root, db, _undo_stack, log)

    # Stage 3.5: the shared persist-adjacent stage, run against the
    # post-reconciliation paths so classify(), the size probe and the rating
    # scan all see the file where it finally lives.
    collection_fields, leaf_fields = _finalize_row_fields(
        title,
        [Path(row["file_path"])],
        detection.scan,
        db,
        user_override_era=user_override_era,
        override_profile_item_id=override_profile_item_id,
    )
    row.update(collection_fields)
    row.update(leaf_fields[0])

    return row


def _enforce_environment_binding(collection: GameItemBundle) -> None:
    """Environment is strictly PC (doc 02 A5): console items may never carry an environment_item_id.

    PC items may have a null environment_item_id at this point (backfilled later /
    pre-launch-gated — doc 02 part B); only the console+non-null combination is
    rejected here.
    """
    if collection.item_type == "console" and collection.environment_item_id is not None:
        raise HTTPException(
            status_code=422,
            detail="Console software cannot have an environment_item_id; Environment is strictly PC.",
        )


def _persist_collection_of_one(row: dict, db: Session) -> GameItemBundle:
    """Create a GameItemBundle + its single GameItem leaf from a prepared row.

    Flushes both so ids exist and launch/display disk pointers are set to the
    leaf. Does NOT commit — the caller owns the transaction (and any undo of
    filesystem side effects on IntegrityError).
    """
    collection = GameItemBundle(**{k: row[k] for k in _COLLECTION_COLUMNS if k in row})
    _enforce_environment_binding(collection)
    db.add(collection)
    db.flush()

    leaf = GameItem(
        game_item_bundle_id=collection.id,
        disc_number=1,
        **{k: row[k] for k in _LEAF_COLUMNS if k in row},
    )
    db.add(leaf)
    db.flush()

    collection.launch_disk_id = leaf.id
    collection.display_disk_id = leaf.id
    db.add(collection)
    return collection


def _replay_undo(undo_stack: list) -> None:
    """Replay a staging stage's filesystem undo callables in reverse order.

    Best effort by construction: a failed undo must never mask the exception
    that triggered the replay, so an OSError from any single callable is
    swallowed and the remaining callables still run.
    """
    for undo in reversed(undo_stack):
        try:
            undo()
        except OSError:
            pass


@contextmanager
def _ingest_transaction(db: Session, undo_stack: list, *, slug_collision_detail: str | None = None):
    """The one transaction model every ingest shape uses. The caller commits.

    Wrapping the whole prepare-and-persist sequence, not just the persist call,
    is load-bearing: the staging stage performs filesystem moves and renames
    (appended to *undo_stack* as it goes) before the DB is touched at all, so
    ANY exception in either stage has to replay them, not only an IntegrityError
    from a flush. Otherwise an HTTPException or DB error raised during staging,
    after a file had already been moved, would leave the move applied with no DB
    row and no rollback: an orphaned move.

    The caller's own db.commit() belongs inside the block too. A commit can
    still raise (a deferred constraint, a concurrent insert claiming the slug
    between flush and commit), and that failure needs the same rollback and
    undo replay every earlier failure gets.

    A slug unique violation is translated into _SlugCollision so callers can
    surface a retryable 409 instead of a raw driver error;
    *slug_collision_detail* supplies a call-site-specific message, defaulting
    to _SlugCollision's own generic wording.
    """
    try:
        yield
    except IntegrityError as exc:
        db.rollback()
        _replay_undo(undo_stack)
        if _is_slug_unique_violation(exc):
            raise _SlugCollision(slug_collision_detail) from exc
        raise
    except Exception:
        db.rollback()
        _replay_undo(undo_stack)
        raise


def _ingest_media_entry(
    media_path: str,
    title: str,
    db: Session,
    *,
    override_profile_item_id: int | None = None,
) -> GameItemBundle:
    """
    Single shared ingest pipeline: prepare, then persist a collection-of-one.
    Called by the manual add route, the upload finalizer and the path importer.
    Raises _ItemAlreadyExists if the path is already tracked, or _SlugCollision
    if a concurrent insert claimed the generated slug first (rare TOCTOU race).
    """
    undo_ops: list = []
    with _ingest_transaction(db, undo_ops):
        row = _prepare_item(
            media_path, title, db,
            override_profile_item_id=override_profile_item_id,
            _undo_stack=undo_ops,
        )
        collection = _persist_collection_of_one(row, db)
        db.commit()

    db.refresh(collection)
    return collection


_CUE_FILE_RE = re.compile(r'FILE\s+"([^"]+)"', re.IGNORECASE)
_GDI_QUOTED_NAME_RE = re.compile(r'"([^"]+)"')


def _disc_data_size(disc_file: Path) -> int | None:
    """Return the on-disk size represented by *disc_file*.

    For .cue/.gdi pointer files this sums the referenced track/data files
    (parsed from the pointer text itself) instead of the pointer file's own
    size, which is a few hundred bytes regardless of the actual disc size.
    Falls back to the pointer file's own size if no referenced file resolves
    (e.g. non-standard pointer contents) — fail-soft, matching the rest of
    this codebase's detection behavior. .chd is a single self-contained file
    and is sized directly, no parsing needed.
    """
    if disc_file.suffix.lower() not in (".cue", ".gdi"):
        return disc_file.stat().st_size if disc_file.exists() else None

    try:
        with open(disc_file, "rb") as f:
            # cue/gdi pointer files are a few hundred bytes; cap defends against a giant file
            text = f.read(64 * 1024).decode("utf-8", errors="ignore")
    except OSError:
        text = ""

    referenced: list[str] = []
    if disc_file.suffix.lower() == ".cue":
        referenced = _CUE_FILE_RE.findall(text)
    else:  # .gdi — track lines after the leading track-count line
        for line in text.splitlines()[1:]:
            m = _GDI_QUOTED_NAME_RE.search(line)
            if m:
                referenced.append(m.group(1))
            else:
                parts = line.split()
                if len(parts) >= 5:
                    referenced.append(parts[4])

    total = 0
    found_any = False
    for name in referenced:
        candidate = disc_file.parent / name
        if candidate.exists():
            total += candidate.stat().st_size
            found_any = True

    if found_any:
        return total
    return disc_file.stat().st_size if disc_file.exists() else None


def _prepare_multi_disc(
    disc_files: list[Path],
    title: str,
    db: Session,
    *,
    staging_dir: Path | None = None,
    undo_stack: list | None = None,
) -> tuple[dict, list[dict]]:
    """
    Run validate_source, detect and stage_files for a multi-disc set, without
    writing to the DB. Returns ``(collection_fields, [leaf_fields per disc])``
    for _persist_multi_disc_collection. The caller owns the transaction.

    disc_files must be pre-sorted (disc 1 first). Each disc file becomes both
    file_path and executable_path for its leaf.

    Detection runs once, against disc 1 only: every disc of a set shares one
    era, one requires_install and one content rating. Only the hash and title
    check is genuinely per-disc (Redump gives each disc of a set its own dat
    entry and therefore its own sha1), and _finalize_row_fields handles that by
    running classify() once per target.

    staging_dir, when given, is the shared directory the caller staged every
    disc_files entry into (service.uploads.core.reassemble() / path_import's
    stage_from_source(), named via unique_slug() against filesystem
    existence). It is renamed to match this collection's DB slug (generated
    below against DB uniqueness, a different domain) so the two never diverge,
    and that rename registers its undo on *undo_stack* like every other
    staging-stage mutation. Deliberately NOT inferred from
    disc_files[0].parent: dedup_disc_anchor may have already repointed
    disc_files[0] at an unrelated, pre-existing orphan file elsewhere under
    media_root, and renaming *that* file's parent would corrupt a directory
    this ingest doesn't own. Only disc_files entries that actually resolve
    under staging_dir are remapped after the rename; a repointed anchor is left
    untouched. Omitted (None) by direct callers that never staged a dedicated
    directory: reconciliation is skipped entirely in that case, not guessed at.
    """
    from backend.core.logger import get_logger
    from backend.service.utils.profile_builder import _find_cover
    from backend.service.utils.smart_media_detector import detect as _smart_detect

    log = get_logger(__name__)

    # Stage 1: validate_source. There is no path normalisation to do (the
    # caller resolved these off disk itself) but an empty list would otherwise
    # fail as an IndexError several stages later.
    if not disc_files:
        raise HTTPException(
            status_code=422,
            detail="No disc files were resolved for this multi-disc import.",
        )

    # Stage 2: detect. No filesystem writes.
    scan = _smart_detect(disc_files[0])
    if scan.era is None and scan.warnings:
        log.warning("Media detection warnings for '%s': %s", disc_files[0], scan.warnings)

    # Stage 3: stage_files.
    slug = generate_collection_slug(title, db)
    staged_dir = staging_dir
    if staging_dir is not None:
        staged_dir = _reconcile_folder_to_slug(staging_dir, slug, db, undo_stack=undo_stack)
        slug = staged_dir.name
        if staged_dir != staging_dir:
            disc_files = [
                staged_dir / f.relative_to(staging_dir) if f.is_relative_to(staging_dir) else f
                for f in disc_files
            ]
    cover = _find_cover(staged_dir if staged_dir is not None else disc_files[0].parent)

    # Stage 3.5: the shared persist-adjacent stage.
    collection_fields, leaf_fields = _finalize_row_fields(title, disc_files, scan, db)
    collection_fields["title"] = title
    collection_fields["slug"] = slug

    leaf_rows: list[dict] = []
    for disc_number, (disc_file, fields) in enumerate(zip(disc_files, leaf_fields), start=1):
        leaf_rows.append({
            **fields,
            "file_path": str(disc_file),
            "executable_path": str(disc_file),
            "original_name": disc_file.name,
            "folder_path": str(disc_file.parent),
            "cover_art_path": str(cover) if disc_number == 1 and cover else None,
            # All disc files of a "set" upload are written together into one
            # unique-slugged staging directory dedicated to this collection
            # (see service.uploads.software_games.finalize_reassembled), safe
            # to rmtree.
            "folder_owned": True,
        })

    return collection_fields, leaf_rows


def _persist_multi_disc_collection(
    collection_fields: dict, leaf_rows: list[dict], db: Session
) -> GameItemBundle:
    """Create a GameItemBundle plus one GameItem leaf per disc from prepared
    rows, the N-leaf counterpart to _persist_collection_of_one.

    Flushes so ids exist and the launch/display disk pointers can be set to
    disc 1. Does NOT commit: the caller owns the transaction (and any undo of
    filesystem side effects on failure).
    """
    collection = GameItemBundle(
        **{k: v for k, v in collection_fields.items() if k in _COLLECTION_COLUMNS}
    )
    _enforce_environment_binding(collection)
    db.add(collection)
    db.flush()

    leaves: list[GameItem] = []
    for disc_number, leaf_row in enumerate(leaf_rows, start=1):
        leaf = GameItem(
            game_item_bundle_id=collection.id,
            disc_number=disc_number,
            **{k: v for k, v in leaf_row.items() if k in _LEAF_COLUMNS},
        )
        db.add(leaf)
        leaves.append(leaf)
    db.flush()

    collection.launch_disk_id = leaves[0].id
    collection.display_disk_id = leaves[0].id
    db.add(collection)
    return collection


def multi_disc_slug_collision_detail(title: str, disc_files: list[Path]) -> str:
    """Message for a slug race during a multi-disc ingest, shared by both call
    sites so the two report the collision identically."""
    anchor = disc_files[0].name if disc_files else "unknown"
    return (
        f"Import collided with a concurrent change while adding '{title}' "
        f"(disc file '{anchor}'). Please retry."
    )


def create_library_collection(body: GameItemBundleCreate, db: Session) -> tuple[GameItemBundle, bool]:
    """Backward-compat wrapper. Returns (collection, already_existed)."""
    try:
        return (
            _ingest_media_entry(
                body.file_path, body.title, db, override_profile_item_id=body.profile_item_id
            ),
            False,
        )
    except _ItemAlreadyExists as e:
        return e.collection, True


def _delete_leaf_media_folders(collection: GameItemBundle) -> None:
    """Delete each leaf's on-disk media, used only when _should_delete_media()
    resolves true (per-collection override, else the global
    delete_media_on_removal setting).

    Only rmtree's folder_path when leaf.folder_owned is True — meaning the
    ingest pipeline created or renamed that directory exclusively for this
    item (or, for a multi-disc set, this collection). folder_owned False or
    None (rows written before this column existed) means folder_path is a
    pre-existing directory the ingest pipeline does not own — most notably the
    parent directory of a loose file ingested with no SOFTWARE_PATH configured,
    which may be shared with unrelated files or other library items entirely
    outside this app's control. For those leaves only the tracked file_path
    file itself is unlinked; the directory is left alone. This is deliberately
    asymmetric with the owned case (which may leave cover art / companion
    files behind for legacy folder_owned=None rows) — over-deleting a shared
    directory is worse than under-deleting an unowned one.

    Every resolved path is required to fall under the game library root
    (library/software/games/) before removal; a path that fails this check is
    refused and logged loudly rather than silently skipped, since silently
    continuing past a failed containment check on a delete path is worse than
    doing nothing.
    """
    from backend.core.logger import get_logger
    from backend.core.settings import get_settings
    from backend.service.utils.path_utils import library_domain_root

    log = get_logger(__name__)
    svc = get_settings()
    media_root_str = svc.get("SOFTWARE_PATH", "") or ""
    if not media_root_str:
        log.error(
            "Media deletion is enabled for collection %s but SOFTWARE_PATH is unset; "
            "refusing to delete media folders.",
            collection.id,
        )
        return
    media_root = library_domain_root("games")

    def _under_root(path: Path) -> bool:
        return path == media_root or path.is_relative_to(media_root)

    seen_folders: set[str] = set()
    seen_files: set[str] = set()
    for leaf in collection.items:
        if leaf.folder_owned and leaf.folder_path:
            if leaf.folder_path in seen_folders:
                continue
            seen_folders.add(leaf.folder_path)

            folder = Path(leaf.folder_path).resolve()
            if not _under_root(folder):
                log.error(
                    "Refusing to delete media folder '%s' for library item %s: "
                    "it does not resolve under the game library root ('%s').",
                    folder, leaf.id, media_root,
                )
                continue
            try:
                if folder.exists():
                    shutil.rmtree(folder)
                    log.info("Deleted media folder: %s", folder)
            except OSError as exc:
                log.warning("Could not delete media folder %s: %s", folder, exc)
        elif leaf.file_path:
            # folder_path is not exclusively owned (or ownership is unknown) —
            # never rmtree it. Only remove the one tracked file.
            if leaf.file_path in seen_files:
                continue
            seen_files.add(leaf.file_path)

            file_path = Path(leaf.file_path).resolve()
            if not _under_root(file_path):
                log.error(
                    "Refusing to delete media file '%s' for library item %s: "
                    "it does not resolve under the game library root ('%s').",
                    file_path, leaf.id, media_root,
                )
                continue
            try:
                if file_path.is_file():
                    file_path.unlink()
                    log.info("Deleted media file: %s", file_path)
            except OSError as exc:
                log.warning("Could not delete media file %s: %s", file_path, exc)


def _should_delete_media(collection: GameItemBundle) -> bool:
    """Resolve the effective delete-media decision for a collection: its own
    override if set, else the global delete_media_on_removal setting."""
    if collection.delete_media_override is not None:
        return collection.delete_media_override
    from backend.core.settings import get_settings
    return bool(get_settings().get("delete_media_on_removal", False))


def delete_library_collection(collection_id: int, token: str, db: Session) -> None:
    if not _consume(token, "game", collection_id):
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation token.")
    collection = db.get(GameItemBundle, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Software collection not found.")
    # Remove the collection-owned drive row and its on-disk FAT16 image before
    # deleting the collection, so the image file is never orphaned (the FK cascade
    # only drops the DB row, not the file). No-op for collections without a drive.
    from backend.service.utils.drive_utils import delete_drive_for_collection
    delete_drive_for_collection(collection, db)

    if _should_delete_media(collection):
        _delete_leaf_media_folders(collection)

    # MediaLink carries no DB-level FK to game_item_bundles (a polymorphic
    # entity_id cannot FK to multiple target tables), so there is no
    # ON DELETE CASCADE for it, unlike the leaf rows below. Clean it up
    # explicitly or a stale link row could resurface as a wrong deeplink if
    # this id is ever reused.
    from backend.models.media import delete_links_for
    delete_links_for("game_item_bundle", collection_id, db)

    db.delete(collection)  # ON DELETE CASCADE removes the leaf rows
    db.commit()


def update_library_collection(
    collection_id: int, body: GameItemBundleUpdate, db: Session
) -> GameItemBundle:
    from sqlalchemy import select as _select

    collection = db.get(GameItemBundle, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Software collection not found.")

    fields = body.model_dump(exclude_unset=True)
    if "era" in fields and fields["era"] is None:
        # era is a NOT NULL column (see GameItemBundle.era in backend/models/game.py).
        # A caller that explicitly sends era: null would otherwise reach the
        # setattr/commit below and fail as a raw NOT NULL constraint violation.
        # Reject it cleanly here instead, this is defense-in-depth against any
        # caller, the frontend form now omits the key entirely when era is unset.
        raise HTTPException(status_code=422, detail="era cannot be null. Omit the field to leave it unchanged.")
    for disk_field in ("display_disk_id", "launch_disk_id"):
        if fields.get(disk_field) is not None:
            leaf_ids = set(
                db.execute(
                    _select(GameItem.id).where(GameItem.game_item_bundle_id == collection_id)
                ).scalars().all()
            )
            if fields[disk_field] not in leaf_ids:
                raise HTTPException(status_code=422, detail="disc does not belong to this collection.")
    for key, value in fields.items():
        setattr(collection, key, value)
    if "era" in fields:
        # setattr bypasses GameItemBundle._derive_item_type_from_era (no
        # validate_assignment) — re-derive explicitly whenever era changes.
        collection.item_type = derive_item_type(collection.era)
    _enforce_environment_binding(collection)
    db.commit()
    db.refresh(collection)
    return collection


_PATH_FIELDS = {"executable_path", "cover_art_path"}
_EXISTENCE_FIELDS = {"executable_path", "cover_art_path"}
# executable_path is what coordinator.py prefers over media_path when
# building a LaunchSpec (see _launch_entity), so it is the one field here
# that can steer a launch outside the library entirely if left unchecked.
# cover_art_path only ever gets read for display, never passed to a
# backend's launch(), so it is deliberately left out of this containment
# check, same reasoning ingest already applies to media_src at
# ~line 340-348 (games-only, directory case).
_CONTAINMENT_FIELDS = {"executable_path"}


def update_library_leaf(collection_id: int, leaf_id: int, body: GameItemUpdate, db: Session) -> GameItem:
    leaf = db.get(GameItem, leaf_id)
    if not leaf or leaf.game_item_bundle_id != collection_id:
        raise HTTPException(status_code=404, detail="Software item not found.")
    fields = body.model_dump(exclude_none=True)
    for key in _PATH_FIELDS & fields.keys():
        try:
            resolved = normalise_path(fields[key])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"{key}: {e}")
        if key in _EXISTENCE_FIELDS and not resolved.exists():
            raise HTTPException(status_code=400, detail=f"{key} does not exist: {resolved}")
        if key in _CONTAINMENT_FIELDS:
            from backend.core.settings import get_settings
            games_root_str = get_settings().get("SOFTWARE_PATH", "") or ""
            if games_root_str:
                from backend.service.utils.path_utils import library_domain_root
                media_root = library_domain_root("games")
                if not (resolved == media_root or resolved.is_relative_to(media_root)):
                    raise HTTPException(
                        status_code=422,
                        detail=f"{key} must be inside the games library (library/software/games/).",
                    )
        fields[key] = str(resolved)
    for key, value in fields.items():
        setattr(leaf, key, value)
    db.commit()
    db.refresh(leaf)
    return leaf


def _reverify_leaf_in_session(leaf: GameItem, bundle: GameItemBundle) -> None:
    """Shared re-verify body, mutates *leaf* in place, caller commits.

    Split out of reverify_library_leaf so reverify_library_collection (the
    Part D "re-check all discs" bundle endpoint) can re-verify every leaf in
    one transaction instead of one commit per disc.

    Never reads detection_reason and never fabricates a comparison value,
    that was the old implementation's bug: parsing a hash out of
    detection_reason and, on failure to parse, silently comparing a freshly
    computed hash against itself, which always "matched" whether the file was
    actually good or not. Reads leaf.sha1 (persisted at ingest by
    _prepare_item / _prepare_multi_disc) directly instead:

    - leaf.sha1 present: run classify() fresh against the current file. This
      naturally re-derives "verified" if nothing changed, "caution" or
      "mismatch" if the file drifted into a different but still
      index-recognizable state, or "not_in_index" if it drifted into
      nothing recognizable at all.
    - leaf.sha1 absent (a legacy row from before this field existed, or
      hash_file() failed at ingest): there is no baseline to anchor a real
      classification to. Only hash the file now and resolve to "not_in_index"
      (hashing succeeded) or "unchecked" (it still can't be hashed), never
      jump straight to verified/caution/mismatch on a leaf that was never
      classified at ingest.
    """
    path = normalise_path(leaf.file_path)
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"Media file not found on disk: {leaf.file_path}")

    if leaf.sha1 is not None:
        from backend.service.utils.smart_media_detector import classify as _classify

        era = bundle.era if bundle.era != "unknown" else None
        result = _classify(path, bundle.title, era)
        leaf.verification_status = result.status
        leaf.verification_similarity = result.similarity
        leaf.sha1 = result.computed_sha1
    else:
        from backend.service.utils.smart_media_detector.hashing.hash_lookup import hash_file

        try:
            leaf.sha1 = hash_file(path)["sha1"]
            leaf.verification_status = "not_in_index"
            leaf.verification_similarity = None
        except OSError:
            leaf.sha1 = None
            leaf.verification_status = "unchecked"
            leaf.verification_similarity = None


def reverify_library_leaf(leaf_id: int, db: Session) -> GameItem:
    """On-demand re-check of one leaf, the manual counterpart to ingest-time
    classify() above. Catches post-ingest corruption or a swapped file, which
    ingest-time detection can never see. See _reverify_leaf_in_session for
    the actual logic.
    """
    leaf = db.get(GameItem, leaf_id)
    if leaf is None:
        raise HTTPException(status_code=404, detail="Software item not found.")
    bundle = db.get(GameItemBundle, leaf.game_item_bundle_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Parent collection not found.")

    _reverify_leaf_in_session(leaf, bundle)
    db.commit()
    db.refresh(leaf)
    return leaf


def reverify_library_collection(collection_id: int, db: Session) -> GameItemBundle:
    """Re-check every disc in a collection in one transaction, the bundle-
    level "re-verify all discs" action (Part D). Per-disc verification means
    a single-leaf re-verify can no longer stand in for "verify the whole
    game" once a bundle has more than one disc.
    """
    collection = db.get(GameItemBundle, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail="Software collection not found.")

    for leaf in collection.items:
        _reverify_leaf_in_session(leaf, collection)

    db.commit()
    db.refresh(collection)
    return collection


def reorder_library_items(
    collection_id: int, body: GameItemReorder, db: Session
) -> GameItemBundle:
    """Persist a staged disc reorder in one transaction.

    ``body.disc_order`` must be exactly the collection's current leaf ids,
    top-to-bottom — validated the same way ``update_library_collection``
    validates ``launch_disk_id``/``display_disk_id`` against the collection's
    own leaves, so a client can't name a leaf belonging to a different
    collection. Looping individual per-leaf PATCH calls instead of this single
    endpoint would risk a mid-loop failure leaving ``disc_number`` duplicated
    or gapped across leaves; this commits all of them together or none.
    """
    collection = db.get(GameItemBundle, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Software collection not found.")

    leaves = db.query(GameItem).filter(GameItem.game_item_bundle_id == collection_id).all()
    leaf_ids = {leaf.id for leaf in leaves}
    if not body.disc_order or set(body.disc_order) != leaf_ids or len(body.disc_order) != len(leaf_ids):
        raise HTTPException(
            status_code=422,
            detail="disc_order must contain exactly this collection's discs, with no duplicates.",
        )

    leaves_by_id = {leaf.id: leaf for leaf in leaves}
    for position, leaf_id in enumerate(body.disc_order, start=1):
        leaves_by_id[leaf_id].disc_number = position
    collection.launch_disk_id = body.disc_order[0]
    db.commit()
    db.refresh(collection)
    return collection
