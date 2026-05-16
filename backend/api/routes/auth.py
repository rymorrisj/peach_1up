import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.models.user import User, UserRead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class SwitchRequest(BaseModel):
    user_id: int
    pin: str


class SetupOwnerRequest(BaseModel):
    name: str
    pin: str
    confirm_pin: str


def _verify_pin(pin: str, pin_hash: str) -> bool:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerificationError, VerifyMismatchError

    ph = PasswordHasher()
    try:
        return ph.verify(pin_hash, pin)
    except VerifyMismatchError:
        return False
    except (VerificationError, Exception) as exc:
        logger.warning("PIN verification error: %s", exc)
        return False


@router.post("/setup-owner")
def setup_owner(body: SetupOwnerRequest, db: Session = Depends(get_db)):
    has_owner = db.query(User).filter(User.is_owner.is_(True)).count() > 0
    if has_owner:
        raise HTTPException(status_code=409, detail="Owner account already exists.")

    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Name is required.")
    if not body.pin.isdigit() or not (4 <= len(body.pin) <= 6):
        raise HTTPException(status_code=400, detail="PIN must be 4–6 digits.")
    if body.pin != body.confirm_pin:
        raise HTTPException(status_code=400, detail="PINs do not match.")

    from argon2 import PasswordHasher
    ph = PasswordHasher()
    pin_hash = ph.hash(body.pin)

    owner = User(
        name=body.name.strip(),
        is_owner=True,
        is_admin=True,
        pin_required=True,
        can_launch_media=True,
        can_edit_platforms=True,
        can_edit_library=True,
        can_manage_profiles=True,
        can_edit_settings=True,
        pin_hash=pin_hash,
    )
    db.add(owner)
    db.commit()
    logger.info("Owner account created for %r", body.name.strip())
    return {"success": True}


@router.post("/switch", response_model=UserRead)
def switch_user(body: SwitchRequest, request: Request, db: Session = Depends(get_db)):
    user = db.get(User, body.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    if user.is_locked:
        raise HTTPException(status_code=403, detail="Account is locked.")

    if not user.pin_required:
        user.failed_pin_attempts = 0
        db.commit()
        request.session["active_user_id"] = user.id
        return user

    if user.pin_hash is None or not _verify_pin(body.pin, user.pin_hash):
        user.failed_pin_attempts = (user.failed_pin_attempts or 0) + 1
        if user.failed_pin_attempts >= 4:
            user.is_locked = True
            logger.warning("User %d locked after %d failed PIN attempts.", user.id, user.failed_pin_attempts)
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid PIN.")

    user.failed_pin_attempts = 0
    db.commit()
    request.session["active_user_id"] = user.id
    return user


@router.post("/logout", response_model=UserRead)
def logout(request: Request, db: Session = Depends(get_db)):
    request.session.pop("active_user_id", None)
    owner = db.query(User).filter(User.is_owner.is_(True)).first()
    if owner is None:
        raise HTTPException(status_code=503, detail="No owner account configured.")
    return owner


@router.get("/me", response_model=UserRead)
def me(request: Request, db: Session = Depends(get_db)):
    try:
        from backend.core.settings import get_settings
    except RuntimeError:
        pass

    owner = db.query(User).filter(User.is_owner.is_(True)).first()
    if owner is None:
        raise HTTPException(status_code=503, detail="No owner account configured.")

    user_id = request.session.get("active_user_id")
    if user_id is None:
        return owner

    user = db.get(User, user_id)
    return user if user is not None else owner
