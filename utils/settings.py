"""Settings management for Peach 1UP.

Single source for binary path resolution and persisted settings state.
Call init() once at startup — from launcher.py on_mount — before any
other access to this module.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv


_SETTINGS_PATH = Path("config") / "settings.yaml"

_DEFAULTS: dict = {
    "first_run_complete": False,
    "dosbox_path_override": "",
    "virtualbox_path_override": "",
    "box86_path_override": "",
}

# Maps emulator key → (env_var_name, settings_override_key)
_ENV_BINARY_VARS: dict[str, tuple[str, str]] = {
    "dosbox":      ("DOSBOX_PATH",      "dosbox_path_override"),
    "virtualbox":  ("VIRTUALBOX_PATH",  "virtualbox_path_override"),
    "box86":       ("BOX86_PATH",       "box86_path_override"),
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

    load_dotenv()

    state: dict = dict(_DEFAULTS)

    if _SETTINGS_PATH.exists():
        with _SETTINGS_PATH.open("r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
        if isinstance(loaded, dict):
            state.update(loaded)

    # Snapshot binary env vars after load_dotenv() so get_binary_path()
    # never needs to call os.getenv() at call time.
    _env: dict[str, str] = {}
    for _emulator, (env_var, _override) in _ENV_BINARY_VARS.items():
        _env[env_var] = os.getenv(env_var, "")
    state["_env"] = _env

    _state = state


def _require_init() -> dict:
    """Return _state or raise a clear error if init() was not called."""
    if _state is None:
        raise RuntimeError(
            "settings.init() has not been called. "
            "Call settings.init() at the start of launcher.py on_mount "
            "before any binary path resolution or settings access."
        )
    return _state


def get_binary_path(emulator: str) -> str:
    """Return the resolved binary path for an emulator.

    Checks the settings.yaml override first; falls back to the env var
    value captured at init() time. Never calls os.getenv() at call time.

    Args:
        emulator: One of ``'dosbox'``, ``'virtualbox'``, ``'box86'``.

    Returns:
        Resolved path string, or empty string if neither override nor
        env var was set at init() time.

    Raises:
        RuntimeError: If init() has not been called.
        ValueError: If emulator is not a recognised key.
    """
    state = _require_init()

    if emulator not in _ENV_BINARY_VARS:
        raise ValueError(
            f"Unknown emulator '{emulator}'. "
            f"Valid values: {', '.join(sorted(_ENV_BINARY_VARS))}"
        )

    env_var, override_key = _ENV_BINARY_VARS[emulator]
    override = state.get(override_key, "") or ""
    if override:
        return override
    return state["_env"].get(env_var, "")


def get(key: str, default=None):
    """Return a settings value from the module-level state.

    Raises:
        RuntimeError: If init() has not been called.
    """
    return _require_init().get(key, default)


def is_first_run() -> bool:
    """Return True if first_run_complete is False or absent in settings.yaml."""
    return not get("first_run_complete", False)


def mark_first_run_complete() -> None:
    """Set first_run_complete to True in state and persist to settings.yaml."""
    state = _require_init()
    state["first_run_complete"] = True
    _save()


def set_override_path(emulator: str, path: str) -> None:
    """Write a binary override path to settings.yaml and update state.

    Args:
        emulator: One of ``'dosbox'``, ``'virtualbox'``, ``'box86'``.
        path: Absolute path to the emulator executable.

    Raises:
        RuntimeError: If init() has not been called.
        ValueError: If emulator is not recognised.
    """
    state = _require_init()

    if emulator not in _ENV_BINARY_VARS:
        raise ValueError(
            f"Unknown emulator '{emulator}'. "
            f"Valid values: {', '.join(sorted(_ENV_BINARY_VARS))}"
        )

    _, override_key = _ENV_BINARY_VARS[emulator]
    state[override_key] = path
    _save()


def _save() -> None:
    """Persist the current settings state to settings.yaml atomically.

    Internal keys prefixed with ``_`` (e.g. ``_env``) are excluded from
    the file. Writes to a temp file then renames into place so a mid-write
    interruption cannot corrupt the settings file.
    """
    state = _require_init()
    payload = {k: v for k, v in state.items() if not k.startswith("_")}

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
