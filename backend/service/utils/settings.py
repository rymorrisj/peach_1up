"""Settings management for Peach 1UP.

Single source for binary path resolution and persisted settings state.
Call init() once at startup (via the FastAPI lifespan handler) before
any other access to this module.
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
    "DOSBOX_PATH": "",
    "BOX86_PATH": "",
    "VIRTUALBOX_PATH": "",
    "ROM_PATH": "",
    "IMAGES_PATH": "",
    "PROFILES_PATH": "",
    "DUCKSTATION_PATH": "",
    "PCSX2_PATH": "",
    "XEMU_PATH": "",
    "MESEN_PATH": "",
    "PROJECT64_PATH": "",
    "PS1_BIOS_PATH": "",
    "PS2_BIOS_PATH": "",
    "XBOX_BIOS_PATH": "",
    "suppress_confirmations": [],
    "SANDBOX_PASSWORD": "",
}

# Maps emulator key → (env_var_name, settings_yaml_key)
_ENV_BINARY_VARS: dict[str, tuple[str, str]] = {
    "dosbox":       ("DOSBOX_PATH",       "DOSBOX_PATH"),
    "virtualbox":   ("VIRTUALBOX_PATH",   "VIRTUALBOX_PATH"),
    "box86":        ("BOX86_PATH",        "BOX86_PATH"),
    "duckstation":  ("DUCKSTATION_PATH",  "DUCKSTATION_PATH"),
    "pcsx2":        ("PCSX2_PATH",        "PCSX2_PATH"),
    "xemu":         ("XEMU_PATH",         "XEMU_PATH"),
    "mesen":        ("MESEN_PATH",        "MESEN_PATH"),
    "project64":    ("PROJECT64_PATH",    "PROJECT64_PATH"),
}

# Path keys whose values are normalised to forward slashes on save.
_PATH_KEYS: frozenset[str] = frozenset({
    "DOSBOX_PATH",
    "BOX86_PATH",
    "VIRTUALBOX_PATH",
    "ROM_PATH",
    "IMAGES_PATH",
    "PROFILES_PATH",
    "DUCKSTATION_PATH",
    "PCSX2_PATH",
    "XEMU_PATH",
    "MESEN_PATH",
    "PROJECT64_PATH",
    "PS1_BIOS_PATH",
    "PS2_BIOS_PATH",
    "XBOX_BIOS_PATH",
})

# Ordered emulator catalog used by compute_setup_status().
_EMULATOR_CATALOG: list[tuple[str, str, bool, str]] = [
    ("dosbox-x",    "DOSBox-X",   True,  "DOSBOX_PATH"),
    ("86box",       "86Box",      False, "BOX86_PATH"),
    ("virtualbox",  "VirtualBox", False, "VIRTUALBOX_PATH"),
    ("duckstation", "DuckStation",False, "DUCKSTATION_PATH"),
    ("pcsx2",       "PCSX2",      False, "PCSX2_PATH"),
    ("xemu",        "xemu",       False, "XEMU_PATH"),
    ("mesen",       "Mesen",      False, "MESEN_PATH"),
    ("project64",   "Project64",  False, "PROJECT64_PATH"),
]

# Bundled emulator executables checked as a last-resort fallback in get_binary_path().
# Checked after the settings.yaml override and the .env var, so users can always
# override by setting either of those.
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent.parent

_BUNDLED: dict[str, Path] = {
    "dosbox":      _PROJECT_ROOT / "emulators" / "dosbox-x" / "dosbox-x.exe",
    "box86":       _PROJECT_ROOT / "emulators" / "86box" / "86Box.exe",
    "virtualbox":  _PROJECT_ROOT / "emulators" / "virtualbox" / "VBoxManage.exe",
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

    # Snapshot .env values after load_dotenv() so path resolution never calls
    # os.getenv() at call time. settings.yaml values are already in state;
    # these .env values take precedence when non-empty.
    _env: dict[str, str] = {}
    for _emulator, (env_var, _yaml_key) in _ENV_BINARY_VARS.items():
        _env[env_var] = os.getenv(env_var, "")
    _env["ROM_PATH"] = os.getenv("ROM_PATH", "")
    _env["PROFILES_PATH"] = os.getenv("PROFILES_PATH", "")
    _env["IMAGES_PATH"] = os.getenv("IMAGES_PATH", "")
    _env["PS1_BIOS_PATH"] = os.getenv("PS1_BIOS_PATH", "")
    _env["PS2_BIOS_PATH"] = os.getenv("PS2_BIOS_PATH", "")
    _env["XBOX_BIOS_PATH"] = os.getenv("XBOX_BIOS_PATH", "")
    state["_env"] = _env

    _state = state


def get_env_var(key: str) -> str:
    """Return an env var value from the snapshot captured at init() time.

    Args:
        key: The environment variable name (e.g. ``'ROM_PATH'``).

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
    if key == "PROFILES_PATH":
        return "profiles"
    if key == "IMAGES_PATH":
        return str((_PROJECT_ROOT / "images" / "games").resolve())
    return ""


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

    env_var, yaml_key = _ENV_BINARY_VARS[emulator]
    env_val = state["_env"].get(env_var, "") or ""
    if env_val:
        return env_val
    yaml_val = state.get(yaml_key, "") or ""
    if yaml_val:
        return yaml_val
    bundled = _BUNDLED.get(emulator)
    if bundled and bundled.is_file():
        return str(bundled)
    return ""


