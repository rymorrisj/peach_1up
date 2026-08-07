import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import case, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core import rate_limit
from backend.core.database import get_db
from backend.core.identity import clear_session, extend_session, generate_identity_secret, issue_session, parse_session_cookie, validate_session
from backend.core.logger import get_logger
from backend.models.user import UserItem, UserItemRead

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_COOKIE_NAME = "peach_token"
_CSRF_COOKIE_NAME = "peach_csrf"

# Bounds total /auth/switch attempts per source IP, independent of the
# per-user PIN lockout counter, without this, a remote actor can enumerate
# users via GET /api/v1/user-items and brute-force/lock any account (including
# owner) with unlimited unauthenticated requests. This is a household
# device where several sub-accounts share one source IP (same LAN/localhost),
# so the budget has to absorb normal multi-account traffic, the per-account
# 4-attempt lockout is the actual brake on guessing any single account's PIN;
# this cap exists to stop high-volume automated sweeps across many accounts,
# not to police ordinary retries.
_SWITCH_RATE_LIMIT = 30
_SWITCH_RATE_WINDOW_SECONDS = 60.0


class SwitchRequest(BaseModel):
    user_item_id: int
    pin: str = ""


class SetupOwnerRequest(BaseModel):
    name: str
    pin: str
    confirm_pin: str


class UserResponse(BaseModel):
    user: UserItemRead


def _cookies_secure() -> bool:
    from backend.core.settings import get_settings
    return bool(get_settings().get("ALLOW_NETWORK_ACCESS", False))


