import re
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import require_permission
from backend.core.logger import get_logger
from backend.core.settings import get_base_path
from backend.models.drive import Drive, DriveCreate, DriveRead
from backend.models.user import User

router = APIRouter(prefix="/api/v1/drives", tags=["drives"])
logger = get_logger(__name__)

_TOKEN_TTL = 60
_confirm_tokens: dict[str, tuple[str, float]] = {}
_SLUG_RE = re.compile(r"^[a-z0-9-]+$")


def _validate_drive_slug(slug: str) -> None:
    if not slug or not _SLUG_RE.match(slug) or len(slug) > 64:
        raise HTTPException(
            status_code=422,
            detail="Drive slug must contain only lowercase letters, digits, and hyphens (max 64 chars).",
        )


def _issue_token(slug: str) -> str:
    token = secrets.token_urlsafe(32)
    _confirm_tokens[token] = (slug, time.monotonic() + _TOKEN_TTL)
    return token


def _consume_token(token: str, slug: str) -> bool:
    now = time.monotonic()
    expired = [k for k, (_, exp) in _confirm_tokens.items() if exp < now]
    for k in expired:
        _confirm_tokens.pop(k, None)
    entry = _confirm_tokens.pop(token, None)
    if entry is None:
        return False
    stored_slug, expires_at = entry
    return stored_slug == slug and expires_at >= now


@router.get("", response_model=list[DriveRead])
def list_drives(db: Session = Depends(get_db)):
    return db.query(Drive).all()


@router.post("", response_model=DriveRead, status_code=201)
def create_drive(
    body: DriveCreate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    _validate_drive_slug(body.slug)
    existing = db.query(Drive).filter(Drive.slug == body.slug).first()
    if existing:
        raise HTTPException(status_code=409, detail="Drive slug already exists.")
    drive = Drive(**body.model_dump())
    db.add(drive)
    db.commit()
    db.refresh(drive)
    logger.info("Created drive record: slug=%s size_mb=%d era=%s", drive.slug, drive.size_mb, drive.era)
    return drive


@router.get("/{slug}/confirm-token")
def issue_delete_token(
    slug: str,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    if not db.query(Drive).filter(Drive.slug == slug).first():
        raise HTTPException(status_code=404, detail="Drive not found.")
    return {"confirmation_token": _issue_token(slug), "expires_in_seconds": _TOKEN_TTL}


@router.delete("/{slug}", status_code=204)
def delete_drive(
    slug: str,
    confirmation_token: str = Query(...),
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    if not _consume_token(confirmation_token, slug):
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation token.")
    drive = db.query(Drive).filter(Drive.slug == slug).first()
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found.")
    img_path = get_base_path() / "library" / "system" / "drives" / f"{slug}.img"
    if img_path.exists():
        img_path.unlink()
        logger.info("Deleted drive image: %s", img_path)
    db.delete(drive)
    db.commit()
