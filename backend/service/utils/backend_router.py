"""Backend routing utilities for Peach 1UP.

Maps eras to their corresponding backend launch functions, accounting for
the multi-tier routing introduced in P2 (primary / compat / accuracy) and
the console backends added in P4.
"""

import os
import yaml
from pathlib import Path
from typing import Callable, Dict, Any, Optional

from backend.constants_generated import BackendSlug, Era
from backend.service.utils.settings import get_binary_path


def _load_eras_config() -> Dict[str, Any]:
    """Load and parse ``config/eras.yaml``.

    Returns:
        Dictionary mapping era keys to their configuration values.

    Raises:
        FileNotFoundError: If ``eras.yaml`` cannot be found.
        yaml.YAMLError: If the file exists but is not valid YAML.
    """
    # Anchor to the project root — this file is at backend/service/utils/,
    # so 4 parents up is the project root.
    config_path = Path(__file__).resolve().parent.parent.parent.parent / "config" / "eras.yaml"
    with config_path.open('r') as f:
        return yaml.safe_load(f)


def resolve_backend_name(era: Era, accuracy_mode: bool) -> str:
    """Resolve the backend name string for an era and accuracy flag.

    Args:
        era: The gaming era to resolve.
        accuracy_mode: When True, Win9x routes to 86Box instead of VirtualBox.

    Returns:
        A ``BackendSlug`` value string — one of the values in ``BackendSlug``.

    Raises:
        RuntimeError: If eras.yaml cannot be loaded or the era is not configured.
        ValueError: If the era has no resolvable backend.
    """
    try:
        eras_config = _load_eras_config()
    except (FileNotFoundError, yaml.YAMLError) as e:
        raise RuntimeError(f"Failed to load eras.yaml configuration: {e}")

    era_config = eras_config.get(era.value)
    if not era_config:
        raise ValueError(f"Era '{era.value}' not found in eras.yaml")

    # Flat backend key — DOS, Win31, and all console eras use this.
    if 'backend' in era_config:
        return era_config['backend']

    # Win9x: accuracy_mode → 86box, default → virtualbox.
    if era.value in ('win95', 'win98'):
        return BackendSlug.BOX86.value if accuracy_mode else BackendSlug.VIRTUALBOX.value

    # WinXP: always virtualbox.
    if era.value == 'winxp':
        if 'primary' not in era_config:
            raise ValueError(f"Era 'winxp' has no primary backend configured in eras.yaml")
        return era_config['primary']

    raise ValueError(f"Cannot resolve backend for era '{era.value}'")


def get_launch_fn(era: Era, accuracy_mode: bool = False) -> Callable:
    """Return the ``launch`` callable for the backend that handles ``era``.

    For Win9x eras, ``accuracy_mode=True`` routes to 86Box; the default
    routes to VirtualBox.  DOS, Win31, and console eras are unaffected by
    ``accuracy_mode``.

    Args:
        era: The gaming era to resolve.
        accuracy_mode: Route Win9x to 86Box when True.

    Returns:
        The ``launch`` function from the resolved backend module.

    Raises:
        RuntimeError: If eras.yaml cannot be loaded, the era is not
            configured, or the backend module cannot be imported.
    """
    try:
        backend_name = resolve_backend_name(era, accuracy_mode)
    except (ValueError, RuntimeError) as e:
        raise RuntimeError(f"Failed to resolve backend for era '{era.value}': {e}")

    try:
        if backend_name == BackendSlug.DOSBOX.value:
            from backend.service.backends.dosbox import launch
            return launch
        elif backend_name == BackendSlug.BOX86.value:
            from backend.service.backends.box86 import launch
            return launch
        elif backend_name == BackendSlug.VIRTUALBOX.value:
            from backend.service.backends.virtualbox import launch
            return launch
        elif backend_name == BackendSlug.DUCKSTATION.value:
            from backend.service.backends.duckstation import launch
            return launch
        elif backend_name == BackendSlug.PCSX2.value:
            from backend.service.backends.pcsx2 import launch
            return launch
        elif backend_name == BackendSlug.XEMU.value:
            from backend.service.backends.xemu import launch
            return launch
        elif backend_name == BackendSlug.MESEN.value:
            from backend.service.backends.mesen import launch
            return launch
        elif backend_name == BackendSlug.PROJECT64.value:
            from backend.service.backends.project64 import launch
            return launch
        else:
            raise ValueError(f"Unknown backend '{backend_name}' for era '{era.value}'")
    except Exception as e:
        raise RuntimeError(f"Failed to load backend for era '{era.value}': {e}")


def get_backend_name(era: Era, accuracy_mode: bool = False) -> str:
    """Return a human-readable display name for the backend handling ``era``.

    Pure display function for the UI layer — does not validate that the
    backend is installed or functional.

    Args:
        era: The gaming era to look up.
        accuracy_mode: Route Win9x display name to 86Box when True.

    Returns:
        Display name string, or ``"Unknown"`` if the era is not configured.
    """
    try:
        backend_name = resolve_backend_name(era, accuracy_mode)
        return {
            BackendSlug.DOSBOX.value: 'DOSBox-X',
            BackendSlug.BOX86.value: '86Box',
            BackendSlug.VIRTUALBOX.value: 'VirtualBox',
            BackendSlug.DUCKSTATION.value: 'DuckStation',
            BackendSlug.PCSX2.value: 'PCSX2',
            BackendSlug.XEMU.value: 'xemu',
            BackendSlug.MESEN.value: 'Mesen',
            BackendSlug.PROJECT64.value: 'Project64',
        }.get(backend_name, 'Unknown')
    except Exception:
        return 'Unknown'


