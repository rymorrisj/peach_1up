import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.logger import get_logger
from backend.core.token_store import create_token, resolve_token, revoke_token
from backend.models.user import User, UserRead

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_COOKIE_NAME = "peach_token"
_CSRF_COOKIE_NAME = "peach_csrf"


class SwitchRequest(BaseModel):
    user_id: int
    pin: str = ""


class SetupOwnerRequest(BaseModel):
    name: str
    pin: str
    confirm_pin: str


class UserResponse(BaseModel):
    user: UserRead


def _set_auth_cookie(response: Response, token: str, session_expiry_minutes) -> None:
    max_age = (session_expiry_minutes * 60) if session_expiry_minutes is not None else (30 * 24 * 60 * 60)
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=max_age,
    )


def _set_csrf_cookie(response: Response, session_expiry_minutes) -> None:
    csrf_token = secrets.token_urlsafe(32)
    max_age = (session_expiry_minutes * 60) if session_expiry_minutes is not None else (30 * 24 * 60 * 60)
    response.set_cookie(
        key=_CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,  # must be JS-readable so the client can submit it as a header
        samesite="lax",
        secure=False,
        max_age=max_age,
    )


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


@router.post("/setup-owner", response_model=UserResponse)
def setup_owner(body: SetupOwnerRequest, response: Response, db: Session = Depends(get_db)):
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
    db.refresh(owner)

    token = create_token(db, owner.id, owner.session_expiry_minutes)
    _set_auth_cookie(response, token, owner.session_expiry_minutes)
    _set_csrf_cookie(response, owner.session_expiry_minutes)
    logger.info("Owner account created for %r", body.name.strip())
    return {"user": owner}


@router.post("/switch", response_model=UserResponse)
def switch_user(body: SwitchRequest, response: Response, db: Session = Depends(get_db)):
    user = db.get(User, body.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    if user.is_locked:
        raise HTTPException(status_code=403, detail="Account is locked.")

    if user.is_owner:
        if not body.pin:
            raise HTTPException(status_code=400, detail="Owner account requires a PIN.")
        if user.pin_hash is None or not _verify_pin(body.pin, user.pin_hash):
            user.failed_pin_attempts = (user.failed_pin_attempts or 0) + 1
            if user.failed_pin_attempts >= 4:
                user.is_locked = True
                logger.warning("User %d locked after %d failed PIN attempts.", user.id, user.failed_pin_attempts)
            db.commit()
            raise HTTPException(status_code=401, detail="Invalid PIN.")
        user.failed_pin_attempts = 0
        db.commit()
        token = create_token(db, user.id, user.session_expiry_minutes)
        _set_auth_cookie(response, token, user.session_expiry_minutes)
        _set_csrf_cookie(response, user.session_expiry_minutes)
        return {"user": user}

    if not user.pin_required:
        user.failed_pin_attempts = 0
        db.commit()
        token = create_token(db, user.id, user.session_expiry_minutes)
        _set_auth_cookie(response, token, user.session_expiry_minutes)
        _set_csrf_cookie(response, user.session_expiry_minutes)
        return {"user": user}

    if user.pin_hash is None or not _verify_pin(body.pin, user.pin_hash):
        user.failed_pin_attempts = (user.failed_pin_attempts or 0) + 1
        if user.failed_pin_attempts >= 4:
            user.is_locked = True
            logger.warning("User %d locked after %d failed PIN attempts.", user.id, user.failed_pin_attempts)
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid PIN.")

    user.failed_pin_attempts = 0
    db.commit()
    token = create_token(db, user.id, user.session_expiry_minutes)
    _set_auth_cookie(response, token, user.session_expiry_minutes)
    return {"user": user}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token_str = request.cookies.get(_COOKIE_NAME)
    if token_str:
        revoke_token(db, token_str)
    response.delete_cookie(key=_COOKIE_NAME, httponly=True, samesite="lax")
    response.delete_cookie(key=_CSRF_COOKIE_NAME, httponly=False, samesite="lax")
    return {"success": True}


@router.get("/me", response_model=UserRead)
def me(request: Request, db: Session = Depends(get_db)):
    token_str = request.cookies.get(_COOKIE_NAME)
    if not token_str:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    user = resolve_token(db, token_str)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    return user


@router.post("/refresh", response_model=UserResponse)
def refresh_session(request: Request, response: Response, db: Session = Depends(get_db)):
    """Rotate the session token and reset the CSRF cookie.

    Called on every app open so sessions extend automatically. The old token is
    revoked after the new one is committed — the user is never left without a
    valid session even if the second write fails.
    """
    token_str = request.cookies.get(_COOKIE_NAME)
    if not token_str:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    user = resolve_token(db, token_str)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    new_token = create_token(db, user.id, user.session_expiry_minutes)
    _set_auth_cookie(response, new_token, user.session_expiry_minutes)
    _set_csrf_cookie(response, user.session_expiry_minutes)
    revoke_token(db, token_str)
    return {"user": user}
