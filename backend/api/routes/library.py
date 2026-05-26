import re
import secrets
import threading
import time
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


class RestrictionsBody(BaseModel):
    user_ids: list[int]



def _make_slug(title: str, db: Session) -> str:
    base = re.sub(r'[^a-z0-9-]', '', re.sub(r'\s+', '-', title.lower())).strip('-') or 'item'
    candidate = base
    n = 2
    while True:
        if not db.query(LibraryItem).filter(LibraryItem.slug == candidate).first():
            return candidate
        candidate = f"{base}-{n}"
        n += 1

router = APIRouter(prefix="/api/v1/library", tags=["library"])
logger = get_logger(__name__)

_scan_lock = threading.Lock()
_scan_state: dict[str, Any] = {"running": False, "progress": 0, "total": 0, "results": []}

_confirm_tokens: dict[str, tuple[int, float]] = {}
_TOKEN_TTL = 60


def _issue_confirm_token(item_id: int) -> str:
    token = secrets.token_urlsafe(32)
    _confirm_tokens[token] = (item_id, time.monotonic() + _TOKEN_TTL)
    return token


def _consume_confirm_token(token: str, item_id: int) -> bool:
    now = time.monotonic()
    expired = [k for k, (_, exp) in _confirm_tokens.items() if exp < now]
    for k in expired:
        _confirm_tokens.pop(k, None)
    entry = _confirm_tokens.pop(token, None)
    if entry is None:
        return False
    expected_id, expires_at = entry
    if now > expires_at:
        return False
    return expected_id == item_id


def _validate_scan_directory(directory: str) -> Path:
    """Resolve and validate a scan directory against the allowlisted base directories.

    Per SECURITY.md mandatory input validation rules: every file path accepted
    from any source must be resolved, normalised, and validated against an
    allowlist of permitted base directories before any filesystem operation.
    Only MEDIA_PATH (library/media/) is a permitted scan root — system files
    in library/system/ are never exposed via the scan endpoint.
    """
    if "\x00" in directory:
        logger.warning("Scan directory rejected: contains null byte (raw=%r)", directory)
        raise HTTPException(status_code=400, detail="Invalid path: contains a null byte.")

    resolved = Path(directory).resolve()

    try:
        from backend.core.settings import get_settings
        svc = get_settings()
        allowed_roots: list[Path] = []
        val = svc.get("MEDIA_PATH", "") or ""
        if val:
            allowed_roots.append(Path(val).resolve())
    except RuntimeError:
        allowed_roots = []

    if not allowed_roots:
        logger.warning("Scan rejected: MEDIA_PATH is not configured")
        raise HTTPException(
            status_code=400,
            detail=(
                "No media library path is configured. "
                "Set MEDIA_PATH in Settings before scanning."
            ),
        )

    within_allowed = any(
        resolved == root or resolved.is_relative_to(root)
        for root in allowed_roots
    )

    if not within_allowed:
        logger.warning(
            "Scan rejected: directory outside media library: directory=%r resolved=%s allowed=%s",
            directory,
            resolved,
            [str(r) for r in allowed_roots],
        )
        raise HTTPException(
            status_code=400,
            detail=(
                "Directory is outside the media library (library/media/). "
                "Only the media library may be scanned."
            ),
        )

    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="Path does not exist or is not a directory.")

    return resolved


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
    item.slug = generate_item_slug(item.title, item.era, db)

    svc = get_settings()
    games_root_str = svc.get("MEDIA_PATH", "") or ""
    if games_root_str:
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
                item.cover_path = str(cover)
        except OSError as exc:
            logger.warning("Could not create item folder %s: %s", item_folder, exc)

    from backend.service.utils.media_attach import detect_media_type
    media_type = detect_media_type(Path(item.media_path))
    item.media_type = media_type
    item.requires_install = media_type == "iso"
    source_size_mb = Path(item.media_path).stat().st_size / (1024 * 1024)
    multiplier = 1.5 if media_type == "iso" else 2.0
    item.drive_size_mb = min(max(int(source_size_mb * multiplier), 50), 500)

    if not item.content_rating:
        from backend.utils.rating_detect import detect_rating
        item.content_rating = detect_rating(body.media_path)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/scan/status")
def scan_status():
    with _scan_lock:
        return dict(_scan_state)


@router.post("/scan")
def trigger_scan(directory: str = Query(...), background_tasks: BackgroundTasks = BackgroundTasks()):
    with _scan_lock:
        if _scan_state["running"]:
            raise HTTPException(status_code=409, detail="A scan is already running.")

    validated_path = _validate_scan_directory(directory)

    with _scan_lock:
        _scan_state["running"] = True
        _scan_state["progress"] = 0
        _scan_state["total"] = 0
        _scan_state["results"] = []

    background_tasks.add_task(_run_scan, str(validated_path))
    return {"started": True, "directory": str(validated_path)}


def _run_scan(directory: str) -> None:
    from backend.service.utils.profile_builder import scan_directory
    try:
        results = scan_directory(Path(directory))
        serialisable = [
            {
                "path": str(e.path),
                "era": e.era.value if e.era is not None else None,
                "name": e.name,
            }
            for e in results
        ]
        with _scan_lock:
            _scan_state["results"] = serialisable
            _scan_state["total"] = len(serialisable)
            _scan_state["progress"] = len(serialisable)
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
    token = _issue_confirm_token(item_id)
    return {"confirmation_token": token, "expires_in_seconds": _TOKEN_TTL}


@router.delete("/{item_id}", status_code=204)
def delete_library_item(
    item_id: int,
    confirmation_token: str = Query(...),
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    if not _consume_confirm_token(confirmation_token, item_id):
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation token.")
    item = db.get(LibraryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Library item not found.")
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
