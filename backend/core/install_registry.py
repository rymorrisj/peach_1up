import threading
from typing import Literal

from backend.service.utils import confirmation_tokens

InstallStatus = Literal["idle", "complete", "error", "installer_launched", "cloning", "downloading"]

_registry: dict[str, dict] = {}
_lock = threading.Lock()


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
    return confirmation_tokens.issue("emulator", slug)


def consume_confirm_token(slug: str, token: str) -> bool:
    return confirmation_tokens.consume(token, "emulator", slug)
