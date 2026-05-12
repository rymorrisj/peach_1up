import logging
import secrets
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import get_active_user, get_filtered_library, require_permission
from backend.models.library import LibraryItem, LibraryItemCreate, LibraryItemRead, LibraryItemUpdate
from backend.models.user import User

router = APIRouter(prefix="/api/v1/library", tags=["library"])
logger = logging.getLogger(__name__)

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
    Permitted base directories are IMAGES_PATH, PROFILES_PATH, and ROM_PATH.
    """
    if "\x00" in directory:
        logger.warning("Scan directory rejected: contains null byte (raw=%r)", directory)
        raise HTTPException(status_code=400, detail="Invalid path: contains a null byte.")

    resolved = Path(directory).resolve()

    try:
        from backend.core.settings import get_settings
        svc = get_settings()
        allowed_roots: list[Path] = []
        for key in ("IMAGES_PATH", "PROFILES_PATH", "ROM_PATH"):
            val = svc.get(key, "") or ""
            if val:
                allowed_roots.append(Path(val).resolve())
    except RuntimeError:
        allowed_roots = []

    if not allowed_roots:
        logger.warning("Scan rejected: no allowed base directories are configured")
        raise HTTPException(
            status_code=400,
            detail=(
                "No scan base directories are configured. "
                "Set IMAGES_PATH in Settings before scanning."
            ),
        )

    within_allowed = any(
        resolved == root or resolved.is_relative_to(root)
        for root in allowed_roots
    )

    if not within_allowed:
        logger.warning(
            "Path traversal attempt on scan endpoint: directory=%r resolved=%s allowed=%s",
            directory,
            resolved,
            [str(r) for r in allowed_roots],
        )
        raise HTTPException(
            status_code=400,
            detail=(
                "Directory is outside the permitted scan locations "
                "(IMAGES_PATH, PROFILES_PATH, ROM_PATH). "
                "Update your path settings to include this location."
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
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    item = LibraryItem(**body.model_dump())
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
