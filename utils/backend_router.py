"""Backend routing utilities for Peach 1UP.

Maps eras to their corresponding backend launch functions, accounting for
the multi-tier routing introduced in P2 (primary / compat / accuracy).
"""

import os
import yaml
from typing import Callable, Dict, Any

from utils.constants import Era


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


def _resolve_backend_name(era: Era, accuracy_mode: bool) -> str:
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
        backend_name = _resolve_backend_name(era, accuracy_mode)
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
        backend_name = _resolve_backend_name(era, accuracy_mode)
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
        backend_name = _resolve_backend_name(era, accuracy_mode)
    except Exception:
        backend_name = 'dosbox'

    if backend_name == 'virtualbox':
        env_var = 'VIRTUALBOX_PATH'
    elif backend_name == '86box':
        env_var = 'BOX86_PATH'
    else:
        env_var = 'DOSBOX_PATH'

    return os.getenv(env_var, ''), env_var
