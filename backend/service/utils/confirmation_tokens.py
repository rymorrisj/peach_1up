"""Confirmation token machinery for destructive-action guards.

Tokens are in-memory, TTL-based, single-use, and thread-safe.
Each token encodes a (resource, resource_id, action) triple so a token
issued for one resource cannot be consumed against a different one.
"""

import secrets
import threading
import time

TOKEN_TTL = 60

_tokens: dict[str, tuple[str, int | str, str | None, float]] = {}
_lock = threading.Lock()


def issue(resource: str, resource_id: int | str, action: str | None = None) -> str:
    """Issue a single-use confirmation token for a destructive action.

    Args:
        resource:    Logical resource type (e.g. "library", "platform", "drive").
        resource_id: Primary key or slug of the target resource.
        action:      Optional action discriminator (e.g. "delete", "restore").

    Returns:
        An opaque URL-safe token string.
    """
    token = secrets.token_urlsafe(32)
    expires = time.monotonic() + TOKEN_TTL
    with _lock:
        _expire_stale()
        _tokens[token] = (resource, resource_id, action, expires)
    return token


def consume(token: str, resource: str, resource_id: int | str, action: str | None = None) -> bool:
    """Consume a confirmation token, returning True if valid and matching.

    The token is removed from the store regardless of whether it matched,
    so it cannot be replayed. Expired tokens are purged on each call.

    Args:
        token:       The token string returned by :func:`issue`.
        resource:    Must match the resource passed to :func:`issue`.
        resource_id: Must match the resource_id passed to :func:`issue`.
        action:      Must match the action passed to :func:`issue`.

    Returns:
        True if the token existed, had not expired, and matched all fields.
    """
    now = time.monotonic()
    with _lock:
        _expire_stale()
        entry = _tokens.pop(token, None)
        if entry is None:
            return False
        res, rid, act, expires_at = entry
        if now > expires_at:
            return False
        return res == resource and rid == resource_id and act == action


def _expire_stale() -> None:
    now = time.monotonic()
    stale = [k for k, (_, _, _, exp) in _tokens.items() if exp < now]
    for k in stale:
        del _tokens[k]
