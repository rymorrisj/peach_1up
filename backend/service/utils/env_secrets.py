"""Read/write helpers for secrets stored in the project's .env file.

PIN_PEPPER, THEGAMESDB_API_KEY, AI_API_KEY, IGDB_CLIENT_ID, and IGDB_CLIENT_SECRET
are deliberately kept out of settings (unlike every other former settings.yaml key, which
now lives in the DB — see backend/service/utils/settings.py). A secret must
not round-trip through the same SQLite file that the reset_db dev flag can
delete, and .env is already gitignored and documented as the secrets home
(.env.template).

get_env_secret() loads .env itself (once per process) rather than relying on
settings.init() to have run first — pin_hashing.get_pin_pepper() and
thegamesdb_client's key lookup must not silently see an empty pepper/key
just because they ran before or independently of the settings subsystem
(e.g. scripts/manage_test_users.py, which hashes PINs without ever calling
init_settings()). Silently treating an unloaded secret as "disabled" would
violate this project's fail-loudly rule by masking real configuration.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

_ENV_KEYS = frozenset({
    "PIN_PEPPER", "THEGAMESDB_API_KEY", "AI_API_KEY", "IGDB_CLIENT_ID", "IGDB_CLIENT_SECRET",
})

_dotenv_loaded = False


def _env_path() -> Path:
    from backend.core.settings import get_base_path
    return get_base_path() / ".env"


def _ensure_loaded() -> None:
    global _dotenv_loaded
    if not _dotenv_loaded:
        load_dotenv(_env_path())
        _dotenv_loaded = True


def _check_key(key: str) -> None:
    if key not in _ENV_KEYS:
        raise ValueError(f"'{key}' is not a recognised .env secret key.")


def get_env_secret(key: str) -> str:
    """Return the current value of *key* from .env / the process environment."""
    _check_key(key)
    _ensure_loaded()
    return os.getenv(key, "") or ""


def set_env_secret(key: str, value: str) -> None:
    """Persist *value* for *key* into .env and the current process environment.

    Rewrites .env line-by-line, preserving every other line (comments, blank
    lines, unrelated vars) and replacing or appending only the target key's
    line. Atomic via temp file + rename, mirroring the write pattern
    settings.yaml used before secrets moved here.
    """
    _check_key(key)
    _ensure_loaded()

    path = _env_path()
    lines: list[str] = []
    found = False
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            for raw_line in fh:
                stripped = raw_line.rstrip("\n")
                if stripped.startswith(f"{key}="):
                    lines.append(f"{key}={value}")
                    found = True
                else:
                    lines.append(stripped)
    if not found:
        lines.append(f"{key}={value}")

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".env.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    os.environ[key] = value
