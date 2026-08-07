import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional


def generate_identity_secret() -> str:
    """Root-of-trust HMAC key for a user, generated once at account creation."""
    return secrets.token_hex(32)


def mint_session_token(identity_secret: str) -> tuple[str, datetime]:
    nonce = secrets.token_hex(16)
    issued_at = datetime.now(timezone.utc)
    session_token = hmac.new(
        identity_secret.encode(),
        f"{nonce}.{issued_at.isoformat()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return session_token, issued_at


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_session(db, user) -> tuple[str, Optional[datetime]]:
    """Mint a new session token for *user*, overwriting any prior session.

    One active session per user by design, a new login naturally invalidates
    any previous session since the hash is overwritten, not appended.
    """
    if not user.identity_token_secret:
        # Lazily backfilled for rows created before this column existed, or
        # created by a path that doesn't set it explicitly (e.g. the CLI
        # owner-recovery script), guarantees issue_session always works.
        user.identity_token_secret = generate_identity_secret()

    token, _issued_at = mint_session_token(user.identity_token_secret)
    user.session_token_hash = hash_session_token(token)
    user.session_token_expires_at = (
        datetime.now(timezone.utc) + timedelta(minutes=user.session_token_ttl)
        if user.session_token_ttl is not None
        else None
    )
    db.add(user)
    db.commit()
    return token, user.session_token_expires_at


def extend_session(db, user) -> Optional[datetime]:
    """Push out *user*'s existing session expiry without rotating the token.

    Unlike issue_session, this never touches session_token_hash, the caller
    has already validated the presented token, so there is no new token to
    roll back and the two-row rollback-safety tradeoff doesn't apply here.
    """
    user.session_token_expires_at = (
        datetime.now(timezone.utc) + timedelta(minutes=user.session_token_ttl)
        if user.session_token_ttl is not None
        else None
    )
    db.add(user)
    db.commit()
    return user.session_token_expires_at


def clear_session(db, user) -> None:
    user.session_token_hash = None
    user.session_token_expires_at = None
    db.add(user)
    db.commit()


def validate_session(db, user_item_id: int, presented_token: str):
    from backend.models.user import UserItem

    user = db.get(UserItem, user_item_id)
    if user is None:
        return None
    if user.session_token_hash is None:
        return None

    expires_at = user.session_token_expires_at
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            return None

    if not hmac.compare_digest(hash_session_token(presented_token), user.session_token_hash):
        return None
    return user


def parse_session_cookie(cookie: str) -> Optional[tuple[int, str]]:
    """Split the ``peach_token`` cookie value into ``(user_item_id, token)``.

    Returns None if the cookie has no separator or a non-numeric user_item_id —
    callers must treat that as unauthenticated, never as a lookup of 0/None.
    """
    user_item_id_str, sep, token = cookie.partition(".")
    if not sep or not user_item_id_str.isdigit():
        return None
    return int(user_item_id_str), token
