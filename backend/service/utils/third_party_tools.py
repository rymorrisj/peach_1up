"""Loads config/third_party_tools.yaml.

Non-emulator third-party tools bundled with Peach 1UP (e.g. extract-xiso)
that need attribution but must never be surfaced as launchable emulators on
the Emulators page, kept out of config/emulators/*.toml for that reason.
"""

from __future__ import annotations

from typing import Any

import yaml

from backend.core.settings import get_base_path

_PATH = get_base_path() / "config" / "third_party_tools.yaml"

_cache: list[dict[str, Any]] | None = None


def get_third_party_tools() -> list[dict[str, Any]]:
    """Return the parsed third_party_tools.yaml list, loading and caching it on first call."""
    global _cache
    if _cache is None:
        if _PATH.exists():
            with _PATH.open("r", encoding="utf-8") as f:
                _cache = yaml.safe_load(f) or []
        else:
            _cache = []
    return _cache
