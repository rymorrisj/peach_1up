"""
Backend routing utilities for Peach 1UP.
Maps eras to their corresponding backend launch functions.
"""

import yaml
import os
from typing import Optional, Callable, Dict, Any

from .constants import Era


def _load_eras_config() -> Dict[str, Any]:
    """
    Load and parse eras.yaml configuration file.

    Returns:
        Dictionary containing eras configuration data

    Raises:
        Exception: If file not found or YAML parsing fails
    """
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'eras.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def get_launch_fn(era: Era) -> Optional[Callable]:
    """
    Get the launch function for the specified era's backend.

    Args:
        era: Gaming era to get launch function for

    Returns:
        Launch function callable for era's backend, or None if backend not implemented.

    Notes:
        - Returns backends.dosbox.launch for dos and win31 eras
        - Returns backends.box86.launch for win95, win98, winxp eras
        - Reads backend name from eras.yaml configuration
    """
    try:
        eras_config = _load_eras_config()

        era_config = eras_config.get(era.value)
        if not era_config:
            return None

        backend_name = era_config.get('backend')
        if not backend_name:
            return None

        # Route to appropriate backend
        if backend_name == 'dosbox':
            from ..backends.dosbox import launch
            return launch
        elif backend_name == '86box':
            from ..backends.box86 import launch
            return launch
        else:
            return None

    except Exception:
        # If any error loading config, return None
        return None


def get_backend_name(era: Era) -> str:
    """
    Get the display name of the backend for the specified era.

    Args:
        era: Gaming era to get backend name for

    Returns:
        Human-readable backend name (e.g., "DOSBox-X", "86Box")
        Returns "Unknown" if era not found in configuration

    Notes:
        - Pure display function for UI layer
        - Does not validate backend implementation status
        - Maps backend config names to display names
    """
    try:
        eras_config = _load_eras_config()

        era_config = eras_config.get(era.value)
        if not era_config:
            return "Unknown"

        backend_name = era_config.get('backend')
        if not backend_name:
            return "Unknown"

        # Map config names to display names
        if backend_name == 'dosbox':
            return "DOSBox-X"
        elif backend_name == '86box':
            return "86Box"
        else:
            return "Unknown"

    except Exception:
        # If any error loading config, return fallback
        return "Unknown"


def get_executable_path(era: Era) -> tuple[str, str]:
    """
    Get the executable path and env var name for the specified era's backend.
    
    Returns:
        Tuple of (executable_path, env_var_name)
    """
    if era.value in ('win95', 'win98', 'winxp'):
        env_var = 'BOX86_PATH'
    else:
        env_var = 'DOSBOX_PATH'
    return os.getenv(env_var, ''), env_var