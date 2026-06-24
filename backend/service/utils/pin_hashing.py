"""Shared Argon2id PIN hashing.

Single implementation collapsing what were three separate copies of this
logic (routes/auth.py's PasswordHasher() usage, routes/users.py::_hash_pin,
scripts/setup_admin_user.py::_hash_pin) — all used the same Argon2id
parameters, just expressed three different ways.

Pepper application point: the configured pepper (PIN_PEPPER in
settings.yaml, opt-in — empty/unset means disabled) is appended directly
to the PIN before hashing: secret = pin + pepper. This is deliberate —
because the pepper changes the hashed secret itself rather than being
tracked as separate metadata, toggling it on, off, or to a new value
automatically makes every existing hash fail to verify. No separate
"pepper version" marker is needed to detect staleness; the hash IS the
marker.
"""

import os

from argon2.exceptions import VerificationError, VerifyMismatchError
from argon2.low_level import Type, hash_secret, verify_secret

from backend.core.logger import get_logger

logger = get_logger(__name__)

_TIME_COST = 3
_MEMORY_COST = 65536
_PARALLELISM = 4
_HASH_LEN = 32


def get_pin_pepper() -> str:
    """Return the configured PIN pepper, or "" if unset (opt-in, disabled by default)."""
    from backend.core.settings import get_settings
    return get_settings().get("PIN_PEPPER", "") or ""


def hash_pin(pin: str, *, pepper: str | None = None) -> str:
    """Hash a PIN with Argon2id, applying the configured pepper if set.

    Args:
        pin: Plaintext PIN.
        pepper: Override the configured pepper (used when re-hashing under
            a new pepper value during a pepper change). Defaults to the
            currently configured pepper.
    """
    if pepper is None:
        pepper = get_pin_pepper()
    salt = os.urandom(16)
    return hash_secret(
        secret=(pin + pepper).encode(),
        salt=salt,
        time_cost=_TIME_COST,
        memory_cost=_MEMORY_COST,
        parallelism=_PARALLELISM,
        hash_len=_HASH_LEN,
        type=Type.ID,
    ).decode()


def verify_pin(pin: str, pin_hash: str, *, pepper: str | None = None) -> bool:
    """Verify a PIN against a stored hash, applying the configured pepper if set."""
    if pepper is None:
        pepper = get_pin_pepper()
    try:
        return verify_secret(pin_hash.encode(), (pin + pepper).encode(), Type.ID)
    except VerifyMismatchError:
        return False
    except VerificationError as exc:
        logger.warning("PIN verification error: %s", exc)
        return False
