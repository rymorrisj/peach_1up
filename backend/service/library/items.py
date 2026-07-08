from __future__ import annotations

import re
import shutil
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.library import (
    LibraryCollection, LibraryCollectionCreate, LibraryCollectionUpdate,
    LibraryItem, LibraryItemReorder, LibraryItemUpdate,
)
from backend.service.utils.confirmation_tokens import consume as _consume
from backend.service.utils.era_media import is_drive_image, media_type_from_path, resolve_media_file_from_directory
from backend.service.utils.path_utils import normalise_path, resolve_under
from backend.service.utils.era_defaults import DOS_WIN_ERAS as _DRIVE_ERAS
from backend.service.utils.slug_generator import generate_collection_slug, slugify, unique_slug

_MEDIA_SUFFIXES = {".iso", ".cue", ".exe", ".com", ".zip"}

# Keys in the prepared row that belong to the collection (parent) vs the leaf.
_COLLECTION_COLUMNS = {
    "title", "era", "slug", "sort_title", "category", "description", "publisher",
    "year", "external_game_id", "metadata_source", "content_rating",
    "launch_commands", "launch_review_flagged", "installed", "requires_install",
    "platform_id", "profile_id", "last_launched_at", "launch_count",
}
_LEAF_COLUMNS = {
    "media_path", "executable_path", "cover_art_path", "media_type",
    "folder_path", "detection_reason", "file_size_bytes", "original_name",
}


class _ItemAlreadyExists(Exception):
    """Raised by _prepare_item when the media path is already tracked."""
    def __init__(self, collection: LibraryCollection | None):
        self.collection = collection


class _SlugCollision(Exception):
    """Raised when a concurrent insert claimed the same slug between generation and commit."""
    def __init__(self, message: str | None = None):
        super().__init__(message or "Import collided with a concurrent change, please retry.")


def best_detect_path(folder: Path, executable_path: str | None) -> Path:
    if executable_path and Path(executable_path).suffix.lower() != ".img":
        return Path(executable_path)
    from backend.service.utils.era_media import all_supported_extensions
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


def _collection_for_leaf(leaf: LibraryItem | None, db: Session) -> LibraryCollection | None:
    if leaf is None:
        return None
    return db.get(LibraryCollection, leaf.library_collection_id)


