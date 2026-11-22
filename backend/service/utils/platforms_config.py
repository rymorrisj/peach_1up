"""Shared platforms.yaml utilities for Peach 1UP.

Single accessor for the parsed platforms.yaml config. ``get_platforms_config()`` loads and
caches the file on first call and serves every subsequent call from memory,
platforms.yaml is read once per process, not once per call site. lifespan.py warms
this cache at startup via emulator_catalog._get_platforms_config(), which delegates
here.
"""

from __future__ import annotations

from typing import Any

import yaml

from backend.core.logger import get_logger
from backend.core.settings import get_base_path

logger = get_logger(__name__)

_PLATFORMS_PATH = get_base_path() / "config" / "platforms.yaml"
_STALE_ERAS_PATH = get_base_path() / "config" / "eras.yaml"

_PLATFORMS_CACHE: dict[str, Any] | None = None

# Hardcoded sanity ceilings for platforms.yaml's Job Object resource limits.
# There is deliberately no platforms.yaml key, settings-table entry, or UI control for either value,
# moving them requires a code change here.
_CPU_LIMIT_CEILING_PERCENT = 90

# Ceiling is 75% of the host's real total physical RAM, queried
# fresh via GlobalMemoryStatusEx (see system_memory.py) at platforms.yaml load
# time, so it scales with the machine actually running the launch.
_MEMORY_LIMIT_CEILING_FRACTION = 0.75


def _memory_limit_ceiling_mb() -> int:
    """Return 75% of real total system RAM in MB, queried fresh (not cached
    across process restarts, only within one process's platforms.yaml cache)."""
    from backend.service.utils.host_os.windows.system_memory import (
        get_total_physical_memory_mb,
    )

    return int(get_total_physical_memory_mb() * _MEMORY_LIMIT_CEILING_FRACTION)


def _clamp_resource_limits(config: dict[str, Any]) -> None:
    """Clamp every platform's memory_limit_mb and cpu_limit_percent to the
    hardcoded sanity ceilings in place, in *config*. Runs once, at the point
    platforms.yaml is loaded and cached, so every reader of get_platforms_config()/get_platform_config()
    downstream sees the clamped value with no per-call-site check of its own.

    A value over its ceiling is logged as a warning and replaced with the
    ceiling for this run, it never raises. A resource-tuning misconfiguration
    in platforms.yaml should degrade loudly, not take the app down at startup.
    """
    memory_ceiling_mb = _memory_limit_ceiling_mb()

    for platform, block in config.items():
        if not isinstance(block, dict):
            continue

        cpu = block.get("cpu_limit_percent")
        if isinstance(cpu, (int, float)) and cpu > _CPU_LIMIT_CEILING_PERCENT:
            logger.warning(
                f"platforms.yaml: platform '{platform}' cpu_limit_percent={cpu} exceeds the "
                f"hardcoded ceiling of {_CPU_LIMIT_CEILING_PERCENT}; using "
                f"{_CPU_LIMIT_CEILING_PERCENT} for this run instead."
            )
            block["cpu_limit_percent"] = _CPU_LIMIT_CEILING_PERCENT

        mem = block.get("memory_limit_mb")
        if isinstance(mem, (int, float)) and mem > memory_ceiling_mb:
            logger.warning(
                f"platforms.yaml: platform '{platform}' memory_limit_mb={mem} exceeds the "
                f"sanity ceiling of {memory_ceiling_mb} (75% of this "
                f"machine's total RAM); using {memory_ceiling_mb} for this "
                "run instead."
            )
            block["memory_limit_mb"] = memory_ceiling_mb


def get_platforms_config() -> dict[str, Any]:
    """Return the fully parsed platforms.yaml config, loading and caching it on first call."""
    global _PLATFORMS_CACHE
    if _PLATFORMS_CACHE is None:
        with _PLATFORMS_PATH.open("r", encoding="utf-8") as f:
            _PLATFORMS_CACHE = yaml.safe_load(f) or {}
        _clamp_resource_limits(_PLATFORMS_CACHE)
    return _PLATFORMS_CACHE


def get_platform_config(platform: str) -> dict[str, Any]:
    """Return the config block for *platform*, or {} if the platform is not configured."""
    block = get_platforms_config().get(platform)
    return block if isinstance(block, dict) else {}


def get_cpu_min_rate(platform: str) -> int:
    """Return cpu_min_rate_percent from platforms.yaml, defaulting to 5 if absent."""
    try:
        platforms = get_platforms_config()
        val = platforms.get("cpu_min_rate_percent")
        if val is not None:
            return int(val)
    except Exception:
        pass
    logger.warning("cpu_min_rate_percent not found in platforms.yaml; defaulting to 5.")
    return 5


def remove_stale_eras_config() -> None:
    """Delete config/eras.yaml left behind by an older install once
    platforms.yaml exists. The installer keeps config/ across upgrades."""
    if not (_PLATFORMS_PATH.is_file() and _STALE_ERAS_PATH.is_file()):
        return
    try:
        _STALE_ERAS_PATH.unlink()
    except OSError as exc:
        logger.warning("Could not remove stale %s: %s", _STALE_ERAS_PATH, exc)
        return
    logger.info("Removed stale %s, replaced by platforms.yaml.", _STALE_ERAS_PATH)
