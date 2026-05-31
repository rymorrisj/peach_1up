from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.models.library import LibraryItem, LibraryItemCreate, LibraryItemUpdate
from backend.service.utils.confirmation_tokens import consume as _consume
from backend.service.utils.drive_utils import create_drive_for_item
from backend.service.utils.path_utils import normalise_path
from backend.service.utils.slug_generator import generate_item_slug

_MEDIA_SUFFIXES = {".iso", ".cue", ".exe", ".com", ".zip"}


def best_detect_path(folder: Path, executable_path: str | None) -> Path:
    if executable_path and Path(executable_path).suffix.lower() != ".img":
        return Path(executable_path)
    try:
        hit = next(
            (f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in _MEDIA_SUFFIXES),
            None,
        )
    except OSError:
        hit = None
    return hit if hit is not None else folder


def create_library_item(body: LibraryItemCreate, db: Session) -> tuple[LibraryItem, bool]:
    """Create a library item. Returns (item, already_existed)."""
    from backend.core.logger import get_logger
    from backend.core.settings import get_settings
    from backend.models.platform import Platform
    from backend.service.utils.detection.era_detect import detect_era as _detect_era
    from backend.service.utils.era_defaults import defaults_for_era, lookup_platform_and_profile
    from backend.service.utils.media_detect import detect_media_type
    from backend.service.utils.profile_builder import _EXECUTABLE_PRIORITY, _find_cover
    from backend.utils.rating_detect import detect_rating

    incoming_norm = Path(body.media_path).resolve().as_posix()

    for stored_path, item_id in db.query(LibraryItem.media_path, LibraryItem.id).all():
        if stored_path and Path(stored_path).resolve().as_posix() == incoming_norm:
            return db.get(LibraryItem, item_id), True

    for base_path, working_path in db.query(Platform.base_image_path, Platform.working_image_path).all():
        if (base_path and Path(base_path).resolve().as_posix() == incoming_norm) or (
            working_path and Path(working_path).resolve().as_posix() == incoming_norm
        ):
            raise HTTPException(
                status_code=409,
                detail="Path is an OS environment image and cannot be added as a library item.",
            )

    item = LibraryItem(**body.model_dump())
    item.slug = generate_item_slug(item.title, db)

    svc = get_settings()
    games_root_str = svc.get("MEDIA_PATH", "") or ""
    media_src = Path(body.media_path).resolve()

    if media_src.is_dir():
        if games_root_str:
            media_root = Path(games_root_str).resolve()
            if not (media_src == media_root or media_src.is_relative_to(media_root)):
                raise HTTPException(
                    status_code=400,
                    detail="Folder is outside the media library (library/media/).",
                )
        item.media_path = str(media_src)
        item.folder_path = str(media_src)
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
                    item.executable_path = str(f)
                    break
            if item.executable_path:
                break
        cover = _find_cover(media_src)
        if cover:
            item.cover_art_path = str(cover)
    elif games_root_str:
        item_folder = Path(games_root_str) / item.slug
        try:
            item_folder.mkdir(parents=True, exist_ok=True)
            item.folder_path = str(item_folder)
            if body.media_path:
                src = Path(body.media_path)
                if src.is_file():
                    dest = item_folder / src.name
                    if not dest.exists():
                        shutil.copy2(str(src), str(dest))
                    item.media_path = str(dest)
            cover = _find_cover(item_folder)
            if cover:
                item.cover_art_path = str(cover)
        except OSError as exc:
            get_logger(__name__).warning("Could not create item folder %s: %s", item_folder, exc)

    media_type = detect_media_type(Path(item.media_path))
    item.media_type = media_type
    item.requires_install = media_type in ("iso", "cue", "floppy")

    _era_folder = Path(item.media_path) if item.media_path else media_src
    _era_path = best_detect_path(_era_folder, item.executable_path)
    _era_slug, _era_reason = _detect_era(_era_path)

    if _era_slug is not None and item.era == "unknown":
        item.era = _era_slug
    if hasattr(item, "detection_reason"):
        item.detection_reason = _era_reason if _era_slug is not None else None

    if _era_slug is not None:
        _emulator_slug, _profile_era = defaults_for_era(_era_slug)
        if _emulator_slug and _profile_era:
            _def_platform_id, _def_profile_id = lookup_platform_and_profile(_emulator_slug, _profile_era, db)
            if item.platform_id is None and _def_platform_id is not None:
                item.platform_id = _def_platform_id
            if item.profile_id is None and _def_profile_id is not None:
                item.profile_id = _def_profile_id

    if not item.content_rating:
        item.content_rating = detect_rating(body.media_path)

    db.add(item)
    db.flush()

    create_drive_for_item(item, db)

    db.commit()
    db.refresh(item)
    return item, False


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
        if key in _EXISTENCE_FIELDS and not resolved.exists():
            raise HTTPException(status_code=400, detail=f"{key} does not exist: {resolved}")
        fields[key] = str(resolved)
    for key, value in fields.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item