def get(key: str, default=None):
    """Return a settings value from the module-level state.

    Raises:
        RuntimeError: If init() has not been called.
    """
    return _require_init().get(key, default)


def is_first_run() -> bool:
    """Return True if first_run_complete is False or absent in settings.yaml."""
    return not get("first_run_complete", False)


def get_or_generate_session_secret() -> str:
    """Return the session signing secret, generating and persisting it on first call.

    Per SECURITY.md the secret is never exposed via API responses or logs.
    """
    state = _require_init()
    secret: str = state.get("SESSION_SECRET") or ""
    if not secret:
        import secrets as _sec
        secret = _sec.token_hex(32)
        state["SESSION_SECRET"] = secret
        _save()
    return secret


def get_or_generate_sandbox_password() -> str:
    """Return the peach_sandbox account password, generating and persisting it on first call.

    Follows the same pattern as get_or_generate_session_secret(). The password
    is a 32-character alphanumeric string. Per SECURITY.md it is never exposed
    via API responses or logs.
    """
    state = _require_init()
    password: str = state.get("SANDBOX_PASSWORD") or ""
    if not password:
        import secrets as _sec
        import string as _str
        alphabet = _str.ascii_letters + _str.digits
        password = "".join(_sec.choice(alphabet) for _ in range(32))
        state["SANDBOX_PASSWORD"] = password
        _save()
    return password


def mark_first_run_complete() -> None:
    """Set first_run_complete to True in state and persist to settings.yaml."""
    state = _require_init()
    state["first_run_complete"] = True
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

    _, yaml_key = _ENV_BINARY_VARS[emulator]
    state[yaml_key] = path
    _save()


def set_path(key: str, value: str) -> None:
    """Write a path value to settings.yaml and update state.

    Covers all keys in ``_PATH_KEYS``: ``DOSBOX_PATH``, ``BOX86_PATH``,
    ``VIRTUALBOX_PATH``, ``ROM_PATH``, ``IMAGES_PATH``, ``PROFILES_PATH``.
    For emulator binary paths, ``set_override_path()`` accepts a short
    emulator key (``'dosbox'``) as an alternative.

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
    state[key] = value
    _save()


def compute_setup_status() -> list[dict]:
    """Return availability status for every emulator in the catalog."""
    state = _require_init()
    result = []
    for slug, name, required, key in _EMULATOR_CATALOG:
        env_val = state["_env"].get(key, "") or ""
        yaml_val = state.get(key, "") or ""
        path = env_val or yaml_val or ""
        available = bool(path and Path(path).is_file())
        result.append({
            "slug": slug,
            "name": name,
            "required": required,
            "available": available,
            "path": path or None,
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
