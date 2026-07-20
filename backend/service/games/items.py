from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

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
    # PS3_DISC.SFB at the folder root marks a disc-format dump. The folder
    # itself, not the nested EBOOT.BIN, is both the detection target (only
    # directory_detect.py's structural PS3_DISC.SFB check recognizes this
    # shape, EBOOT.BIN alone carries no such signal) and the launch target
    # (mirrors rpcs3.launch()'s own is_dir() handling), so this must run
    # before find_eboot's file resolution below can ever apply here.
    from backend.service.backends.rpcs3 import is_disc_format_folder
    if is_disc_format_folder(folder):
        return folder
    # Extracted Xbox 360 XEX folders can contain multiple top-level .xex
    # files. Resolve those first, before the generic top-level scan below,
    # so the same file is always chosen deterministically (exact
    # default.xex, else alphabetically first) instead of whatever order
    # the generic scan's directory iteration happens to return.
    from backend.service.utils.smart_media_detector.directory_detect import find_default_xex
    xex = find_default_xex(folder)
    if xex is not None:
        return xex
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
    if hit is not None:
        return hit
    # Extracted PS3 disc folders have no top-level launchable file, era.yaml
    # only declares .iso for ps3, and the real target is nested two levels
    # down (USRDIR/EBOOT.BIN or PS3_GAME/USRDIR/EBOOT.BIN). Without this,
    # the raw folder falls through unchanged and reaches hash_file(), which
    # opens it as a file and raises PermissionError. This check is
    # inherently PS3-specific (no other era's folder ever has an EBOOT.BIN),
    # so it is a no-op for every other era's folder.
    from backend.service.backends.rpcs3 import find_eboot
    eboot = find_eboot(folder)
    return eboot if eboot is not None else folder


