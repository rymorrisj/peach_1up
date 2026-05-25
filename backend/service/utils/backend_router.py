"""Backend routing utilities for Peach 1UP.

Maps eras to their corresponding backend launch functions. 86Box eras
(win95, win98, winxp) always route to 86Box. DOS and console eras route
to their dedicated backends. No accuracy-mode conditional exists.
"""

import yaml
from pathlib import Path
from typing import Callable, Dict, Any

from backend.constants_generated import BackendSlug, Era
from backend.core.settings import get_base_path
from backend.service.utils.settings import get_binary_path


def _load_eras_config() -> Dict[str, Any]:
    """Load and parse ``config/eras.yaml``."""
    config_path = get_base_path() / "config" / "eras.yaml"
    with config_path.open('r') as f:
        return yaml.safe_load(f)


_ERAS_CONFIG: Dict[str, Any] = _load_eras_config()


def resolve_backend_name(era: Era) -> str:
    """Resolve the backend name string for an era.

    86Box eras (win95, win98, winxp) always route to 86Box. DOS, Win31,
    and console eras use the flat 'backend' key from eras.yaml.

    Args:
        era: The gaming era to resolve.

    Returns:
        A ``BackendSlug`` value string — one of the values in ``BackendSlug``.

    Raises:
        RuntimeError: If eras.yaml cannot be loaded or the era is not configured.
        ValueError: If the era has no resolvable backend.
    """
    era_config = _ERAS_CONFIG.get(era.value)
    if not era_config:
        raise ValueError(f"Era '{era.value}' not found in eras.yaml")

    # Flat backend key — DOS, Win31, and all console eras use this.
    if 'backend' in era_config:
        return era_config['backend']

    # 86Box eras (win95, win98, winxp) always route to 86Box.
    if era.value in ('win95', 'win98', 'winxp'):
        return BackendSlug.BOX86.value

    raise ValueError(f"Cannot resolve backend for era '{era.value}'")


def get_launch_fn(era: Era) -> Callable:
    """Return the ``launch`` callable for the backend that handles ``era``.

    Args:
        era: The gaming era to resolve.

    Returns:
        The ``launch`` function from the resolved backend module.

    Raises:
        RuntimeError: If eras.yaml cannot be loaded, the era is not
            configured, or the backend module cannot be imported.
    """
    try:
        backend_name = resolve_backend_name(era)
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
        elif backend_name == BackendSlug.FLYCAST.value:
            from backend.service.backends.flycast import launch
            return launch
        else:
            raise ValueError(f"Unknown backend '{backend_name}' for era '{era.value}'")
    except Exception as e:
        raise RuntimeError(f"Failed to load backend for era '{era.value}': {e}")


def get_backend_name(era: Era) -> str:
    """Return a human-readable display name for the backend handling ``era``.

    Pure display function for the UI layer — does not validate that the
    backend is installed or functional.

    Args:
        era: The gaming era to look up.

    Returns:
        Display name string, or ``"Unknown"`` if the era is not configured.
    """
    try:
        backend_name = resolve_backend_name(era)
        return {
            BackendSlug.DOSBOX.value: 'DOSBox-X',
            BackendSlug.BOX86.value: '86Box',
            BackendSlug.VIRTUALBOX.value: 'VirtualBox',
            BackendSlug.DUCKSTATION.value: 'DuckStation',
            BackendSlug.PCSX2.value: 'PCSX2',
            BackendSlug.XEMU.value: 'xemu',
            BackendSlug.MESEN.value: 'Mesen',
            BackendSlug.PROJECT64.value: 'Project64',
            BackendSlug.FLYCAST.value: 'Flycast',
        }.get(backend_name, 'Unknown')
    except Exception:
        return 'Unknown'


