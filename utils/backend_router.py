"""
Backend routing utilities for Peach 1UP.
Maps eras to their corresponding backend launch functions.
"""

import yaml
import os
from typing import Optional, Callable

from .constants import Era


def get_launch_fn(era: Era) -> Optional[Callable]:
    """
    Get the launch function for the specified era's backend.

    Args:
        era: Gaming era to get launch function for

    Returns:
        Launch function callable for era's backend, or None if backend not implemented.

    Notes:
        - Returns backends.dosbox.launch for dos and win31 eras
        - Returns None for win95, win98, winxp (86Box support coming in P0-9)
        - Reads backend name from eras.yaml configuration
    """
    try:
        # Load eras.yaml to get backend name for this era
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'eras.yaml')
        with open(config_path, 'r') as f:
            eras_config = yaml.safe_load(f)

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
            # 86Box support coming in P0-9
            return None
        else:
            return None

    except Exception:
        # If any error loading config, return None
        return None