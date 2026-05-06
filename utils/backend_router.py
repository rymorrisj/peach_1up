"""Backend routing utilities for Peach 1UP.

Maps eras to their corresponding backend launch functions, accounting for
the multi-tier routing introduced in P2 (primary / compat / accuracy).
"""

import os
import yaml
from typing import Callable, Dict, Any

from utils.constants import Era
from utils.settings import get_binary_path


def _load_eras_config() -> Dict[str, Any]:
    """Load and parse ``config/eras.yaml``.

    Returns:
        Dictionary mapping era keys to their configuration values.

    Raises:
        FileNotFoundError: If ``eras.yaml`` cannot be found.
        yaml.YAMLError: If the file exists but is not valid YAML.
    """
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'eras.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def resolve_backend_name(era: Era, accuracy_mode: bool) -> str:
    """Resolve the backend name string for an era and accuracy flag.

    Args:
        era: The gaming era to resolve.
        accuracy_mode: When True, Win9x routes to 86Box instead of VirtualBox.

    Returns:
        One of ``'dosbox'``, ``'86box'``, or ``'virtualbox'``.

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

    # DOS and Win31 use a flat backend key — no multi-tier routing.
    if 'backend' in era_config:
        return era_config['backend']

    # Win9x: accuracy_mode → 86box, default → virtualbox.
    if era.value in ('win95', 'win98'):
        return '86box' if accuracy_mode else 'virtualbox'

    # WinXP: always virtualbox.
    if era.value == 'winxp':
        if 'primary' not in era_config:
            raise ValueError(f"Era 'winxp' has no primary backend configured in eras.yaml")
        return era_config['primary']

    raise ValueError(f"Cannot resolve backend for era '{era.value}'")


def get_launch_fn(era: Era, accuracy_mode: bool = False) -> Callable:
    """Return the ``launch`` callable for the backend that handles ``era``.

    For Win9x eras, ``accuracy_mode=True`` routes to 86Box; the default
    routes to VirtualBox.  DOS and Win31 are unaffected by ``accuracy_mode``.

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
        if backend_name == 'dosbox':
            from backends.dosbox import launch
            return launch
        elif backend_name == '86box':
            from backends.box86 import launch
            return launch
        elif backend_name == 'virtualbox':
            from backends.virtualbox import launch
            return launch
        else:
            raise ValueError(f"Unknown backend '{backend_name}' for era '{era.value}'")
    except Exception as e:
        raise RuntimeError(f"Failed to resolve backend for era '{era.value}': {e}")


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
            'dosbox': 'DOSBox-X',
            '86box': '86Box',
            'virtualbox': 'VirtualBox',
        }.get(backend_name, 'Unknown')
    except Exception:
        return 'Unknown'


# NAMING: get_executable_path returns a tuple (path, env_var_name) — the second
# element is the name of the environment variable that supplied the path, not
# another path.  The function name does not signal the two-value return.
def get_executable_path(era: Era, accuracy_mode: bool = False) -> tuple[str, str]:
    """Return the emulator executable path and the env var that provides it.

    Args:
        era: The gaming era to look up.
        accuracy_mode: Route Win9x to BOX86_PATH when True.

    Returns:
        A tuple of ``(executable_path, env_var_name)`` where ``env_var_name``
        is the environment variable consulted and ``executable_path`` is its
        current value, or an empty string if the variable is not set.
    """
    try:
        backend_name = resolve_backend_name(era, accuracy_mode)
    except Exception:
        backend_name = 'dosbox'

    if backend_name == 'virtualbox':
        env_var = 'VIRTUALBOX_PATH'
        emulator_key = 'virtualbox'
    elif backend_name == '86box':
        env_var = 'BOX86_PATH'
        emulator_key = 'box86'
    else:
        env_var = 'DOSBOX_PATH'
        emulator_key = 'dosbox'

    return get_binary_path(emulator_key), env_var


def launch_media(era: Era, media_path):
    """Resolve backend, validate executable, and launch media.

    Single entry point for FastAPI route handlers and the TUI launch flow.
    Resolves the backend for the era, validates that the executable is
    configured and present, then calls the backend ``launch`` function.

    Args:
        era: Gaming era to launch.
        media_path: ``Path`` to the media file to mount.

    Returns:
        ``(process, job_object)`` from the backend launch call.

    Raises:
        RuntimeError: If the executable path is not configured.
        FileNotFoundError: If the configured executable does not exist on disk.
        ValueError: If the era has no resolvable backend.
        Any exception raised by the backend launch function.
    """
    executable_path, env_var = get_executable_path(era)
    if not executable_path:
        raise RuntimeError(
            f"{env_var} is not configured. "
            "Set the path in config/settings.yaml or via Settings."
        )
    launch_fn = get_launch_fn(era)
    return launch_fn(media_path=media_path, era=era.value, executable_path=executable_path)
