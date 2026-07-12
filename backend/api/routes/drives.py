from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import get_active_user
from backend.core.logger import get_logger
from backend.models.app import AppItemBundle
from backend.models.drive import Drive, DriveRead
from backend.models.game import GameItemBundle
from backend.models.user import User
from backend.service.utils import confirmation_tokens
from backend.service.utils.confirmation_tokens import TOKEN_TTL

router = APIRouter(prefix="/api/v1/drives", tags=["drives"])
logger = get_logger(__name__)


def _require_drive_owner_permission(drive: Drive, active_user: User) -> None:
    """Gate a drive mutation on the permission matching its owning collection.

    Exactly one of game_item_bundle_id / app_item_bundle_id is ever set on a
    Drive (enforced by Drive.model_post_init) -- app-owned drives require
    can_manage_apps, software-owned drives require can_manage_software
    (unchanged from before Apps existed).
    """
    if active_user.is_owner:
        return
    flag = "can_manage_apps" if drive.app_item_bundle_id is not None else "can_manage_software"
    if not getattr(active_user, flag, False):
        raise HTTPException(status_code=403, detail=f"Permission denied: requires {flag}.")


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
    active_user: User = Depends(get_active_user),
):
    drive = db.get(Drive, drive_id)
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found.")
    _require_drive_owner_permission(drive, active_user)
    return {"confirmation_token": confirmation_tokens.issue("drive", drive_id), "expires_in_seconds": TOKEN_TTL}


@router.delete("/{drive_id}", status_code=204)
def delete_drive(
    drive_id: int,
    confirmation_token: str = Query(...),
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
):
    drive = db.get(Drive, drive_id)
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found.")
    _require_drive_owner_permission(drive, active_user)
    if not confirmation_tokens.consume(confirmation_token, "drive", drive_id):
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation token.")
    if drive.image_path:
        img_path = Path(drive.image_path)
        if img_path.exists():
            img_path.unlink()
            logger.info("Deleted drive image: %s", img_path)
    if drive.app_item_bundle_id is not None:
        db.query(AppItemBundle).filter(AppItemBundle.drive_id == drive_id).update({"drive_id": None})
    else:
        db.query(GameItemBundle).filter(GameItemBundle.drive_id == drive_id).update({"drive_id": None})
    db.flush()
    db.delete(drive)
    db.commit()
