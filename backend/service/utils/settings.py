"""Settings management for Peach 1UP.

Single source for binary path resolution and persisted settings state,
backed by the app_settings DB table (SQLite). Call init() once at startup
(via main.py, before the FastAPI app is built) before any other access to
this module.

This module talks to app_settings through backend.core.database's shared
SQLAlchemy engine. main.py calls init_settings() at import time, before
backend.core.database's lifespan-scoped create_tables() has run across the
full model metadata — get_engine() lazily creates the engine on first use
(rather than requiring init_db() to run first) and ensure_settings_table()
creates just the app_settings table, scoped narrowly enough to be safe to
call before the rest of backend.models.* has registered with SQLModel's
metadata. The later, full create_tables() call in the lifespan handler
no-ops on a table that already exists.

The legacy settings.yaml / %APPDATA%\\Peach1UP\\paths.yaml files (and their
one-time migration into app_settings/.env) have been fully retired — this
module is now DB-only, with secrets in .env (see env_secrets.py).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from backend.core.database import ensure_settings_table, get_engine
from backend.models.settings import Settings


def _get_project_root() -> Path:
    from backend.core.settings import get_base_path
    return get_base_path()


_PROJECT_ROOT: Path = _get_project_root()

from backend.service.utils.upload_utils import DEFAULT_UPLOAD_TMP_TTL_SECONDS  # noqa: E402

_DEFAULTS: dict = {
    "LIBRARY_PATH": "",
    "SOFTWARE_PATH": "",
    "MEDIA_PATH": "",
    "OS_PATH": "",
    "ROMS_PATH": "",
    "PROFILES_PATH": "",
    "suppress_confirmations": [],
    "reset_db": False,
    "delete_media_on_removal": False,
    "delete_original_on_upload": False,
    "UPLOAD_TMP_TTL_SECONDS": DEFAULT_UPLOAD_TMP_TTL_SECONDS,
    "metadata_provider": "thegamesdb",
}

# Path keys whose values are resolved to absolute paths at load time.
_PATH_KEYS: frozenset[str] = frozenset({
    "LIBRARY_PATH",
    "SOFTWARE_PATH",
    "MEDIA_PATH",
    "OS_PATH",
    "ROMS_PATH",
    "PROFILES_PATH",
})

_PATH_DEFAULTS: dict[str, str] = {
    "LIBRARY_PATH":       str((_PROJECT_ROOT / "library").resolve()),
    # v2: library/software is the launchable-Software root (pre-v2 this was
    # library/media). library/media is now the archival Media/Archive domain's
    # root — see backend/models/media.py and api/routes/media.py.
    "SOFTWARE_PATH":      str((_PROJECT_ROOT / "library" / "software").resolve()),
    "MEDIA_PATH":         str((_PROJECT_ROOT / "library" / "media").resolve()),
    "OS_PATH":            str((_PROJECT_ROOT / "library" / "system" / "os").resolve()),
    "ROMS_PATH":          str((_PROJECT_ROOT / "library" / "system" / "roms" / "86box").resolve()),
    "PROFILES_PATH":      str((_PROJECT_ROOT / "library" / "system" / "profiles").resolve()),
}

# None until init() is called; dict thereafter
_state: Optional[dict] = None


def _load_all_rows() -> dict:
    with Session(get_engine()) as session:
        rows = session.query(Settings.key, Settings.value).all()
    result: dict = {}
    for key, value in rows:
        if value is None:
            continue
        try:
            result[key] = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            result[key] = value
    return result


def _persist(key: str, value) -> None:
    serialized = json.dumps(value)
    with Session(get_engine()) as session:
        row = session.get(Settings, key)
        if row is None:
            session.add(Settings(key=key, value=serialized))
        else:
            row.value = serialized
        session.commit()


def init() -> None:
    """Load .env and app_settings into module-level state.

    Must be called exactly once before any other function in this module.

    Raises:
        RuntimeError: If called a second time.
    """
    global _state

    if _state is not None:
        raise RuntimeError(
            "settings.init() has already been called. "
            "It may only be called once per process."
        )

    load_dotenv(_PROJECT_ROOT / ".env")

    ensure_settings_table()

    state: dict = dict(_DEFAULTS)
    state.update(_load_all_rows())
    state.pop("first_run_complete", None)

    # Resolve relative path values against project root so all downstream
    # consumers always receive absolute paths regardless of how the value
    # originally reached app_settings.
    for _pkey in _PATH_KEYS:
        _pval = state.get(_pkey)
        if _pval and isinstance(_pval, str):
            _pp = Path(_pval)
            if not _pp.is_absolute():
                state[_pkey] = str((_PROJECT_ROOT / _pp).resolve())

    for _key, _default in _PATH_DEFAULTS.items():
        if not state.get(_key):
            state[_key] = _default

    # Snapshot .env values after load_dotenv() so path resolution never calls
    # os.getenv() at call time. app_settings values are already in state;
    # these .env values take precedence when non-empty.
    _env: dict[str, str] = {}
    for _pkey in _PATH_KEYS:
        _env[_pkey] = os.getenv(_pkey, "")
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
    stored_val = state.get(key, "") or ""
    if stored_val:
        return str(stored_val)
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


def set_flag(key: str, value) -> None:
    """Persist a value to app_settings.

    Args:
        key: Settings key to set (e.g. ``'suppress_confirmations'``).
        value: Value to store (JSON-serialisable).

    Raises:
        RuntimeError: If init() has not been called.
    """
    state = _require_init()
    state[key] = value
    _persist(key, value)


def add_suppression(suppression_id: str) -> None:
    """Add a confirmation suppression ID and persist to app_settings.

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
    _persist("suppress_confirmations", suppressions)


