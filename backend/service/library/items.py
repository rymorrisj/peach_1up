from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.models.library import LibraryItem, LibraryItemCreate, LibraryItemUpdate
from backend.service.utils.confirmation_tokens import consume as _consume
from backend.service.utils.drive_utils import create_drive_for_item
from backend.service.utils.era_media import media_type_from_path, resolve_media_file_from_directory
from backend.service.utils.path_utils import normalise_path
from backend.service.utils.slug_generator import generate_item_slug, unique_slug

_MEDIA_SUFFIXES = {".iso", ".cue", ".exe", ".com", ".zip"}
# Per-item FAT16 drives are for dos/win31 only; win95/win98/winxp use the
# shared OSPlatform base/working-image model (dev_docs/DECISIONS.md 2026-05-03/05-19).
_DRIVE_ERAS = frozenset({"dos", "win31"})


class _ItemAlreadyExists(Exception):
    """Raised by _prepare_item when the media path is already tracked."""
    def __init__(self, item: LibraryItem):
        self.item = item


def best_detect_path(folder: Path, executable_path: str | None) -> Path:
    if executable_path and Path(executable_path).suffix.lower() != ".img":
        return Path(executable_path)
    from backend.service.utils.era_media import all_supported_extensions
    all_exts = _MEDIA_SUFFIXES | all_supported_extensions()
    try:
        hit = next(
            (f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in all_exts),
            None,
        )
    except OSError:
        hit = None
    return hit if hit is not None else folder


