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
from backend.service.library import items as lib_svc
from backend.service.utils import confirmation_tokens
from backend.service.utils.confirmation_tokens import TOKEN_TTL


class RestrictionsBody(BaseModel):
    user_ids: list[int]


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
    item, existed = lib_svc.create_library_item(body, db)
    if existed:
        response.status_code = 200
    return item


@router.get("/scan/status")
def scan_status():
    with _scan_lock:
        return dict(_scan_state)


def _resolve_scan_directory() -> Path:
    try:
        from backend.core.settings import get_settings
        media_path = get_settings().get("MEDIA_PATH", "") or ""
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
    return resolved


@router.post("/scan")
def trigger_scan(background_tasks: BackgroundTasks = BackgroundTasks()):
    with _scan_lock:
        if _scan_state["running"]:
            raise HTTPException(status_code=409, detail="A scan is already running.")
    resolved = _resolve_scan_directory()
    with _scan_lock:
        _scan_state["running"] = True
        _scan_state["progress"] = 0
        _scan_state["total"] = 0
        _scan_state["results"] = []
    background_tasks.add_task(_run_scan, str(resolved))
    return {"started": True, "directory": str(resolved)}


def _run_scan(directory: str) -> None:
    from backend.core.database import get_engine
    from backend.models.library import LibraryItem
    from backend.service.library.items import best_detect_path
    from backend.service.utils.detection.era_detect import detect_era as _detect_era
    from backend.service.utils.profile_builder import scan_media_folders
    from backend.service.utils.slug_generator import generate_item_slug
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
                _detect_path = best_detect_path(
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
    return lib_svc.update_library_item(item_id, body, db)


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
    lib_svc.delete_library_item(item_id, confirmation_token, db)


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
