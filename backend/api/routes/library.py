import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import get_active_user, get_filtered_library, require_permission
from backend.core.logger import get_logger
from backend.models.library import LibraryItem, LibraryItemCreate, LibraryItemRead, LibraryItemUpdate
from backend.models.media_restriction import MediaRestriction
from backend.models.user import User
from backend.service.utils import confirmation_tokens
from backend.service.utils.confirmation_tokens import TOKEN_TTL


class RestrictionsBody(BaseModel):
    user_ids: list[int]


_MEDIA_SUFFIXES = {".iso", ".cue", ".exe", ".com"}


def _best_detect_path(folder: Path, executable_path: str | None) -> Path:
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


router = APIRouter(prefix="/api/v1/library", tags=["library"])
logger = get_logger(__name__)

_scan_lock = threading.Lock()
_scan_state: dict[str, Any] = {"running": False, "progress": 0, "total": 0, "results": []}



@router.get("", response_model=list[LibraryItemRead])
def list_library(
    era: str | None = None,
    category: str | None = None,
    platform_id: int | None = None,
    tag: str | None = None,
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
):
    q = get_filtered_library(active_user, db)
    if era:
        q = q.filter(LibraryItem.era == era)
    if category:
        q = q.filter(LibraryItem.category == category)
    if platform_id is not None:
        q = q.filter(LibraryItem.platform_id == platform_id)
    if tag:
        from backend.models.tag import Tag
        q = q.join(LibraryItem.tags).filter(Tag.name == tag)
    return q.all()


@router.post("", response_model=LibraryItemRead, status_code=201)
def add_library_item(
    body: LibraryItemCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
    response: Response = None,
):
    from backend.models.platform import Platform

    incoming_norm = Path(body.media_path).resolve().as_posix()

    for stored_path, item_id in db.query(LibraryItem.media_path, LibraryItem.id).all():
        if stored_path and Path(stored_path).resolve().as_posix() == incoming_norm:
            response.status_code = 200
            return db.get(LibraryItem, item_id)

    for base_path, working_path in db.query(Platform.base_image_path, Platform.working_image_path).all():
        if (base_path and Path(base_path).resolve().as_posix() == incoming_norm) or (
            working_path and Path(working_path).resolve().as_posix() == incoming_norm
        ):
            raise HTTPException(
                status_code=409,
                detail="Path is an OS environment image and cannot be added as a library item.",
            )

    from backend.core.settings import get_settings
    from backend.service.utils.slug_generator import generate_item_slug

    item = LibraryItem(**body.model_dump())
    item.slug = generate_item_slug(item.title, db)

    svc = get_settings()
    games_root_str = svc.get("MEDIA_PATH", "") or ""
    media_src = Path(body.media_path).resolve()

    if media_src.is_dir():
        # Folder-as-item: validate path is within MEDIA_PATH per SECURITY.md, then use directly.
        if games_root_str:
            media_root = Path(games_root_str).resolve()
            if not (media_src == media_root or media_src.is_relative_to(media_root)):
                raise HTTPException(
                    status_code=400,
                    detail="Folder is outside the media library (library/media/).",
                )
        item.media_path = str(media_src)
        item.folder_path = str(media_src)
        from backend.service.utils.profile_builder import _EXECUTABLE_PRIORITY, _find_cover
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
        # File-based: create a slug subfolder and optionally copy the file into it.
        item_folder = Path(games_root_str) / item.slug
        try:
            item_folder.mkdir(parents=True, exist_ok=True)
            item.folder_path = str(item_folder)
            if body.media_path:
                src = Path(body.media_path)
                if src.is_file():
                    import shutil as _shutil
                    dest = item_folder / src.name
                    if not dest.exists():
                        _shutil.copy2(str(src), str(dest))
                    item.media_path = str(dest)
            from backend.service.utils.profile_builder import _find_cover
            cover = _find_cover(item_folder)
            if cover:
                item.cover_art_path = str(cover)
        except OSError as exc:
            logger.warning("Could not create item folder %s: %s", item_folder, exc)

    from backend.service.utils.media_detect import detect_media_type
    media_type = detect_media_type(Path(item.media_path))
    item.media_type = media_type
    item.requires_install = media_type in ("iso", "cue", "floppy")

    from backend.service.utils.detection.era_detect import detect_era as _detect_era
    _era_folder = Path(item.media_path) if item.media_path else media_src
    _era_path = _best_detect_path(_era_folder, item.executable_path)
    _era_slug, _era_reason = _detect_era(_era_path)

    if _era_slug is not None and item.era == "unknown":
        item.era = _era_slug
    if hasattr(item, "detection_reason"):
        item.detection_reason = _era_reason if _era_slug is not None else None

    if _era_slug is not None:
        from backend.service.utils.era_defaults import defaults_for_era, lookup_platform_and_profile
        _emulator_slug, _profile_era = defaults_for_era(_era_slug)
        if _emulator_slug and _profile_era:
            _def_platform_id, _def_profile_id = lookup_platform_and_profile(_emulator_slug, _profile_era, db)
            if item.platform_id is None and _def_platform_id is not None:
                item.platform_id = _def_platform_id
            if item.profile_id is None and _def_profile_id is not None:
                item.profile_id = _def_profile_id

    if not item.content_rating:
        from backend.utils.rating_detect import detect_rating
        item.content_rating = detect_rating(body.media_path)

    db.add(item)
    db.flush()

    from backend.service.utils.drive_utils import create_drive_for_item
    create_drive_for_item(item, db)

    db.commit()
    db.refresh(item)
    return item