def is_suppressed(suppression_id: str) -> bool:
    """Return True if the given confirmation ID has been suppressed.

    Raises:
        RuntimeError: If init() has not been called.
    """
    return suppression_id in _require_init().get("suppress_confirmations", [])


def set_path(key: str, value: str) -> None:
    """Write a path value to app_settings and update state.

    Covers all keys in ``_PATH_KEYS``: ``LIBRARY_PATH``, ``SOFTWARE_PATH``,
    ``MEDIA_PATH``, ``OS_PATH``, ``ROMS_PATH``, ``PROFILES_PATH``.

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
    _persist(key, value)


def reset_db_completed() -> None:
    """Clear the reset_db flag and rewrite every in-memory setting to disk.

    Called by the lifespan handler immediately after deleting peach1up.db
    for a reset_db cycle. Settings live in the same SQLite file as library
    data, so deleting it also empties app_settings — without this, a
    reset_db wipe would silently drop every configured setting. Re-persisting
    the state that was already loaded before the delete restores it.

    Raises:
        RuntimeError: If init() has not been called.
    """
    state = _require_init()
    state["reset_db"] = False
    for key, value in state.items():
        if key.startswith("_"):
            continue
        _persist(key, value)


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


def validate_configured_paths() -> None:
    """Check that all configured path keys exist on disk and log warnings.

    Call this from the lifespan handler *after* ``_ensure_default_paths()``
    has created the default directories, so default paths do not produce
    false-positive warnings.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)
    state = _require_init()
    warnings: list[str] = []
    for key in sorted(_PATH_KEYS):
        val = state.get(key, "") or ""
        if not val:
            msg = f"{key} is not configured"
            warnings.append(msg)
            _log.warning("Path configuration: %s", msg)
        elif not Path(val).exists():
            msg = f"{key} points to a non-existent location: {val}"
            warnings.append(msg)
            _log.warning("Path configuration: %s", msg)
    state["_path_warnings"] = warnings


def get_path_warnings() -> list[str]:
    """Return path validation warnings collected by ``validate_configured_paths()``.

    Returns an empty list if ``validate_configured_paths()`` has not been called
    or if all paths are valid.
    """
    if _state is None:
        return []
    return list(_state.get("_path_warnings", []))
