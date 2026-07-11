from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import get_active_user, require_permission
from backend.core.logger import get_logger
from backend.models.drive import Drive, DriveRead
from backend.models.software import SoftwareCollection
from backend.models.user import User
from backend.service.utils import confirmation_tokens
from backend.service.utils.confirmation_tokens import TOKEN_TTL

router = APIRouter(prefix="/api/v1/drives", tags=["drives"])
logger = get_logger(__name__)


@router.get("", response_model=list[DriveRead])
def list_drives(db: Session = Depends(get_db), _: User = Depends(get_active_user)):
    return db.query(Drive).all()


@router.get("/{drive_id}", response_model=DriveRead)
def get_drive(drive_id: int, db: Session = Depends(get_db), _: User = Depends(get_active_user)):
    drive = db.get(Drive, drive_id)
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found.")
    return drive


@router.get("/{drive_id}/confirm-token")
def issue_delete_token(
    drive_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("can_manage_software"),
):
    if not db.get(Drive, drive_id):
        raise HTTPException(status_code=404, detail="Drive not found.")
    return {"confirmation_token": confirmation_tokens.issue("drive", drive_id), "expires_in_seconds": TOKEN_TTL}


@router.delete("/{drive_id}", status_code=204)
def delete_drive(
    drive_id: int,
    confirmation_token: str = Query(...),
    db: Session = Depends(get_db),
    _: User = require_permission("can_manage_software"),
):
    if not confirmation_tokens.consume(confirmation_token, "drive", drive_id):
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation token.")
    drive = db.get(Drive, drive_id)
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found.")
    if drive.image_path:
        img_path = Path(drive.image_path)
        if img_path.exists():
            img_path.unlink()
            logger.info("Deleted drive image: %s", img_path)
    db.query(SoftwareCollection).filter(SoftwareCollection.drive_id == drive_id).update({"drive_id": None})
    db.flush()
    db.delete(drive)
    db.commit()