@router.get("/scan/status")
def scan_status():
    with _scan_lock:
        return dict(_scan_state)


@router.post("/scan")
def trigger_scan(background_tasks: BackgroundTasks = BackgroundTasks()):
    with _scan_lock:
        if _scan_state["running"]:
            raise HTTPException(status_code=409, detail="A scan is already running.")

    try:
        from backend.core.settings import get_settings
        svc = get_settings()
        media_path = svc.get("MEDIA_PATH", "") or ""
    except RuntimeError:
        media_path = ""

    if not media_path:
        raise HTTPException(
            status_code=400,
            detail="No media library path is configured. Set MEDIA_PATH in Settings before scanning.",
        )

    resolved = Path(media_path).resolve()
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="Media library path does not exist or is not a directory.")

    with _scan_lock:
        _scan_state["running"] = True
        _scan_state["progress"] = 0
        _scan_state["total"] = 0
        _scan_state["results"] = []

    background_tasks.add_task(_run_scan, str(resolved))
    return {"started": True, "directory": str(resolved)}


def _run_scan(directory: str) -> None:
    from backend.service.utils.profile_builder import scan_media_folders
    from backend.core.database import get_engine
    from backend.models.library import LibraryItem
    from backend.service.utils.slug_generator import generate_item_slug
    from backend.service.utils.detection.era_detect import detect_era as _detect_era
    from sqlalchemy.orm import Session

    created: list[dict] = []
    try:
        entries = scan_media_folders(Path(directory))
        db = Session(get_engine())
        try:
            existing: set[str] = {
                str(Path(fp).resolve())
                for (fp,) in db.query(LibraryItem.folder_path)
                .filter(LibraryItem.folder_path.isnot(None))
                .all()
            }
            for entry in entries:
                folder_str = str(entry.folder_path.resolve())
                if folder_str in existing:
                    continue
                item = LibraryItem(
                    title=entry.name,
                    era="unknown",
                    media_path=str(entry.folder_path),
                    folder_path=str(entry.folder_path),
                    executable_path=str(entry.executable_path) if entry.executable_path else None,
                    cover_art_path=str(entry.cover_path) if entry.cover_path else None,
                )
                item.slug = generate_item_slug(item.title, db)
                _detect_path = _best_detect_path(
                    Path(entry.folder_path),
                    str(entry.executable_path) if entry.executable_path else None,
                )
                _era_slug, _era_reason = _detect_era(_detect_path)
                if _era_slug is not None:
                    item.era = _era_slug
                if hasattr(item, "detection_reason"):
                    item.detection_reason = _era_reason if _era_slug is not None else None

                if _era_slug is not None:
                    from backend.service.utils.era_defaults import defaults_for_era, lookup_platform_and_profile
                    _emulator_slug, _profile_era = defaults_for_era(_era_slug)
                    if _emulator_slug and _profile_era:
                        _def_platform_id, _def_profile_id = lookup_platform_and_profile(_emulator_slug, _profile_era, db)
                        if item.platform_id is None and _def_platform_id is not None:
                            item.platform_id = _def_platform_id
                        if item.profile_id is None and _def_profile_id is not None:
                            item.profile_id = _def_profile_id

                db.add(item)
                db.flush()
                existing.add(folder_str)
                created.append({
                    "folder_path": str(entry.folder_path),
                    "name": entry.name,
                    "executable_path": str(entry.executable_path) if entry.executable_path else None,
                })
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        with _scan_lock:
            _scan_state["results"] = created
            _scan_state["total"] = len(created)
            _scan_state["progress"] = len(created)

    except Exception as exc:
        logger.error("Scan failed: %s", exc, exc_info=True)
    finally:
        with _scan_lock:
            _scan_state["running"] = False