# Maps BackendSlug value → (settings_key, emulator_key_for_get_binary_path)
_BACKEND_TO_EMULATOR: Dict[str, tuple[str, str]] = {
    BackendSlug.VIRTUALBOX.value:  ('VIRTUALBOX_PATH',  'virtualbox'),
    BackendSlug.BOX86.value:       ('BOX86_PATH',       'box86'),
    BackendSlug.DUCKSTATION.value: ('DUCKSTATION_PATH', 'duckstation'),
    BackendSlug.PCSX2.value:       ('PCSX2_PATH',       'pcsx2'),
    BackendSlug.XEMU.value:        ('XEMU_PATH',        'xemu'),
    BackendSlug.MESEN.value:       ('MESEN_PATH',       'mesen'),
    BackendSlug.PROJECT64.value:   ('PROJECT64_PATH',   'project64'),
}


# NAMING: get_executable_path returns a tuple (path, env_var_name) — the second
# element is the name of the environment variable that supplied the path, not
# another path.  The function name does not signal the two-value return.
def get_executable_path(era: Era, accuracy_mode: bool = False) -> tuple[str, str]:
    """Return the emulator executable path and the settings key that provides it.

    Args:
        era: The gaming era to look up.
        accuracy_mode: Route Win9x to BOX86_PATH when True.

    Returns:
        A tuple of ``(executable_path, settings_key)`` where ``settings_key``
        is the key consulted and ``executable_path`` is its current value,
        or an empty string if the variable is not set.
    """
    try:
        backend_name = resolve_backend_name(era, accuracy_mode)
    except Exception:
        backend_name = BackendSlug.DOSBOX.value

    if backend_name in _BACKEND_TO_EMULATOR:
        env_var, emulator_key = _BACKEND_TO_EMULATOR[backend_name]
    else:
        env_var = 'DOSBOX_PATH'
        emulator_key = BackendSlug.DOSBOX.value

    return get_binary_path(emulator_key), env_var


def launch_media(era, media_path, profile=None):
    """Resolve backend, validate executable, and launch media.

    Single entry point for FastAPI route handlers. Accepts era as either a
    string or an Era enum, and media_path as either a string or a Path, to
    match the types stored in the database.

    Args:
        era: Gaming era as an Era enum or a string matching an Era value.
        media_path: Path to the media file — string or Path object.
        profile: Optional Profile ORM object (reserved for accuracy_mode
            routing on Win9x eras; unused for other eras).

    Returns:
        ``(process, job_object)`` from the backend launch call.

    Raises:
        ValueError: If the era string does not match a known Era value.
        RuntimeError: If the executable path is not configured.
        FileNotFoundError: If the configured executable does not exist on disk.
        Any exception raised by the backend launch function.
    """
    # Coerce era string → Era enum (DB stores eras as strings).
    if isinstance(era, str):
        try:
            era = Era(era)
        except ValueError:
            raise ValueError(
                f"Unknown era '{era}'. "
                f"Valid values: {', '.join(e.value for e in Era)}"
            )

    # Coerce media_path string → Path (DB stores paths as strings).
    if isinstance(media_path, str):
        media_path = Path(media_path)

    # Resolve accuracy_mode and enable_networking from profile if present.
    accuracy_mode = False
    enable_networking = False
    if profile is not None:
        if hasattr(profile, 'accuracy_mode'):
            accuracy_mode = bool(profile.accuracy_mode)
        if hasattr(profile, 'enable_networking'):
            enable_networking = bool(profile.enable_networking)

    executable_path, env_var = get_executable_path(era, accuracy_mode)
    if not executable_path:
        raise RuntimeError(
            f"{env_var} is not configured. "
            "Set the path in config/settings.yaml or via Settings."
        )

    launch_fn = get_launch_fn(era, accuracy_mode)

    # Console backends (DuckStation, PCSX2, xemu, Mesen, Project64) emulate
    # hardware with no meaningful network capability — no enable_networking arg.
    _console_backends = {
        BackendSlug.DUCKSTATION.value,
        BackendSlug.PCSX2.value,
        BackendSlug.XEMU.value,
        BackendSlug.MESEN.value,
        BackendSlug.PROJECT64.value,
    }
    try:
        backend_name = resolve_backend_name(era, accuracy_mode)
    except Exception:
        backend_name = BackendSlug.DOSBOX.value

    if backend_name in _console_backends:
        return launch_fn(media_path=media_path, era=era.value, executable_path=executable_path)

    return launch_fn(
        media_path=media_path,
        era=era.value,
        executable_path=executable_path,
        enable_networking=enable_networking,
    )
