"""
Backend routing utilities for Peach 1UP.
Maps eras to their corresponding backend launch functions.
"""

import yaml
import os
from typing import Callable, Dict, Any

from .constants import Era


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


def get_launch_fn(era: Era) -> Callable:
    """Return the ``launch`` callable for the backend that handles ``era``.

    Reads the backend name from ``eras.yaml``, imports the matching backend
    module, and returns its ``launch`` function.

    Args:
        era: The gaming era to resolve.

    Returns:
        The ``launch`` function from ``backends.dosbox`` or ``backends.box86``.

    Raises:
        RuntimeError: If ``eras.yaml`` cannot be loaded, the era is not
            configured, the backend name is unknown, or the backend module
            cannot be imported.
    """
    try:
        eras_config = _load_eras_config()
    except (FileNotFoundError, yaml.YAMLError) as e:
        raise RuntimeError(f"Failed to load eras.yaml configuration: {e}")

    try:
        era_config = eras_config.get(era.value)
        if not era_config:
            raise ValueError(f"Era '{era.value}' not found in eras.yaml")

        backend_name = era_config.get('backend')
        if not backend_name:
            raise ValueError(f"Backend not configured for era '{era.value}' in eras.yaml")

        if backend_name == 'dosbox':
            from backends.dosbox import launch
            return launch
        elif backend_name == '86box':
            from backends.box86 import launch
            return launch
        else:
            raise ValueError(f"Unknown backend '{backend_name}' for era '{era.value}'")

    except Exception as e:
        raise RuntimeError(f"Failed to resolve backend for era '{era.value}': {e}")


def get_backend_name(era: Era) -> str:
    """Return a human-readable display name for the backend handling ``era``.

    Pure display function for the UI layer — does not validate that the
    backend is installed or functional.

    Args:
        era: The gaming era to look up.

    Returns:
        Display name string (``"DOSBox-X"``, ``"86Box"``), or ``"Unknown"``
        if the era is not in the configuration or an error occurs.
    """
    try:
        eras_config = _load_eras_config()

        era_config = eras_config.get(era.value)
        if not era_config:
            return "Unknown"

        backend_name = era_config.get('backend')
        if not backend_name:
            return "Unknown"

        if backend_name == 'dosbox':
            return "DOSBox-X"
        elif backend_name == '86box':
            return "86Box"
        else:
            return "Unknown"

    except Exception:
        return "Unknown"


# NAMING: get_executable_path returns a tuple (path, env_var_name) — the second
# element is the name of the environment variable that supplied the path, not
# another path.  The function name does not signal the two-value return.
def get_executable_path(era: Era) -> tuple[str, str]:
    """Return the emulator executable path and the env var that provides it.

    Args:
        era: The gaming era to look up.

    Returns:
        A tuple of ``(executable_path, env_var_name)`` where ``env_var_name``
        is the environment variable consulted (``"DOSBOX_PATH"`` or
        ``"BOX86_PATH"``) and ``executable_path`` is its current value, or
        an empty string if the variable is not set.
    """
    if era.value in ('win95', 'win98', 'winxp'):
        env_var = 'BOX86_PATH'
    else:
        env_var = 'DOSBOX_PATH'
    return os.getenv(env_var, ''), env_var
