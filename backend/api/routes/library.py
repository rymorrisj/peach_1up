import secrets
import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.models import LibraryItem
from backend.schemas.library import LibraryItemCreate, LibraryItemRead, LibraryItemUpdate

router = APIRouter(prefix="/api/v1/library", tags=["library"])

# In-memory scan state — cleared on each new scan
_scan_state: dict[str, Any] = {"running": False, "progress": 0, "total": 0, "results": []}

# Confirmation tokens: {token: (resource_id, expires_at)}
_confirm_tokens: dict[str, tuple[int, float]] = {}

_TOKEN_TTL = 60  # seconds


def _issue_confirm_token(item_id: int) -> str:
    token = secrets.token_urlsafe(32)
    _confirm_tokens[token] = (item_id, time.monotonic() + _TOKEN_TTL)
    return token


def _consume_confirm_token(token: str, item_id: int) -> bool:
    entry = _confirm_tokens.pop(token, None)
    if entry is None:
        return False
    expected_id, expires_at = entry
    if time.monotonic() > expires_at:
        return False
    return expected_id == item_id


@router.get("", response_model=list[LibraryItemRead])
def list_library(
    era: str | None = None,
    category: str | None = None,
    platform_id: int | None = None,
    tag: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(LibraryItem)
    if era:
        q = q.filter(LibraryItem.era == era)
    if category:
        q = q.filter(LibraryItem.category == category)
    if platform_id is not None:
        q = q.filter(LibraryItem.platform_id == platform_id)
    return q.all()


@router.post("", response_model=LibraryItemRead, status_code=201)
def add_library_item(body: LibraryItemCreate, db: Session = Depends(get_db)):
    item = LibraryItem(**body.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/scan/status")
def scan_status():
    return _scan_state


@router.post("/scan")
def trigger_scan(directory: str = Query(...), background_tasks: BackgroundTasks = BackgroundTasks()):
    if _scan_state["running"]:
        raise HTTPException(status_code=409, detail="A scan is already running.")
    background_tasks.add_task(_run_scan, directory)
    return {"started": True, "directory": directory}


def _run_scan(directory: str) -> None:
    from backend.service.utils.profile_builder import scan_directory
    _scan_state["running"] = True
    _scan_state["progress"] = 0
    _scan_state["results"] = []
    try:
        results = scan_directory(directory)
        _scan_state["results"] = [vars(r) for r in results]
        _scan_state["total"] = len(results)
        _scan_state["progress"] = len(results)
    finally:
        _scan_state["running"] = False


@router.get("/{item_id}", response_model=LibraryItemRead)
def get_library_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(LibraryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Library item not found.")
    return item


@router.patch("/{item_id}", response_model=LibraryItemRead)
def update_library_item(item_id: int, body: LibraryItemUpdate, db: Session = Depends(get_db)):
    item = db.get(LibraryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Library item not found.")
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/confirm-delete")
def issue_delete_token(item_id: int, db: Session = Depends(get_db)):
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
):
    if not _consume_confirm_token(confirmation_token, item_id):
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation token.")
    item = db.get(LibraryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Library item not found.")
    db.delete(item)
    db.commit()