def _prepare_item(
    media_path: str,
    title: str,
    db: Session,
    *,
    used_slugs: set[str] | None = None,
    override_profile_id: int | None = None,
) -> dict:
    """
    Run the full ingest pipeline for one media path without writing to the DB.

    Performs filesystem operations (folder creation, file copy) and era
    detection, then returns a mapping of all LibraryItem column values
    (excluding auto-generated columns: id, created_at, updated_at).

    Raises:
        _ItemAlreadyExists: if this path is already tracked as a library item.
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

    media_src = Path(media_path).resolve()

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
        "slug": None,
        "sort_title": None,
        "category": None,
        "media_type": None,
        "folder_path": None,
        "cover_art_path": None,
        "description": None,
        "publisher": None,
        "year": None,
        "igdb_id": None,
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
        "drive_id": None,
        "last_launched_at": None,
        "launch_count": 0,
        "file_size_bytes": None,
    }

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
            raise _ItemAlreadyExists(existing)

        row["folder_path"] = str(media_src)
        row["media_path"] = str(media_src)

        cover = _find_cover(media_src)
        if cover:
            row["cover_art_path"] = str(cover)

        folder_name = media_src.name
        drive_img_lower = f"{folder_name}.img".lower()
        try:
            candidates = [
                f for f in media_src.iterdir()
                if f.is_file() and f.name.lower() != drive_img_lower
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

        _scan = _smart_detect(media_src)
        if _scan.era is not None:
            row["era"] = _scan.era
            row["detection_reason"] = _scan.reason

        if row["era"] and row["era"] != "unknown":
            try:
                resolved_media = resolve_media_file_from_directory(media_src, row["era"])
                row["media_path"] = str(resolved_media)
                _scan = _smart_detect(resolved_media)
                if _scan.era is not None:
                    row["era"] = _scan.era
                    row["detection_reason"] = _scan.reason
            except ValueError as exc:
                log.warning("Could not resolve media file for '%s': %s", title, exc)

    elif media_src.is_file():
        try:
            media_src = normalise_path(str(media_src))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"media_path: {e}")

        if games_root_str:
            dest_folder = Path(games_root_str) / media_src.stem
            dest = dest_folder / media_src.name
            dest_norm = dest.resolve().as_posix()

            # Duplicate check: source path or destination copy already tracked
            for stored_path, item_id in db.query(
                LibraryItem.media_path, LibraryItem.id
            ).filter(LibraryItem.media_path.isnot(None)).all():
                if Path(stored_path).resolve().as_posix() in (incoming_norm, dest_norm):
                    raise _ItemAlreadyExists(db.get(LibraryItem, item_id))

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
                    row["media_path"] = str(dest)

            cover = _find_cover(dest_folder)
            if cover:
                row["cover_art_path"] = str(cover)
        else:
            for stored_path, item_id in db.query(
                LibraryItem.media_path, LibraryItem.id
            ).filter(LibraryItem.media_path.isnot(None)).all():
                if Path(stored_path).resolve().as_posix() == incoming_norm:
                    raise _ItemAlreadyExists(db.get(LibraryItem, item_id))
            row["folder_path"] = str(media_src.parent)

        _scan = _smart_detect(Path(row["media_path"]))
        if _scan.era is not None:
            row["era"] = _scan.era
            row["detection_reason"] = _scan.reason
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
        row["slug"] = generate_item_slug(title, db)

    row["media_type"] = media_type_from_path(Path(row["media_path"]))
    row["requires_install"] = _scan.requires_install

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


def _ingest_media_entry(
    media_path: str,
    title: str,
    db: Session,
    *,
    override_profile_id: int | None = None,
) -> LibraryItem:
    """
    Single shared ingest pipeline: prepare → persist → optional drive creation.
    Called by both the manual add route and the scanner import endpoint.
    Raises _ItemAlreadyExists if the path is already tracked.
    """
    row = _prepare_item(media_path, title, db, override_profile_id=override_profile_id)
    item = LibraryItem(**row)
    db.add(item)
    db.flush()

    if item.era in _DRIVE_ERAS:
        create_drive_for_item(item, db)

    db.commit()
    db.refresh(item)
    return item


def create_library_item(body: LibraryItemCreate, db: Session) -> tuple[LibraryItem, bool]:
    """Backward-compat wrapper. Returns (item, already_existed)."""
    try:
        return (
            _ingest_media_entry(
                body.media_path, body.title, db, override_profile_id=body.profile_id
            ),
            False,
        )
    except _ItemAlreadyExists as e:
        return e.item, True


def delete_library_item(item_id: int, token: str, db: Session) -> None:
    from backend.models.drive import Drive

    if not _consume(token, "library", item_id):
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation token.")
    item = db.get(LibraryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Library item not found.")
    drives = db.query(Drive).filter(Drive.library_item_id == item_id).all()
    for drive in drives:
        if drive.image_path:
            img = Path(drive.image_path)
            if img.exists():
                try:
                    img.unlink()
                except OSError as exc:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Could not delete drive image {drive.image_path}: {exc}",
                    )
    if item.drive_id is not None:
        item.drive_id = None
        db.flush()
    db.query(Drive).filter(Drive.library_item_id == item_id).delete()
    db.flush()
    db.delete(item)
    db.commit()


_PATH_FIELDS = {"media_path", "executable_path", "folder_path", "cover_art_path"}
_EXISTENCE_FIELDS = {"media_path", "executable_path"}


def update_library_item(item_id: int, body: LibraryItemUpdate, db: Session) -> LibraryItem:
    item = db.get(LibraryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Library item not found.")
    fields = body.model_dump(exclude_none=True)
    for key in _PATH_FIELDS & fields.keys():
        try:
            resolved = normalise_path(fields[key])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"{key}: {e}")
        if key in _EXISTENCE_FIELDS:
            if not resolved.exists():
                raise HTTPException(status_code=400, detail=f"{key} does not exist: {resolved}")
            if key == "media_path" and resolved.is_dir():
                raise HTTPException(
                    status_code=400,
                    detail=f"media_path must be a file, not a directory: {resolved}",
                )
        fields[key] = str(resolved)
    for key, value in fields.items():
        setattr(item, key, value)
    if "media_path" in fields:
        try:
            p = Path(fields["media_path"])
            item.file_size_bytes = p.stat().st_size if p.is_file() else None
        except OSError:
            item.file_size_bytes = None
    db.commit()
    db.refresh(item)
    return item
