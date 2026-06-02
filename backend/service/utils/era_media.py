from __future__ import annotations

from pathlib import Path

import yaml

from backend.core.settings import get_base_path

_ERAS_PATH = get_base_path() / "config" / "eras.yaml"


def all_supported_extensions() -> frozenset[str]:
    """Return every media extension across all eras in eras.yaml, lowercased."""
    try:
        eras = yaml.safe_load(_ERAS_PATH.read_text(encoding="utf-8")) or {}
        exts: set[str] = set()
        for era_data in eras.values():
            if isinstance(era_data, dict):
                for ext in era_data.get("supported_media", []):
                    exts.add(ext.lower())
        return frozenset(exts)
    except Exception:
        return frozenset()


def supported_extensions_for_era(era: str) -> list[str]:
    try:
        eras = yaml.safe_load(_ERAS_PATH.read_text(encoding="utf-8")) or {}
        return [ext.lower() for ext in eras.get(era, {}).get("supported_media", [])]
    except Exception:
        return []


def resolve_media_file_from_directory(directory: Path, era: str | None) -> Path:
    """Return the best media file in *directory* for the given era.

    Raises ValueError if era is unset, no supported extensions are configured,
    or no matching file exists. Candidates are sorted by extension priority
    (order in eras.yaml supported_media list) then by filename.
    """
    if not era:
        raise ValueError(
            f"Cannot resolve a launch file from directory '{directory}': "
            "the item has no era set. Please set the era on the item."
        )
    extensions = supported_extensions_for_era(era)
    if not extensions:
        raise ValueError(
            f"Cannot resolve a launch file from directory '{directory}': "
            f"no supported_media extensions found for era '{era}' in eras.yaml."
        )
    candidates: list[Path] = []
    for f in directory.iterdir():
        if f.is_file() and f.suffix.lower() in extensions:
            candidates.append(f)
    if not candidates:
        raise ValueError(
            f"No supported media file found in '{directory}'. "
            f"Expected extensions for era '{era}': {', '.join(extensions)}."
        )
    candidates.sort(key=lambda f: (extensions.index(f.suffix.lower()), f.name))
    return candidates[0]