def _set_auth_cookie(response: Response, user_item_id: int, token: str, session_token_ttl) -> None:
    max_age = (session_token_ttl * 60) if session_token_ttl is not None else (30 * 24 * 60 * 60)
    response.set_cookie(
        key=_COOKIE_NAME,
        value=f"{user_item_id}.{token}",
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


def _record_failed_pin_attempt(db: Session, user: UserItem) -> None:
    """Atomically increment failed_pin_attempts and lock the account at the threshold.

    A single UPDATE (not read-then-write on the ORM attribute) so concurrent
    requests can't each read the same pre-increment count and both slip past
    the >= 4 threshold.
    """
    stmt = (
        update(UserItem)
        .where(UserItem.id == user.id)
        .values(
            failed_pin_attempts=UserItem.failed_pin_attempts + 1,
            is_locked=case(
                (UserItem.failed_pin_attempts + 1 >= 4, True),
                else_=UserItem.is_locked,
            ),
        )
    )
    db.execute(stmt)
    db.commit()
    db.refresh(user)
    if user.is_locked:
        logger.warning("User %d locked after %d failed PIN attempts.", user.id, user.failed_pin_attempts)


def _verify_pin(pin: str, pin_hash: str) -> bool:
    from backend.service.utils.pin_hashing import verify_pin
    return verify_pin(pin, pin_hash)


def _complete_login(response: Response, db: Session, user: UserItem) -> dict:
    user.failed_pin_attempts = 0
    db.commit()
    token, _expires_at = issue_session(db, user)
    _set_auth_cookie(response, user.id, token, user.session_token_ttl)
    _set_csrf_cookie(response, user.session_token_ttl)
    return {"user": user}


def _get_session_user(request: Request, db: Session) -> tuple[UserItem, str]:
    cookie = request.cookies.get(_COOKIE_NAME)
    if not cookie:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    parsed = parse_session_cookie(cookie)
    if parsed is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    user = validate_session(db, parsed[0], parsed[1])
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    return user, parsed[1]


@router.post("/setup-owner", response_model=UserResponse)
def setup_owner(body: SetupOwnerRequest, response: Response, db: Session = Depends(get_db)):
    # Fast-path / friendly-error only. This SELECT COUNT is NOT the real guard:
    # two concurrent requests can both read count==0 here and both fall through
    # to the INSERT before either commits (TOCTOU). The idx_single_owner partial
    # unique index is the actual guarantee, the losing racer's commit raises
    # IntegrityError, caught below and mapped to the same 409.
    has_owner = db.query(UserItem).filter(UserItem.is_owner.is_(True)).count() > 0
    if has_owner:
        raise HTTPException(status_code=409, detail="Owner account already exists.")

    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Name is required.")
    if not body.pin.isdigit() or not (4 <= len(body.pin) <= 6):
        raise HTTPException(status_code=400, detail="PIN must be 4–6 digits.")
    if body.pin != body.confirm_pin:
        raise HTTPException(status_code=400, detail="PINs do not match.")

    from backend.service.utils.pin_hashing import hash_pin
    pin_hash = hash_pin(body.pin)

    owner = UserItem(
        name=body.name.strip(),
        is_owner=True,
        is_admin=True,
        pin_required=True,
        can_launch_media=True,
        can_manage_environment=True,
        can_manage_game=True,
        can_manage_media=True,
        can_manage_app=True,
        can_manage_controllerMapping=True,
        can_manage_settings=True,
        pin_hash=pin_hash,
        identity_token_secret=generate_identity_secret(),
    )
    db.add(owner)
    try:
        db.commit()
    except IntegrityError:
        # Lost the race: another request committed the owner between our
        # pre-check and this commit, and idx_single_owner rejected this second
        # owner row. Surface the same 409 as the pre-check, never a raw 500.
        db.rollback()
        raise HTTPException(status_code=409, detail="Owner account already exists.")
    db.refresh(owner)

    token, _expires_at = issue_session(db, owner)
    _set_auth_cookie(response, owner.id, token, owner.session_token_ttl)
    _set_csrf_cookie(response, owner.session_token_ttl)
    logger.info("Owner account created for %r", body.name.strip())
    return {"user": owner}


@router.post("/switch", response_model=UserResponse)
def switch_user(body: SwitchRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    # Keyed on the immediate TCP peer, not X-Forwarded-For, that header is
    # attacker-controlled unless a trusted reverse proxy strips/sets it, and
    # trusting it here would let the same attacker we're rate-limiting just
    # spoof a fresh IP on every request to bypass the limit.
    allowed, retry_after = rate_limit.check_and_record(
        f"auth-switch:{client_ip}", _SWITCH_RATE_LIMIT, _SWITCH_RATE_WINDOW_SECONDS
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts from this address. Try again shortly.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )

    user = db.get(UserItem, body.user_item_id)
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
        return _complete_login(response, db, user)

    if not user.pin_required:
        return _complete_login(response, db, user)

    if user.pin_hash is None or not _verify_pin(body.pin, user.pin_hash):
        _record_failed_pin_attempt(db, user)
        raise HTTPException(status_code=401, detail="Invalid PIN.")

    return _complete_login(response, db, user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    cookie = request.cookies.get(_COOKIE_NAME)
    if cookie:
        parsed = parse_session_cookie(cookie)
        if parsed is not None:
            # Only clear the session if the presented token actually validates —
            # otherwise a guessed/garbage token paired with someone else's
            # user_item_id could force-clear an arbitrary account with no proof of
            # possession of their real token.
            user = validate_session(db, parsed[0], parsed[1])
            if user is not None:
                clear_session(db, user)
    response.delete_cookie(key=_COOKIE_NAME, httponly=True, samesite="lax")
    response.delete_cookie(key=_CSRF_COOKIE_NAME, httponly=False, samesite="lax")
    return {"success": True}


@router.get("/me", response_model=UserItemRead)
def me(request: Request, db: Session = Depends(get_db)):
    user, _ = _get_session_user(request, db)
    return user


@router.post("/refresh", response_model=UserResponse)
def refresh_session(request: Request, response: Response, db: Session = Depends(get_db)):
    """Validate the existing session token and extend its expiry, without rotating it.

    Called on every app open so sessions extend automatically. The token itself
    is left untouched (session_token_hash is not overwritten), minting a new
    token here would invalidate a still-in-flight refresh from the same
    session (StrictMode double-mount, multiple tabs, retries), 401-ing the
    second legitimate caller. Token issuance stays exclusive to
    login/switch/setup-owner.
    """
    user, token = _get_session_user(request, db)
    extend_session(db, user)
    if user.session_token_ttl is not None:
        _set_auth_cookie(response, user.id, token, user.session_token_ttl)
    _set_csrf_cookie(response, user.session_token_ttl)
    return {"user": user}
