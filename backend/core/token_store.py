import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional


def create_token(db, user_id: int, session_expiry_minutes: Optional[int]) -> str:
    from backend.models.auth_token import AuthToken

    token_str = secrets.token_urlsafe(32)
    issued_at = datetime.now(timezone.utc)
    expires_at = (
        issued_at + timedelta(minutes=session_expiry_minutes)
        if session_expiry_minutes is not None
        else None
    )
    row = AuthToken(
        token=token_str,
        user_id=user_id,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    db.add(row)
    db.commit()
    return token_str


def resolve_token(db, token_str: str):
    from backend.models.auth_token import AuthToken
    from backend.models.user import User

    row = (
        db.query(AuthToken)
        .filter(AuthToken.token == token_str, AuthToken.revoked.is_(False))
        .first()
    )
    if row is None:
        return None
    expires_at = row.expires_at
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            return None
    return db.get(User, row.user_id)


def revoke_token(db, token_str: str) -> None:
    from backend.models.auth_token import AuthToken

    row = db.query(AuthToken).filter(AuthToken.token == token_str).first()
    if row is not None:
        row.revoked = True
        db.commit()


def cleanup_expired_tokens(db) -> None:
    from backend.models.auth_token import AuthToken

    now = datetime.now(timezone.utc)
    db.query(AuthToken).filter(
        AuthToken.expires_at.isnot(None),
        AuthToken.expires_at < now,
    ).delete(synchronize_session=False)
    db.commit()