def _collection_for_leaf(leaf: GameItem | None, db: Session) -> GameItemBundle | None:
    if leaf is None:
        return None
    return db.get(GameItemBundle, leaf.game_item_bundle_id)


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
    Run the full ingest pipeline for one media path without writing to the DB.

    Performs filesystem operations (folder creation, file copy) and era
    detection, then returns a mapping of all column values (collection- and
    leaf-level) for a collection-of-one.

    Era resolution has two sources, in precedence order:
        1. ``user_override_era``, a genuine user selection. Sets
           ``detection_reason`` to "Selected by user during import".
        2. This function's own fresh detection against the file on disk
           (_det_era/_det_reason, computed below), the default for both the
           manual add path and the scan importer.

    ``detected_era`` is still accepted as a parameter, but only as a hint for
    resolve_media_file_from_directory() when choosing which file inside a
    multi-format directory to run detection against (see _resolve_era
    below). It is never used to set the persisted era or detection_reason
    directly. It used to be: the scan importer passed its scan-preview era
    straight through and it won on precedence over this function's own
    detection. That value is echoed back by the client from an earlier
    request and was never re-checked against the file at import time, so a
    file that changed between scan and import, or a client that sent a
    stale or incorrect value, would silently persist under the wrong era.
    This function already runs a real detection pass unconditionally on
    every call regardless of what the caller passes in, so trusting that
    fresh result instead of the client echo costs nothing extra.

    Raises:
        _ItemAlreadyExists: if this path is already tracked as a library leaf.
        HTTPException: for path or conflict errors.
    """
    from backend.core.logger import get_logger
    from backend.core.settings import get_settings
    from backend.models.environment import EnvironmentItem
    from backend.service.utils.era_defaults import defaults_for_era, lookup_environment_and_profile
    from backend.service.utils.profile_builder import _EXECUTABLE_PRIORITY, _find_cover
    from backend.service.utils.smart_media_detector import classify as _classify
    from backend.service.utils.smart_media_detector import detect as _smart_detect
    from backend.service.utils.rating_detect import detect_rating

    log = get_logger(__name__)
    svc = get_settings()
    games_root_str = svc.get("SOFTWARE_PATH", "") or ""

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

    # The directory this ingest owns and created/renamed exclusively for this
    # item — set by the dir-ingest and file-ingest (SOFTWARE_PATH configured)
    # branches only. Reconciled to match the DB slug once it's final (Stage
    # 6.5, below), so folder_owned rows never carry a folder name that
    # differs from their slug regardless of which branch created them.
    _owned_folder_root: Path | None = None
    # Detection accumulates into these locals; row["era"] and
    # row["detection_reason"] are written exactly once, at the single resolution
    # site below the branches (Stage 6 — one write site, one era-resolution path).
    _det_era: str | None = None
    _det_reason: str | None = None

    if media_src.is_dir():
        if games_root_str:
            from backend.service.utils.path_utils import library_domain_root
            media_root = library_domain_root("games")
            if not (media_src == media_root or media_src.is_relative_to(media_root)):
                raise HTTPException(
                    status_code=400,
                    detail="Folder is outside the games library (library/software/games/).",
                )

        existing = db.query(GameItem).filter(
            GameItem.folder_path == str(media_src)
        ).first()
        if existing:
            raise _ItemAlreadyExists(_collection_for_leaf(existing, db))
        sub = db.query(GameItem).filter(
            GameItem.file_path.like(str(media_src) + "/%")
        ).first()
        if sub:
            raise _ItemAlreadyExists(_collection_for_leaf(sub, db))

        _owned_folder_root = media_src
        row["folder_path"] = str(media_src)
        row["folder_owned"] = True
        row["file_path"] = str(media_src)

        cover = _find_cover(media_src)
        if cover:
            row["cover_art_path"] = str(cover)

        folder_name = media_src.name
        try:
            candidates = [
                f for f in media_src.iterdir()
                if f.is_file() and not is_drive_image(f, folder_name)
            ]
        except OSError:
            candidates = []
        for ext in _EXECUTABLE_PRIORITY:
            for f in candidates:
                if f.suffix.lower() == ext:
                    row["executable_path"] = str(f)
                    break
            if row["executable_path"]:
                break

        _detect_path = best_detect_path(media_src, row["executable_path"])
        _scan = _smart_detect(_detect_path)
        if _scan.era is not None:
            _det_era = _scan.era
            _det_reason = _scan.reason
        elif _scan.warnings:
            log.warning("Media detection warnings for '%s': %s", _detect_path, _scan.warnings)

        # Era used only to pick the era-specific launch file inside the folder:
        # a user override wins, then a scan-preview hint, then this detection.
        _resolve_era = user_override_era or detected_era or _det_era
        if _resolve_era and _resolve_era != "unknown":
            try:
                resolved_media = resolve_media_file_from_directory(media_src, _resolve_era)
                row["file_path"] = str(resolved_media)
                # Only re-run detection if the era-specific resolver picked a
                # different file than the one already scanned above — avoids
                # hashing the same (possibly large) file twice, which widens
                # the window for an AV/indexer lock right before the rename.
                if resolved_media != _detect_path:
                    _scan = _smart_detect(resolved_media)
                    if _scan.era is not None:
                        _det_era = _scan.era
                        _det_reason = _scan.reason
                    elif _scan.warnings:
                        log.warning("Media detection warnings for '%s': %s", resolved_media, _scan.warnings)
            except ValueError as exc:
                if _resolve_era == "ps3":
                    # ps3's supported_media is .iso only (config/eras.yaml), so
                    # this resolver always raises for an extracted disc folder,
                    # that is expected, not a failure: there is no single file
                    # to resolve to, the folder itself is the correct launch
                    # target (matches rpcs3.launch()'s own is_dir() handling),
                    # so row["file_path"] is deliberately left pointing at the
                    # folder. Only warn when the folder isn't valid PS3 content
                    # either, i.e. resolution has no other explanation.
                    from backend.service.backends.rpcs3 import find_eboot
                    if find_eboot(media_src) is None:
                        log.warning(
                            "Could not find EBOOT.BIN in expected PS3 folder structure "
                            "for '%s' at '%s' (expected USRDIR/EBOOT.BIN, optionally "
                            "under PS3_GAME/).",
                            title, media_src,
                        )
                else:
                    log.warning("Could not resolve media file for '%s': %s", title, exc)

    elif media_src.is_file():
        if games_root_str:
            from backend.service.utils.path_utils import library_domain_root
            _games_root = library_domain_root("games")
            _src_parent = media_src.parent

            # Slugify the destination folder name (matches the shared slugify()
            # every other ingest path uses, service.uploads.core.reassemble(),
            # path_import.stage_from_source(), and the is_dir() branch below).
            # This is deliberately the plain slug, not unique_slug(): the
            # canonical folder name is deterministic from the stem, and an
            # existing folder at that path is a real target to rename into or
            # move into (handled below), not a collision to suffix away from.
            dest_folder = _games_root / slugify(media_src.stem)
            dest = dest_folder / media_src.name

            # Duplicate check, source side: file_path is always written as
            # str(Path(...).resolve()) by this same function, so an exact match
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
                if _undo_stack is not None:
                    _undo_stack.append(lambda _o=_src_parent, _n=dest_folder: _n.rename(_o) if _n.exists() else None)
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
                        if _undo_stack is not None:
                            _undo_stack.append(lambda _s=media_src, _d=dest: shutil.move(str(_d), str(_s)) if _d.exists() else None)
                        row["file_path"] = str(dest)

            cover = _find_cover(dest_folder)
            if cover:
                row["cover_art_path"] = str(cover)

            _owned_folder_root = dest_folder
        else:
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

        _scan = _smart_detect(Path(row["file_path"]))
        if _scan.era is not None:
            _det_era = _scan.era
            _det_reason = _scan.reason
        elif _scan.warnings:
            log.warning("Media detection warnings for '%s': %s", row["file_path"], _scan.warnings)

        # Single-file ingest (e.g. a loose console ROM/ISO with no companion
        # .exe to discover) has no folder to scan for a launch file the way
        # the directory branch above does. The item's own media file *is*
        # the launch target, so populate executable_path with it directly —
        # this is a "launch target" field, not strictly a "discovered .exe"
        # field, and must not be left null for a launchable item. Mirrors
        # _create_multi_disc_collection, which already does the same for
        # multi-disc sets (executable_path = disc_file).
        if row["executable_path"] is None:
            row["executable_path"] = row["file_path"]
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Path is not a file or directory: {media_path}",
        )

    # Slug — use in-memory set when batching to avoid N DB round-trips
    if used_slugs is not None:
        row["slug"] = unique_slug(title, lambda s: s in used_slugs)
        used_slugs.add(row["slug"])
    else:
        row["slug"] = generate_collection_slug(title, db)

    # Reconcile the owned folder's on-disk name to the DB slug — covers both
    # dir-ingest (folder named from the source directory) and file-ingest
    # with SOFTWARE_PATH configured (folder named from the file's stem); the two
    # start from different source strings and different uniqueness checks, so
    # without this step the folder name and row["slug"] can diverge.
    if _owned_folder_root is not None:
        slug_folder = _reconcile_folder_to_slug(_owned_folder_root, row["slug"], db, undo_stack=_undo_stack)
        row["slug"] = slug_folder.name
        if slug_folder != _owned_folder_root:
            _rewrite_paths_after_folder_rename(
                row, ("folder_path", "file_path", "executable_path", "cover_art_path"),
                _owned_folder_root, slug_folder, log,
            )

    row["file_type"] = file_type_from_path(Path(row["file_path"]))
    row["requires_install"] = _scan.requires_install

    # Single resolution + write site for era and detection_reason (Stage 6).
    # Precedence: explicit user override, then this function's own fresh
    # detection against the file on disk. detected_era (the scan-preview
    # value echoed back by the client) is deliberately not trusted here, it
    # is never re-verified against the file at import time, so a file that
    # changed between scan and import, or a stale/incorrect client value,
    # would otherwise persist silently. _det_era/_det_reason already come
    # from a real detection pass this same call already ran above, so using
    # them instead of detected_era adds no extra cost.
    if user_override_era is not None:
        row["era"] = user_override_era
        row["detection_reason"] = "Selected by user during import"
    elif _det_era is not None:
        row["era"] = _det_era
        row["detection_reason"] = _det_reason
    # else: era stays the initial "unknown" and detection_reason stays None.

    # classify() runs after era resolution above, not alongside the file_type/
    # requires_install write above, since the fuzzy title match tier needs the
    # final resolved era to scope its search. "unknown" is passed through as
    # None, era is required for classify() to ever reach "mismatch", an
    # unscoped title search across every platform would make an accidental
    # false-positive match more likely, not less.
    _classify_result = _classify(
        Path(row["file_path"]), title, row["era"] if row["era"] != "unknown" else None,
    )
    row["verification_status"] = _classify_result.status
    row["verification_similarity"] = _classify_result.similarity
    row["sha1"] = _classify_result.computed_sha1

    if row["era"] and row["era"] != "unknown":
        _emulator_slug, _profile_era = defaults_for_era(row["era"])
        if _emulator_slug and _profile_era:
            _def_environment_item_id, _def_profile_item_id = lookup_environment_and_profile(
                _emulator_slug, _profile_era, db
            )
            if _def_profile_item_id is not None:
                row["profile_item_id"] = _def_profile_item_id
            # Environment is strictly PC (doc 02 A5) — a console era must never
            # get environment_item_id populated, even if a system Environment happens
            # to exist for its emulator_slug (e.g. a seeded DuckStation/PS1 row).
            if _def_environment_item_id is not None and row["era"] in PC_ERAS:
                row["environment_item_id"] = _def_environment_item_id

    if override_profile_item_id is not None:
        row["profile_item_id"] = override_profile_item_id

    row["content_rating"] = detect_rating(row["file_path"]) or None

    try:
        p = Path(row["file_path"])
        row["file_size_bytes"] = p.stat().st_size if p.is_file() else None
    except OSError:
        row["file_size_bytes"] = None

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


def _ingest_media_entry(
    media_path: str,
    title: str,
    db: Session,
    *,
    override_profile_item_id: int | None = None,
) -> GameItemBundle:
    """
    Single shared ingest pipeline: prepare → persist a collection-of-one.
    Called by both the manual add route and the scanner import endpoint.
    Raises _ItemAlreadyExists if the path is already tracked, or _SlugCollision
    if a concurrent insert claimed the generated slug first (rare TOCTOU race).
    """
    _undo_ops: list = []
    # _prepare_item performs filesystem moves/renames (appended to _undo_ops as
    # it goes) before this function ever touches the DB. Wrapping it in this
    # same try — not just the persist call — means ANY exception during
    # prepare-or-persist replays those moves, not only an IntegrityError from
    # the flush. Otherwise an HTTPException/DB error raised inside _prepare_item
    # itself (after it already moved a file) would leave the move applied with
    # no DB row and no rollback: an orphaned move.
    try:
        row = _prepare_item(media_path, title, db, override_profile_item_id=override_profile_item_id, _undo_stack=_undo_ops)
        collection = _persist_collection_of_one(row, db)
    except IntegrityError as exc:
        db.rollback()
        for _undo in reversed(_undo_ops):
            try:
                _undo()
            except OSError:
                pass
        if _is_slug_unique_violation(exc):
            raise _SlugCollision() from exc
        raise
    except Exception:
        db.rollback()
        for _undo in reversed(_undo_ops):
            try:
                _undo()
            except OSError:
                pass
        raise

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
        text = disc_file.read_text(encoding="utf-8", errors="ignore")
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


def _create_multi_disc_collection(
    disc_files: list[Path],
    title: str,
    db: Session,
    *,
    staging_dir: Path | None = None,
) -> GameItemBundle:
    """
    Create a GameItemBundle with one GameItem leaf per disc file.
    disc_files must be pre-sorted (disc 1 first).
    Each disc file becomes both file_path and executable_path for its leaf.

    staging_dir, when given, is the shared directory the caller staged every
    disc_files entry into (service.uploads.core.reassemble() / path_import's
    stage_from_source(), named via unique_slug() against filesystem
    existence) — it is renamed to match this collection's DB slug (generated
    below against DB uniqueness, a different domain) so the two never
    diverge. Deliberately NOT inferred from disc_files[0].parent: dedup_disc_anchor
    may have already repointed disc_files[0] at an unrelated, pre-existing
    orphan file elsewhere under media_root, and renaming *that* file's parent
    would corrupt a directory this ingest doesn't own. Only disc_files entries
    that actually resolve under staging_dir are remapped after the rename;
    a repointed anchor is left untouched. Omitted (None) by direct/test
    callers that never staged a dedicated directory — reconciliation is
    skipped entirely in that case, not guessed at.
    """
    from backend.core.logger import get_logger
    from backend.service.utils.smart_media_detector import classify as _classify
    from backend.service.utils.smart_media_detector import detect as _smart_detect
    from backend.service.utils.era_defaults import defaults_for_era, lookup_environment_and_profile
    from backend.service.utils.profile_builder import _find_cover
    from backend.service.utils.rating_detect import detect_rating

    log = get_logger(__name__)
    _scan = _smart_detect(disc_files[0])
    if _scan.era is None and _scan.warnings:
        log.warning("Media detection warnings for '%s': %s", disc_files[0], _scan.warnings)
    detected_era: str = _scan.era if _scan.era is not None else "unknown"

    detected_environment_item_id: int | None = None
    detected_profile_item_id: int | None = None
    if detected_era and detected_era != "unknown":
        _emulator_slug, _profile_era = defaults_for_era(detected_era)
        if _emulator_slug and _profile_era:
            _looked_up_environment_item_id, detected_profile_item_id = lookup_environment_and_profile(
                _emulator_slug, _profile_era, db
            )
            # Environment is strictly PC (doc 02 A5) — never populate environment_item_id
            # for a console era, even if a system Environment exists for its
            # emulator_slug (e.g. a seeded DuckStation/PS1 row).
            if detected_era in PC_ERAS:
                detected_environment_item_id = _looked_up_environment_item_id

    slug = generate_collection_slug(title, db)

    # Reconcile the shared staging folder to this collection's DB slug — see
    # the staging_dir docstring param above for why this is keyed off the
    # caller-supplied directory rather than disc_files[0].parent. original_dir
    # is kept so a failure below can rename back to it: the caller
    # (service.uploads.software_games.finalize_reassembled) still references the pre-rename
    # path in its own cleanup-on-failure rmtree.
    original_dir = staging_dir
    staged_dir = staging_dir
    if staging_dir is not None:
        staged_dir = _reconcile_folder_to_slug(staging_dir, slug, db)
        slug = staged_dir.name
        if staged_dir != staging_dir:
            disc_files = [
                staged_dir / f.relative_to(staging_dir) if f.is_relative_to(staging_dir) else f
                for f in disc_files
            ]

    collection = GameItemBundle(
        title=title,
        era=detected_era,
        slug=slug,
        environment_item_id=detected_environment_item_id,
        profile_item_id=detected_profile_item_id,
        content_rating=detect_rating(str(disc_files[0])) or None,
    )
    _enforce_environment_binding(collection)
    try:
        db.add(collection)
        db.flush()

        cover = _find_cover(staged_dir if staged_dir is not None else disc_files[0].parent)

        # Redump provides a distinct sha1 per disc of a multi-disc set (each
        # disc is its own dat entry), so every disc gets its own classify()
        # call and its own persisted sha1/verification_status here, not just
        # disc 1. era comes from the single detect() call above (disc 1 only,
        # unchanged), the whole set shares one era, only the hash/title check
        # is genuinely per-disc.
        _classify_era = detected_era if detected_era != "unknown" else None

        leaves: list[GameItem] = []
        for disc_number, disc_file in enumerate(disc_files, start=1):
            _classify_result = _classify(disc_file, title, _classify_era)
            leaf = GameItem(
                game_item_bundle_id=collection.id,
                disc_number=disc_number,
                file_path=str(disc_file),
                executable_path=str(disc_file),
                file_type=file_type_from_path(disc_file),
                file_size_bytes=_disc_data_size(disc_file),
                cover_art_path=str(cover) if disc_number == 1 and cover else None,
                original_name=disc_file.name,
                folder_path=str(disc_file.parent),
                verification_status=_classify_result.status,
                verification_similarity=_classify_result.similarity,
                sha1=_classify_result.computed_sha1,
                # All disc files of a "set" upload are written together into one
                # unique-slugged staging directory dedicated to this collection
                # (see service.uploads.software_games.finalize_reassembled), safe to rmtree.
                folder_owned=True,
            )
            db.add(leaf)
            leaves.append(leaf)
        db.flush()

        collection.launch_disk_id = leaves[0].id
        collection.display_disk_id = leaves[0].id
        db.add(collection)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if staged_dir != original_dir and staged_dir.exists():
            staged_dir.rename(original_dir)
        if _is_slug_unique_violation(exc):
            raise _SlugCollision(
                f"Import collided with a concurrent change while adding '{slug}' "
                f"(disc file '{disc_files[0].name}') — please retry."
            ) from exc
        raise
    except Exception:
        # Any other failure (e.g. an OSError reading a disc file mid-write):
        # revert the folder rename so the caller's own cleanup-on-failure
        # rmtree(reasm.dest_dir) — which still references the pre-rename
        # path — actually finds and removes the staged directory, instead of
        # silently no-op'ing (ignore_errors=True) and orphaning it on disk.
        db.rollback()
        if staged_dir != original_dir and staged_dir.exists():
            staged_dir.rename(original_dir)
        raise

    db.refresh(collection)
    return collection


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
    _prepare_item / _create_multi_disc_collection) directly instead:

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
