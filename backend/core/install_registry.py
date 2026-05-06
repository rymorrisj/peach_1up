import threading
import time
import uuid
from typing import Literal

InstallStatus = Literal["idle", "downloading", "complete", "error"]

_registry: dict[str, dict] = {}
_lock = threading.Lock()

_confirm_tokens: dict[str, tuple[str, float]] = {}
_tokens_lock = threading.Lock()
_TOKEN_TTL = 60.0


def set_status(
    slug: str,
    status: InstallStatus,
    error: str | None = None,
    install_path: str | None = None,
) -> None:
    with _lock:
        _registry[slug] = {
            "slug": slug,
            "status": status,
            "error": error,
            "install_path": install_path,
        }


def get_status(slug: str) -> dict:
    with _lock:
        return dict(
            _registry.get(
                slug,
                {"slug": slug, "status": "idle", "error": None, "install_path": None},
            )
        )


def get_all() -> dict[str, dict]:
    with _lock:
        return {k: dict(v) for k, v in _registry.items()}


def generate_confirm_token(slug: str) -> str:
    token = str(uuid.uuid4())
    with _tokens_lock:
        _confirm_tokens[slug] = (token, time.monotonic() + _TOKEN_TTL)
    return token


def consume_confirm_token(slug: str, token: str) -> bool:
    with _tokens_lock:
        entry = _confirm_tokens.get(slug)
        if entry is None:
            return False
        stored_token, expires_at = entry
        if time.monotonic() > expires_at:
            del _confirm_tokens[slug]
            return False
        if stored_token != token:
            return False
        del _confirm_tokens[slug]
        return True
