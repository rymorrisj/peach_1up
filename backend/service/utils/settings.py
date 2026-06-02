"""Settings management for Peach 1UP.

Single source for binary path resolution and persisted settings state.
Call init() once at startup (via the FastAPI lifespan handler) before
any other access to this module.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv


def _get_project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent.parent


_SETTINGS_PATH = _get_project_root() / "config" / "settings.yaml"

_DEFAULTS: dict = {
    "first_run_complete": False,
    "LIBRARY_PATH": "",
    "MEDIA_PATH": "",
    "OS_PATH": "",
    "ROMS_PATH": "",
    "PROFILES_PATH": "",
    "suppress_confirmations": [],
}

# Path keys whose values are normalised to forward slashes on save.
_PATH_KEYS: frozenset[str] = frozenset({
    "LIBRARY_PATH",
    "MEDIA_PATH",
    "OS_PATH",
    "ROMS_PATH",
    "PROFILES_PATH",
})

_PROJECT_ROOT: Path = _get_project_root()

_PATH_DEFAULTS: dict[str, str] = {
    "LIBRARY_PATH":       str((_PROJECT_ROOT / "library").resolve()),
    "MEDIA_PATH":         str((_PROJECT_ROOT / "library" / "media").resolve()),
    "OS_PATH":            str((_PROJECT_ROOT / "library" / "system" / "os").resolve()),
    "ROMS_PATH":          str((_PROJECT_ROOT / "library" / "system" / "roms" / "86box").resolve()),
    "PROFILES_PATH":      str((_PROJECT_ROOT / "library" / "system" / "profiles").resolve()),
}

# None until init() is called; dict thereafter
_state: Optional[dict] = None


def init() -> None:
    """Load .env and settings.yaml into module-level state.

    Must be called exactly once before any other function in this module.
    Populates os.environ from .env via load_dotenv, snapshots binary env
    vars into state, and merges any settings.yaml overrides on top.

    Raises:
        RuntimeError: If called a second time.
        yaml.YAMLError: If settings.yaml exists but is not valid YAML.
    """
    global _state

    if _state is not None:
        raise RuntimeError(
            "settings.init() has already been called. "
            "It may only be called once per process."
        )

    load_dotenv(_PROJECT_ROOT / ".env")

    state: dict = dict(_DEFAULTS)

    if _SETTINGS_PATH.exists():
        with _SETTINGS_PATH.open("r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
        if isinstance(loaded, dict):
            state.update(loaded)

    # Resolve relative path values against project root so all downstream
    # consumers always receive absolute paths regardless of how settings.yaml
    # was written. Empty strings pass through unchanged (falsy check below).
    _project_root = _get_project_root()
    for _pkey in _PATH_KEYS:
        _pval = state.get(_pkey)
        if _pval and isinstance(_pval, str):
            _pp = Path(_pval)
            if not _pp.is_absolute():
                state[_pkey] = str((_project_root / _pp).resolve())

    for _key, _default in _PATH_DEFAULTS.items():
        if not state.get(_key):
            state[_key] = _default

    # Snapshot .env values after load_dotenv() so path resolution never calls
    # os.getenv() at call time. settings.yaml values are already in state;
    # these .env values take precedence when non-empty.
    _env: dict[str, str] = {}
    _env["LIBRARY_PATH"] = os.getenv("LIBRARY_PATH", "")
    _env["MEDIA_PATH"] = os.getenv("MEDIA_PATH", "")
    _env["OS_PATH"] = os.getenv("OS_PATH", "")
    _env["ROMS_PATH"] = os.getenv("ROMS_PATH", "")
    _env["PROFILES_PATH"] = os.getenv("PROFILES_PATH", "")
    state["_env"] = _env

    _state = state


def get_env_var(key: str) -> str:
    """Return an env var value from the snapshot captured at init() time.

    Args:
        key: The environment variable name (e.g. ``'ROMS_PATH'``).

    Returns:
        The value captured at init() time, or an empty string if unset.

    Raises:
        RuntimeError: If init() has not been called.
        KeyError: If ``key`` was not included in the snapshot.
    """
    state = _require_init()
    env = state["_env"]
    if key not in env:
        raise KeyError(
            f"'{key}' was not captured in the settings snapshot. "
            "Only env vars snapshotted during init() are accessible via get_env_var()."
        )
    env_val = env[key]
    if env_val:
        return env_val
    yaml_val = state.get(key, "") or ""
    if yaml_val:
        return str(yaml_val)
    return _PATH_DEFAULTS.get(key, "")


def _require_init() -> dict:
    """Return _state or raise a clear error if init() was not called."""
    if _state is None:
        raise RuntimeError(
            "settings.init() has not been called. "
            "Call settings.init() at the start of launcher.py on_mount "
            "before any binary path resolution or settings access."
        )
    return _state



def get(key: str, default=None):
    """Return a settings value from the module-level state.

    Raises:
        RuntimeError: If init() has not been called.
    """
    return _require_init().get(key, default)


def is_first_run() -> bool:
    """Return True if neither settings.yaml nor the DB records first_run_complete."""
    if get("first_run_complete", False):
        return False
    try:
        from backend.core.database import get_engine
        from sqlalchemy import text
        with get_engine().connect() as conn:
            row = conn.execute(
                text("SELECT value FROM settings WHERE key='first_run_complete'")
            ).fetchone()
            owner = conn.execute(
                text("SELECT id FROM user WHERE is_owner=1")
            ).fetchone()
            if row and row[0] == "true" and owner:
                _require_init()["first_run_complete"] = True
                return False
    except Exception:
        pass
    return True


def _write_env_key(key: str, value: str) -> None:
    """Write or update a single key in the project .env file and os.environ."""
    from dotenv import set_key as _set_key
    _set_key(str(_PROJECT_ROOT / ".env"), key, value, quote_mode="never")
    os.environ[key] = value


def get_or_generate_session_secret() -> str:
    """Return the session signing secret, generating and persisting it on first call.

    Reads from .env (loaded at init() time). If SESSION_SECRET was previously
    persisted to settings.yaml, migrates it to .env and removes it from
    settings.yaml. Generates a new secret and writes it to .env if absent.

    Per SECURITY.md the secret is never exposed via API responses or logs.
    """
    state = _require_init()
    secret: str = os.getenv("SESSION_SECRET", "") or ""

    if not secret:
        yaml_secret: str = state.get("SESSION_SECRET", "") or ""
        if yaml_secret:
            secret = yaml_secret
            _write_env_key("SESSION_SECRET", secret)
            state.pop("SESSION_SECRET", None)
            _save()

    if not secret:
        import secrets as _sec
        secret = _sec.token_hex(32)
        _write_env_key("SESSION_SECRET", secret)

    return secret


def mark_first_run_complete() -> None:
    """Set first_run_complete to True in state and persist to settings.yaml."""
    state = _require_init()
    state["first_run_complete"] = True
    _save()


def set_flag(key: str, value: bool) -> None:
    """Persist a boolean flag to settings.yaml.

    Args:
        key: Settings key to set (e.g. ``'suppress_confirmations'``).
        value: Boolean value to store.

    Raises:
        RuntimeError: If init() has not been called.
    """
    state = _require_init()
    state[key] = value
    _save()


def add_suppression(suppression_id: str) -> None:
    """Add a confirmation suppression ID and persist to settings.yaml.

    Idempotent — adding an ID that already exists is a no-op.

    Args:
        suppression_id: Identifier for the confirmation to suppress
            (e.g. ``'library_scan_import'``).

    Raises:
        RuntimeError: If init() has not been called.
    """
    state = _require_init()
    suppressions: list = list(state.get("suppress_confirmations", []))
    if suppression_id not in suppressions:
        suppressions.append(suppression_id)
    state["suppress_confirmations"] = suppressions
    _save()


def is_suppressed(suppression_id: str) -> bool:
    """Return True if the given confirmation ID has been suppressed.

    Raises:
        RuntimeError: If init() has not been called.
    """
    return suppression_id in _require_init().get("suppress_confirmations", [])


def set_path(key: str, value: str) -> None:
    """Write a path value to settings.yaml and update state.

    Covers all keys in ``_PATH_KEYS``: ``LIBRARY_PATH``, ``MEDIA_PATH``,
    ``OS_PATH``, ``ROMS_PATH``, ``PROFILES_PATH``.

    Args:
        key: The settings key to update. Must be one of the path keys.
        value: New path value.

    Raises:
        RuntimeError: If init() has not been called.
        ValueError: If key is not a recognised path key.
    """
    state = _require_init()
    if key not in _PATH_KEYS:
        raise ValueError(
            f"'{key}' is not a recognised path key. "
            f"Valid path keys: {', '.join(sorted(_PATH_KEYS))}"
        )
    if value:
        from backend.service.utils.path_utils import normalise_path
        try:
            value = str(normalise_path(value))
        except ValueError as exc:
            raise ValueError(f"Invalid path for {key}: {exc}") from exc
    state[key] = value
    _save()


def compute_setup_status() -> list[dict]:
    """Return availability status for every emulator in the catalog."""
    from backend.service.utils.emulator_catalog import load_catalog, get_install_path
    result = []
    for entry in load_catalog():
        if entry.get("install_type") == "rom_pack":
            continue
        slug = entry["slug"]
        name = entry.get("display_name", slug)
        required = entry.get("required", False)
        try:
            path = get_install_path(slug)
            available = path is not None and path.is_file()
            path_str = str(path) if path else None
        except Exception:
            available = False
            path_str = None
        result.append({
            "slug": slug,
            "name": name,
            "required": required,
            "available": available,
            "path": path_str,
        })
    return result


def _save() -> None:
    """Persist the current settings state to settings.yaml atomically.

    Internal keys prefixed with ``_`` (e.g. ``_env``) are excluded from
    the file. Writes to a temp file then renames into place so a mid-write
    interruption cannot corrupt the settings file.
    """
    state = _require_init()
    payload = {k: v for k, v in state.items() if not k.startswith("_")}

    for key in _PATH_KEYS:
        if key in payload and payload[key]:
            payload[key] = Path(payload[key]).as_posix()

    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(_SETTINGS_PATH.parent), suffix=".yaml.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(payload, fh, allow_unicode=True, sort_keys=False)
        os.replace(tmp, str(_SETTINGS_PATH))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
