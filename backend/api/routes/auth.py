import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import case, update
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.identity import clear_session, extend_session, generate_identity_secret, issue_session, parse_session_cookie, validate_session
from backend.core.logger import get_logger
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


def _cookies_secure() -> bool:
    from backend.core.settings import get_settings
    return bool(get_settings().get("ALLOW_NETWORK_ACCESS", False))


def _set_auth_cookie(response: Response, user_id: int, token: str, session_token_ttl) -> None:
    max_age = (session_token_ttl * 60) if session_token_ttl is not None else (30 * 24 * 60 * 60)
    response.set_cookie(
        key=_COOKIE_NAME,
        value=f"{user_id}.{token}",
        httponly=True,
        samesite="lax",
        secure=_cookies_secure(),
        max_age=max_age,
    )


def _set_csrf_cookie(response: Response, session_token_ttl) -> None:
    csrf_token = secrets.token_urlsafe(32)
    max_age = (session_token_ttl * 60) if session_token_ttl is not None else (30 * 24 * 60 * 60)
    response.set_cookie(
        key=_CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,  # must be JS-readable so the client can submit it as a header
        samesite="lax",
        secure=_cookies_secure(),
        max_age=max_age,
    )


def _record_failed_pin_attempt(db: Session, user: User) -> None:
    """Atomically increment failed_pin_attempts and lock the account at the threshold.

    A single UPDATE (not read-then-write on the ORM attribute) so concurrent
    requests can't each read the same pre-increment count and both slip past
    the >= 4 threshold.
    """
    stmt = (
        update(User)
        .where(User.id == user.id)
        .values(
            failed_pin_attempts=User.failed_pin_attempts + 1,
            is_locked=case(
                (User.failed_pin_attempts + 1 >= 4, True),
                else_=User.is_locked,
            ),
        )
    )
    db.execute(stmt)
    db.commit()
    db.refresh(user)
    if user.is_locked:
        logger.warning("User %d locked after %d failed PIN attempts.", user.id, user.failed_pin_attempts)


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
        identity_token_secret=generate_identity_secret(),
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    token, _expires_at = issue_session(db, owner)
    _set_auth_cookie(response, owner.id, token, owner.session_token_ttl)
    _set_csrf_cookie(response, owner.session_token_ttl)
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
            _record_failed_pin_attempt(db, user)
            raise HTTPException(status_code=401, detail="Invalid PIN.")
        user.failed_pin_attempts = 0
        db.commit()
        token, _expires_at = issue_session(db, user)
        _set_auth_cookie(response, user.id, token, user.session_token_ttl)
        _set_csrf_cookie(response, user.session_token_ttl)
        return {"user": user}

    if not user.pin_required:
        user.failed_pin_attempts = 0
        db.commit()
        token, _expires_at = issue_session(db, user)
        _set_auth_cookie(response, user.id, token, user.session_token_ttl)
        _set_csrf_cookie(response, user.session_token_ttl)
        return {"user": user}

    if user.pin_hash is None or not _verify_pin(body.pin, user.pin_hash):
        _record_failed_pin_attempt(db, user)
        raise HTTPException(status_code=401, detail="Invalid PIN.")

    user.failed_pin_attempts = 0
    db.commit()
    token, _expires_at = issue_session(db, user)
    _set_auth_cookie(response, user.id, token, user.session_token_ttl)
    _set_csrf_cookie(response, user.session_token_ttl)
    return {"user": user}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    cookie = request.cookies.get(_COOKIE_NAME)
    if cookie:
        parsed = parse_session_cookie(cookie)
        if parsed is not None:
            # Only clear the session if the presented token actually validates —
            # otherwise a guessed/garbage token paired with someone else's
            # user_id could force-clear an arbitrary account with no proof of
            # possession of their real token.
            user = validate_session(db, parsed[0], parsed[1])
            if user is not None:
                clear_session(db, user)
    response.delete_cookie(key=_COOKIE_NAME, httponly=True, samesite="lax")
    response.delete_cookie(key=_CSRF_COOKIE_NAME, httponly=False, samesite="lax")
    return {"success": True}


@router.get("/me", response_model=UserRead)
def me(request: Request, db: Session = Depends(get_db)):
    cookie = request.cookies.get(_COOKIE_NAME)
    if not cookie:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    parsed = parse_session_cookie(cookie)
    if parsed is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    user = validate_session(db, parsed[0], parsed[1])
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    return user


@router.post("/refresh", response_model=UserResponse)
def refresh_session(request: Request, response: Response, db: Session = Depends(get_db)):
    """Validate the existing session token and extend its expiry, without rotating it.

    Called on every app open so sessions extend automatically. The token itself
    is left untouched (session_token_hash is not overwritten) — minting a new
    token here would invalidate a still-in-flight refresh from the same
    session (StrictMode double-mount, multiple tabs, retries), 401-ing the
    second legitimate caller. Token issuance stays exclusive to
    login/switch/setup-owner.
    """
    cookie = request.cookies.get(_COOKIE_NAME)
    if not cookie:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    parsed = parse_session_cookie(cookie)
    if parsed is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    user = validate_session(db, parsed[0], parsed[1])
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    extend_session(db, user)
    if user.session_token_ttl is not None:
        _set_auth_cookie(response, user.id, parsed[1], user.session_token_ttl)
    _set_csrf_cookie(response, user.session_token_ttl)
    return {"user": user}