# Maps BackendSlug value → (settings_key, emulator_key_for_get_binary_path)
_BACKEND_TO_EMULATOR: Dict[str, tuple[str, str]] = {
    BackendSlug.DOSBOX.value:      ('DOSBOX_PATH',      'dosbox'),
    BackendSlug.BOX86.value:       ('BOX86_PATH',       'box86'),
    BackendSlug.VIRTUALBOX.value:  ('VIRTUALBOX_PATH',  'virtualbox'),
    BackendSlug.DUCKSTATION.value: ('DUCKSTATION_PATH', 'duckstation'),
    BackendSlug.PCSX2.value:       ('PCSX2_PATH',       'pcsx2'),
    BackendSlug.XEMU.value:        ('XEMU_PATH',        'xemu'),
    BackendSlug.MESEN.value:       ('MESEN_PATH',       'mesen'),
    BackendSlug.PROJECT64.value:   ('PROJECT64_PATH',   'project64'),
    BackendSlug.FLYCAST.value:     ('FLYCAST_PATH',     'flycast'),
}


def get_executable_path(era: Era) -> tuple[str, str]:
    """Return the emulator executable path and the settings key that provides it.

    Args:
        era: The gaming era to look up.

    Returns:
        A tuple of ``(executable_path, settings_key)`` where ``settings_key``
        is the settings.yaml key consulted and ``executable_path`` is its
        current value, or an empty string if not configured.

    Raises:
        RuntimeError: If the era cannot be resolved or has no emulator mapping.
    """
    backend_name = resolve_backend_name(era)

    if backend_name not in _BACKEND_TO_EMULATOR:
        raise RuntimeError(
            f"No executable mapping for backend '{backend_name}' (era '{era.value}'). "
            "Add an entry to _BACKEND_TO_EMULATOR in backend_router.py."
        )

    settings_key, emulator_key = _BACKEND_TO_EMULATOR[backend_name]
    return get_binary_path(emulator_key), settings_key


def launch_media(era, media_path, profile=None, platform=None, game_executable: str | None = None, launch_commands: list[str] | None = None, drive=None):
    """Resolve backend, validate executable, and launch media.

    Single entry point for FastAPI route handlers. Accepts era as either a
    string or an Era enum, and media_path as either a string or a Path, to
    match the types stored in the database.

    Args:
        era: Gaming era as an Era enum or a string matching an Era value.
        media_path: Path to the media file — string or Path object.
        profile: Optional Profile ORM object used for enable_networking.
        platform: Optional Platform ORM object required for Win9x/WinXP eras.
        game_executable: Optional executable name passed to DOS backends.

    Returns:
        ``(process, job_object)`` from the backend launch call.

    Raises:
        ValueError: If the era string does not match a known Era value.
        RuntimeError: If the executable path is not configured or the era
            cannot be resolved.
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

    enable_networking = False
    if profile is not None and hasattr(profile, 'enable_networking'):
        enable_networking = bool(profile.enable_networking)

    executable_path, settings_key = get_executable_path(era)
    if not executable_path:
        raise RuntimeError(
            f"The emulator path for '{settings_key}' is not configured. "
            "Set it in config/settings.yaml or via the Settings page."
        )

    launch_fn = get_launch_fn(era)
    backend_name = resolve_backend_name(era)

    _console_backends = {
        BackendSlug.DUCKSTATION.value,
        BackendSlug.PCSX2.value,
        BackendSlug.MESEN.value,
        BackendSlug.PROJECT64.value,
        BackendSlug.FLYCAST.value,
    }
    _platform_backends = {
        BackendSlug.BOX86.value,
        BackendSlug.VIRTUALBOX.value,
        BackendSlug.XEMU.value,
    }

    if backend_name in _console_backends:
        return launch_fn(media_path=media_path, era=era.value, executable_path=executable_path)

    if backend_name in _platform_backends:
        if platform is None:
            raise RuntimeError(
                f"A Platform record is required to launch era '{era.value}' "
                "but none was provided."
            )
        return launch_fn(platform, media_path=media_path, enable_networking=enable_networking)

    if profile is None:
        raise RuntimeError(
            f"A Profile record is required to launch era '{era.value}' "
            "but none was provided."
        )
    return launch_fn(
        media_path=media_path,
        era=era.value,
        executable_path=executable_path,
        enable_networking=enable_networking,
        game_executable=game_executable,
        launch_commands=launch_commands,
        profile=profile,
        drive=drive,
    )
