import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import require_permission
from backend.core.logger import get_logger
from backend.models.drive import Drive, DriveRead
from backend.models.user import User

router = APIRouter(prefix="/api/v1/drives", tags=["drives"])
logger = get_logger(__name__)

_TOKEN_TTL = 60
_confirm_tokens: dict[str, tuple[int, float]] = {}


def _issue_token(drive_id: int) -> str:
    token = secrets.token_urlsafe(32)
    _confirm_tokens[token] = (drive_id, time.monotonic() + _TOKEN_TTL)
    return token


def _consume_token(token: str, drive_id: int) -> bool:
    now = time.monotonic()
    expired = [k for k, (_, exp) in _confirm_tokens.items() if exp < now]
    for k in expired:
        _confirm_tokens.pop(k, None)
    entry = _confirm_tokens.pop(token, None)
    if entry is None:
        return False
    stored_id, expires_at = entry
    return stored_id == drive_id and expires_at >= now


@router.get("", response_model=list[DriveRead])
def list_drives(db: Session = Depends(get_db)):
    return db.query(Drive).all()


@router.get("/{drive_id}", response_model=DriveRead)
def get_drive(drive_id: int, db: Session = Depends(get_db)):
    drive = db.get(Drive, drive_id)
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found.")
    return drive


@router.get("/{drive_id}/confirm-token")
def issue_delete_token(
    drive_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    if not db.get(Drive, drive_id):
        raise HTTPException(status_code=404, detail="Drive not found.")
    return {"confirmation_token": _issue_token(drive_id), "expires_in_seconds": _TOKEN_TTL}


@router.delete("/{drive_id}", status_code=204)
def delete_drive(
    drive_id: int,
    confirmation_token: str = Query(...),
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    if not _consume_token(confirmation_token, drive_id):
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation token.")
    drive = db.get(Drive, drive_id)
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found.")
    if drive.image_path:
        img_path = Path(drive.image_path)
        if img_path.exists():
            img_path.unlink()
            logger.info("Deleted drive image: %s", img_path)
    db.delete(drive)
    db.commit()
