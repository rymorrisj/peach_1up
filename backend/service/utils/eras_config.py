"""Shared eras.yaml utilities for Peach 1UP.

Single accessor for the parsed eras.yaml config. ``get_eras()`` loads and
caches the file on first call and serves every subsequent call from memory —
eras.yaml is read once per process, not once per call site. lifespan.py warms
this cache at startup via emulator_catalog._get_eras_config(), which delegates
here.
"""

from __future__ import annotations

from typing import Any

import yaml

from backend.core.logger import get_logger
from backend.core.settings import get_base_path

logger = get_logger(__name__)

_ERAS_PATH = get_base_path() / "config" / "eras.yaml"

_ERAS_CACHE: dict[str, Any] | None = None


def get_eras() -> dict[str, Any]:
    """Return the fully parsed eras.yaml config, loading and caching it on first call."""
    global _ERAS_CACHE
    if _ERAS_CACHE is None:
        with _ERAS_PATH.open("r", encoding="utf-8") as f:
            _ERAS_CACHE = yaml.safe_load(f) or {}
    return _ERAS_CACHE


def get_era(era: str) -> dict[str, Any]:
    """Return the config block for *era*, or {} if the era is not configured."""
    block = get_eras().get(era)
    return block if isinstance(block, dict) else {}


def get_cpu_min_rate(era: str) -> int:
    """Return cpu_min_rate_percent from eras.yaml, defaulting to 5 if absent."""
    try:
        eras = get_eras()
        val = eras.get("cpu_min_rate_percent")
        if val is not None:
            return int(val)
    except Exception:
        pass
    logger.warning("cpu_min_rate_percent not found in eras.yaml; defaulting to 5.")
    return 5