@router.get("/by-slug/{slug}", response_model=LibraryItemRead)
def get_library_item_by_slug(slug: str, db: Session = Depends(get_db)):
    item = db.query(LibraryItem).filter(LibraryItem.slug == slug).first()
    if not item:
        raise HTTPException(status_code=404, detail="Library item not found.")
    return item


@router.get("/{item_id}", response_model=LibraryItemRead)
def get_library_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(LibraryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Library item not found.")
    return item


@router.patch("/{item_id}", response_model=LibraryItemRead)
def update_library_item(
    item_id: int,
    body: LibraryItemUpdate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    item = db.get(LibraryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Library item not found.")
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/flag-launch", response_model=LibraryItemRead)
def flag_launch(
    item_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("can_launch_media"),
):
    item = db.get(LibraryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Library item not found.")
    item.launch_review_flagged = True
    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/confirm-delete")
def issue_delete_token(
    item_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    item = db.get(LibraryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Library item not found.")
    token = confirmation_tokens.issue("library", item_id)
    return {"confirmation_token": token, "expires_in_seconds": TOKEN_TTL}


@router.delete("/{item_id}", status_code=204)
def delete_library_item(
    item_id: int,
    confirmation_token: str = Query(...),
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    if not confirmation_tokens.consume(confirmation_token, "library", item_id):
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation token.")
    item = db.get(LibraryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Library item not found.")
    from backend.models.drive import Drive
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


@router.get("/{item_id}/restrictions")
def get_restrictions(
    item_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("is_admin"),
):
    if not db.get(LibraryItem, item_id):
        raise HTTPException(status_code=404, detail="Library item not found.")
    rows = db.query(MediaRestriction).filter(MediaRestriction.library_item_id == item_id).all()
    return {"restricted_user_ids": [r.user_id for r in rows]}


@router.put("/{item_id}/restrictions")
def set_restrictions(
    item_id: int,
    body: RestrictionsBody,
    db: Session = Depends(get_db),
    _: User = require_permission("is_admin"),
):
    if not db.get(LibraryItem, item_id):
        raise HTTPException(status_code=404, detail="Library item not found.")
    db.query(MediaRestriction).filter(MediaRestriction.library_item_id == item_id).delete()
    for user_id in body.user_ids:
        db.add(MediaRestriction(user_id=user_id, library_item_id=item_id))
    db.commit()
    return {"restricted_user_ids": body.user_ids}
