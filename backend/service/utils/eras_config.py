"""Shared eras.yaml utilities for Peach 1UP."""

from __future__ import annotations

import yaml

from backend.core.logger import get_logger
from backend.core.settings import get_base_path

logger = get_logger(__name__)

_ERAS_PATH = get_base_path() / "config" / "eras.yaml"


def get_cpu_min_rate(era: str) -> int:
    """Return cpu_min_rate_percent from eras.yaml, defaulting to 5 if absent."""
    try:
        eras = yaml.safe_load(_ERAS_PATH.read_text(encoding="utf-8")) or {}
        val = eras.get("cpu_min_rate_percent")
        if val is not None:
            return int(val)
    except Exception:
        pass
    logger.warning("cpu_min_rate_percent not found in eras.yaml; defaulting to 5.")
    return 5
