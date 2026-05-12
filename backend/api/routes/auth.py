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


@router.post("/switch", response_model=UserRead)
def switch_user(body: SwitchRequest, request: Request, db: Session = Depends(get_db)):
    user = db.get(User, body.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    if user.is_locked:
        raise HTTPException(status_code=403, detail="Account is locked.")

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