def _prepare_item(
    media_path: str,
    title: str,
    db: Session,
    *,
    used_slugs: set[str] | None = None,
    override_profile_id: int | None = None,
    detected_era: str | None = None,
    user_override_era: str | None = None,
    _undo_stack: list | None = None,
) -> dict:
    """
    Run the full ingest pipeline for one media path without writing to the DB.

    Performs filesystem operations (folder creation, file copy) and era
    detection, then returns a mapping of all column values (collection- and
    leaf-level) for a collection-of-one.

    Era resolution has three sources, in precedence order:
        1. ``user_override_era`` — a genuine user selection. Sets
           ``detection_reason`` to "Selected by user during import".
        2. ``detected_era`` — an era determined by an upstream detection pass
           (e.g. the scan preview). Pins the era but ``detection_reason`` keeps
           the actual per-item detection method, never the "user selected"
           string. This is what the scan importer passes.
        3. This function's own detection — the default (manual add path).

    Keeping (2) and (1) distinct is the fix for scan imports stamping a fixed
    "Selected by user during import" reason on every auto-detected item.

    Raises:
        _ItemAlreadyExists: if this path is already tracked as a library leaf.
        HTTPException: for path or conflict errors.
    """
    from backend.core.logger import get_logger
    from backend.core.settings import get_settings
    from backend.models.platform import Platform
    from backend.service.utils.era_defaults import defaults_for_era, lookup_platform_and_profile
    from backend.service.utils.profile_builder import _EXECUTABLE_PRIORITY, _find_cover
    from backend.service.utils.smart_media_detector import detect as _smart_detect
    from backend.service.utils.rating_detect import detect_rating

    log = get_logger(__name__)
    svc = get_settings()
    games_root_str = svc.get("MEDIA_PATH", "") or ""

    try:
        media_src = normalise_path(media_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"media_path: {e}")

    if not media_src.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {media_path}")

    incoming_norm = media_src.as_posix()

    for base_path, working_path in db.query(
        Platform.base_image_path, Platform.working_image_path
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
        "media_path": str(media_src),
        "original_name": media_src.name,
        "slug": None,
        "sort_title": None,
        "category": None,
        "media_type": None,
        "folder_path": None,
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
        "platform_id": None,
        "profile_id": None,
        "last_launched_at": None,
        "launch_count": 0,
        "file_size_bytes": None,
    }

    _dir_ingest_root: Path | None = None
    # Detection accumulates into these locals; row["era"] and
    # row["detection_reason"] are written exactly once, at the single resolution
    # site below the branches (Stage 6 — one write site, one era-resolution path).
    _det_era: str | None = None
    _det_reason: str | None = None

    if media_src.is_dir():
        if games_root_str:
            media_root = Path(games_root_str).resolve()
            if not (media_src == media_root or media_src.is_relative_to(media_root)):
                raise HTTPException(
                    status_code=400,
                    detail="Folder is outside the media library (library/media/).",
                )

        existing = db.query(LibraryItem).filter(
            LibraryItem.folder_path == str(media_src)
        ).first()
        if existing:
            raise _ItemAlreadyExists(_collection_for_leaf(existing, db))
        sub = db.query(LibraryItem).filter(
            LibraryItem.media_path.like(str(media_src) + "/%")
        ).first()
        if sub:
            raise _ItemAlreadyExists(_collection_for_leaf(sub, db))

        _dir_ingest_root = media_src
        row["folder_path"] = str(media_src)
        row["media_path"] = str(media_src)

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
                row["media_path"] = str(resolved_media)
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
                log.warning("Could not resolve media file for '%s': %s", title, exc)

    elif media_src.is_file():
        if games_root_str:
            _games_root = Path(games_root_str).resolve()
            _src_parent = media_src.parent

            # Slugify the destination folder name (matches the shared slugify()
            # every other ingest path uses — chunked_uploads.reassemble(),
            # path_import.stage_from_source(), and the is_dir() branch below).
            # This is deliberately the plain slug, not unique_slug(): the
            # canonical folder name is deterministic from the stem, and an
            # existing folder at that path is a real target to rename into or
            # move into (handled below), not a collision to suffix away from.
            dest_folder = Path(games_root_str) / slugify(media_src.stem)
            dest = dest_folder / media_src.name

            # Duplicate check: source path or destination copy already tracked.
            # media_path is always written as str(Path(...).resolve()) by this same
            # function, so an exact match against the same two candidate strings
            # finds any prior duplicate without re-resolving the whole table.
            existing_leaf = db.query(LibraryItem).filter(
                LibraryItem.media_path.in_([str(media_src), str(dest)])
            ).first()
            if existing_leaf:
                raise _ItemAlreadyExists(_collection_for_leaf(existing_leaf, db))

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
                row["media_path"] = str(dest)
            else:
                dest_folder.mkdir(parents=True, exist_ok=True)
                row["folder_path"] = str(dest_folder)

                if dest.exists():
                    if dest.stat().st_size == media_src.stat().st_size:
                        # Identical file already in place — reuse without re-copy
                        row["media_path"] = str(dest)
                    else:
                        raise HTTPException(
                            status_code=409,
                            detail=f"A different file named '{media_src.name}' already exists in '{dest_folder}'.",
                        )
                else:
                    if media_src.resolve() == dest.resolve():
                        row["media_path"] = str(dest)
                    else:
                        shutil.move(str(media_src), str(dest))
                        if _undo_stack is not None:
                            _undo_stack.append(lambda _s=media_src, _d=dest: shutil.move(str(_d), str(_s)) if _d.exists() else None)
                        row["media_path"] = str(dest)

            cover = _find_cover(dest_folder)
            if cover:
                row["cover_art_path"] = str(cover)
        else:
            existing_leaf = db.query(LibraryItem).filter(
                LibraryItem.media_path == str(media_src)
            ).first()
            if existing_leaf:
                raise _ItemAlreadyExists(_collection_for_leaf(existing_leaf, db))
            row["folder_path"] = str(media_src.parent)

        _scan = _smart_detect(Path(row["media_path"]))
        if _scan.era is not None:
            _det_era = _scan.era
            _det_reason = _scan.reason
        elif _scan.warnings:
            log.warning("Media detection warnings for '%s': %s", row["media_path"], _scan.warnings)

        # Single-file ingest (e.g. a loose console ROM/ISO with no companion
        # .exe to discover) has no folder to scan for a launch file the way
        # the directory branch above does. The item's own media file *is*
        # the launch target, so populate executable_path with it directly —
        # this is a "launch target" field, not strictly a "discovered .exe"
        # field, and must not be left null for a launchable item. Mirrors
        # _create_multi_disc_collection, which already does the same for
        # multi-disc sets (executable_path = disc_file).
        if row["executable_path"] is None:
            row["executable_path"] = row["media_path"]
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

    # For folder ingests: rename the existing folder to its slug-based name.
    # resolve_under confirms the target stays within the same parent directory
    # (defense-in-depth — slugify already guarantees [a-z0-9-] only).
    if _dir_ingest_root is not None:
        try:
            slug_folder = resolve_under(_dir_ingest_root.parent, row["slug"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Slug-based folder name is invalid: {exc}")
        if slug_folder != _dir_ingest_root.resolve():
            if slug_folder.exists():
                raise HTTPException(
                    status_code=409,
                    detail=f"A folder named '{row['slug']}' already exists in the media library.",
                )
            _dir_ingest_root.rename(slug_folder)
            if _undo_stack is not None:
                _undo_stack.append(lambda _o=_dir_ingest_root, _n=slug_folder: _n.rename(_o) if _n.exists() else None)
            for field in ("folder_path", "media_path", "executable_path", "cover_art_path"):
                val = row.get(field)
                if val:
                    try:
                        field_path = Path(val)
                        if field_path == _dir_ingest_root or field_path.is_relative_to(_dir_ingest_root):
                            row[field] = str(slug_folder / field_path.relative_to(_dir_ingest_root))
                    except (ValueError, TypeError) as exc:
                        log.warning(
                            "Could not rewrite '%s' after folder rename (%s -> %s): %s. "
                            "Field will keep its stale pre-rename value: %s",
                            field, _dir_ingest_root, slug_folder, exc, val,
                        )

    row["media_type"] = media_type_from_path(Path(row["media_path"]))
    row["requires_install"] = _scan.requires_install

    # Single resolution + write site for era and detection_reason (Stage 6).
    # Precedence: explicit user override, then a scan-preview detected-era hint,
    # then this function's own detection. detection_reason therefore reflects the
    # actual detection method per item, and is only the fixed "user" string when
    # the era was genuinely user-selected — not for every scan import.
    if user_override_era is not None:
        row["era"] = user_override_era
        row["detection_reason"] = "Selected by user during import"
    elif detected_era is not None:
        row["era"] = detected_era
        row["detection_reason"] = (
            _det_reason if _det_era == detected_era and _det_reason
            else "Detected during library scan"
        )
    elif _det_era is not None:
        row["era"] = _det_era
        row["detection_reason"] = _det_reason
    # else: era stays the initial "unknown" and detection_reason stays None.

    if row["era"] and row["era"] != "unknown":
        _emulator_slug, _profile_era = defaults_for_era(row["era"])
        if _emulator_slug and _profile_era:
            _def_platform_id, _def_profile_id = lookup_platform_and_profile(
                _emulator_slug, _profile_era, db
            )
            if _def_profile_id is not None:
                row["profile_id"] = _def_profile_id
            if _def_platform_id is not None:
                row["platform_id"] = _def_platform_id

    if override_profile_id is not None:
        row["profile_id"] = override_profile_id

    row["content_rating"] = detect_rating(row["media_path"]) or None

    try:
        p = Path(row["media_path"])
        row["file_size_bytes"] = p.stat().st_size if p.is_file() else None
    except OSError:
        row["file_size_bytes"] = None

    return row


def _persist_collection_of_one(row: dict, db: Session) -> LibraryCollection:
    """Create a LibraryCollection + its single LibraryItem leaf from a prepared row.

    Flushes both so ids exist and launch/display disk pointers are set to the
    leaf. Does NOT commit — the caller owns the transaction (and any undo of
    filesystem side effects on IntegrityError).
    """
    collection = LibraryCollection(**{k: row[k] for k in _COLLECTION_COLUMNS if k in row})
    db.add(collection)
    db.flush()

    leaf = LibraryItem(
        library_collection_id=collection.id,
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
    override_profile_id: int | None = None,
) -> LibraryCollection:
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
        row = _prepare_item(media_path, title, db, override_profile_id=override_profile_id, _undo_stack=_undo_ops)
        collection = _persist_collection_of_one(row, db)
    except IntegrityError as exc:
        db.rollback()
        for _undo in reversed(_undo_ops):
            try:
                _undo()
            except OSError:
                pass
        raise _SlugCollision() from exc
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
) -> LibraryCollection:
    """
    Create a LibraryCollection with one LibraryItem leaf per disc file.
    disc_files must be pre-sorted (disc 1 first).
    Each disc file becomes both media_path and executable_path for its leaf.
    """
    from backend.core.logger import get_logger
    from backend.service.utils.smart_media_detector import detect as _smart_detect
    from backend.service.utils.era_defaults import defaults_for_era, lookup_platform_and_profile
    from backend.service.utils.profile_builder import _find_cover
    from backend.service.utils.rating_detect import detect_rating

    log = get_logger(__name__)
    _scan = _smart_detect(disc_files[0])
    if _scan.era is None and _scan.warnings:
        log.warning("Media detection warnings for '%s': %s", disc_files[0], _scan.warnings)
    detected_era: str = _scan.era if _scan.era is not None else "unknown"

    detected_platform_id: int | None = None
    detected_profile_id: int | None = None
    if detected_era and detected_era != "unknown":
        _emulator_slug, _profile_era = defaults_for_era(detected_era)
        if _emulator_slug and _profile_era:
            detected_platform_id, detected_profile_id = lookup_platform_and_profile(
                _emulator_slug, _profile_era, db
            )

    slug = generate_collection_slug(title, db)
    collection = LibraryCollection(
        title=title,
        era=detected_era,
        slug=slug,
        platform_id=detected_platform_id,
        profile_id=detected_profile_id,
        content_rating=detect_rating(str(disc_files[0])) or None,
    )
    try:
        db.add(collection)
        db.flush()

        cover = _find_cover(disc_files[0].parent)

        leaves: list[LibraryItem] = []
        for disc_number, disc_file in enumerate(disc_files, start=1):
            leaf = LibraryItem(
                library_collection_id=collection.id,
                disc_number=disc_number,
                media_path=str(disc_file),
                executable_path=str(disc_file),
                media_type=media_type_from_path(disc_file),
                file_size_bytes=_disc_data_size(disc_file),
                cover_art_path=str(cover) if disc_number == 1 and cover else None,
                original_name=disc_file.name,
                folder_path=str(disc_file.parent),
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
        raise _SlugCollision(
            f"Import collided with a concurrent change while adding '{slug}' "
            f"(disc file '{disc_files[0].name}') — please retry."
        ) from exc

    db.refresh(collection)
    return collection


def create_library_collection(body: LibraryCollectionCreate, db: Session) -> tuple[LibraryCollection, bool]:
    """Backward-compat wrapper. Returns (collection, already_existed)."""
    try:
        return (
            _ingest_media_entry(
                body.media_path, body.title, db, override_profile_id=body.profile_id
            ),
            False,
        )
    except _ItemAlreadyExists as e:
        return e.collection, True


def _delete_leaf_media_folders(collection: LibraryCollection) -> None:
    """Delete each leaf's on-disk media folder (folder_path), used only when
    _should_delete_media() resolves true (per-collection override, else the
    global delete_media_on_removal setting).

    folder_path (not a path reconstructed from the slug) is the source of truth
    for what to remove, since ingest may have slug-renamed the directory. Leaves
    with no folder_path are skipped — there is nothing to remove for them. Every
    resolved folder is required to fall under MEDIA_PATH before rmtree; a folder
    that fails this check is refused and logged loudly rather than silently
    skipped, since silently continuing past a failed containment check on a
    delete path is worse than doing nothing.
    """
    from backend.core.logger import get_logger
    from backend.core.settings import get_settings

    log = get_logger(__name__)
    svc = get_settings()
    media_root_str = svc.get("MEDIA_PATH", "") or ""
    if not media_root_str:
        log.error(
            "Media deletion is enabled for collection %s but MEDIA_PATH is unset; "
            "refusing to delete media folders.",
            collection.id,
        )
        return
    media_root = Path(media_root_str).resolve()

    seen: set[str] = set()
    for leaf in collection.items:
        if not leaf.folder_path or leaf.folder_path in seen:
            continue
        seen.add(leaf.folder_path)

        folder = Path(leaf.folder_path).resolve()
        if not (folder == media_root or folder.is_relative_to(media_root)):
            log.error(
                "Refusing to delete media folder '%s' for library item %s: "
                "it does not resolve under MEDIA_PATH ('%s').",
                folder, leaf.id, media_root,
            )
            continue

        try:
            if folder.exists():
                shutil.rmtree(folder)
                log.info("Deleted media folder: %s", folder)
        except OSError as exc:
            log.warning("Could not delete media folder %s: %s", folder, exc)


def _should_delete_media(collection: LibraryCollection) -> bool:
    """Resolve the effective delete-media decision for a collection: its own
    override if set, else the global delete_media_on_removal setting."""
    if collection.delete_media_override is not None:
        return collection.delete_media_override
    from backend.core.settings import get_settings
    return bool(get_settings().get("delete_media_on_removal", False))


def delete_library_collection(collection_id: int, token: str, db: Session) -> None:
    if not _consume(token, "library", collection_id):
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation token.")
    collection = db.get(LibraryCollection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Library collection not found.")
    # Remove the collection-owned drive row and its on-disk FAT16 image before
    # deleting the collection, so the image file is never orphaned (the FK cascade
    # only drops the DB row, not the file). No-op for collections without a drive.
    from backend.service.utils.drive_utils import delete_drive_for_collection
    delete_drive_for_collection(collection, db)

    if _should_delete_media(collection):
        _delete_leaf_media_folders(collection)

    db.delete(collection)  # ON DELETE CASCADE removes the leaf rows
    db.commit()


def update_library_collection(
    collection_id: int, body: LibraryCollectionUpdate, db: Session
) -> LibraryCollection:
    from sqlalchemy import select as _select

    collection = db.get(LibraryCollection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Library collection not found.")

    fields = body.model_dump(exclude_unset=True)
    for disk_field in ("display_disk_id", "launch_disk_id"):
        if fields.get(disk_field) is not None:
            leaf_ids = set(
                db.execute(
                    _select(LibraryItem.id).where(LibraryItem.library_collection_id == collection_id)
                ).scalars().all()
            )
            if fields[disk_field] not in leaf_ids:
                raise HTTPException(status_code=422, detail="disc does not belong to this collection.")
    for key, value in fields.items():
        setattr(collection, key, value)
    db.commit()
    db.refresh(collection)
    return collection


_PATH_FIELDS = {"executable_path", "cover_art_path"}
_EXISTENCE_FIELDS = {"executable_path"}


def update_library_leaf(collection_id: int, leaf_id: int, body: LibraryItemUpdate, db: Session) -> LibraryItem:
    leaf = db.get(LibraryItem, leaf_id)
    if not leaf or leaf.library_collection_id != collection_id:
        raise HTTPException(status_code=404, detail="Library item not found.")
    fields = body.model_dump(exclude_none=True)
    for key in _PATH_FIELDS & fields.keys():
        try:
            resolved = normalise_path(fields[key])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"{key}: {e}")
        if key in _EXISTENCE_FIELDS and not resolved.exists():
            raise HTTPException(status_code=400, detail=f"{key} does not exist: {resolved}")
        fields[key] = str(resolved)
    for key, value in fields.items():
        setattr(leaf, key, value)
    db.commit()
    db.refresh(leaf)
    return leaf


def reorder_library_items(
    collection_id: int, body: LibraryItemReorder, db: Session
) -> LibraryCollection:
    """Persist a staged disc reorder in one transaction.

    ``body.disc_order`` must be exactly the collection's current leaf ids,
    top-to-bottom — validated the same way ``update_library_collection``
    validates ``launch_disk_id``/``display_disk_id`` against the collection's
    own leaves, so a client can't name a leaf belonging to a different
    collection. Looping individual per-leaf PATCH calls instead of this single
    endpoint would risk a mid-loop failure leaving ``disc_number`` duplicated
    or gapped across leaves; this commits all of them together or none.
    """
    collection = db.get(LibraryCollection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Library collection not found.")

    leaves = db.query(LibraryItem).filter(LibraryItem.library_collection_id == collection_id).all()
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
