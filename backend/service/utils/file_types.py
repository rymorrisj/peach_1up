from __future__ import annotations

from pathlib import Path
from typing import get_args

from backend.constants_generated import FileType
from backend.service.utils.eras_config import get_eras

# The generated FileType Literal is the single source of truth for the allowed
# file_type vocabulary. Producers below are validated against it so an
# out-of-set value fails loudly at ingest instead of persisting into the
# String-typed DB column and only surfacing as a read-time 500 later.
_VALID_FILE_TYPES: frozenset[str] = frozenset(get_args(FileType))


def all_supported_extensions() -> frozenset[str]:
    """Return every media extension across all eras in eras.yaml, lowercased."""
    try:
        eras = get_eras()
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
        eras = get_eras()
        return [ext.lower() for ext in eras.get(era, {}).get("supported_media", [])]
    except Exception:
        return []


_ROM_EXTENSIONS = {".nes", ".sfc", ".smc", ".zip", ".z64", ".n64", ".v64"}


def is_drive_image(file: Path, folder_name: str) -> bool:
    """Return True if *file* is the folder's own shared-drive image (e.g. 'rally.img'
    for a folder named 'rally'), not a launchable media file. Only excludes the
    file literally named '{folder_name}.img' — a folder's actual .iso/.img game
    media (e.g. a DOS HDD/floppy dump) must not be excluded by extension alone.
    """
    return file.name.lower() == f"{folder_name}.img".lower()


def _classify_file_type(path: Path) -> str:
    if path.is_dir():
        return "directory"
    suffix = path.suffix.lower()
    if suffix == ".iso":
        return "iso"
    if suffix == ".cue":
        return "cue"
    if suffix == ".chd":
        return "chd"
    if suffix == ".bin":
        return "bin"
    if suffix == ".gdi":
        return "gdi"
    if suffix == ".cdi":
        return "cdi"
    if suffix == ".img":
        try:
            return "floppy" if path.stat().st_size < 2 * 1024 * 1024 else "hdd"
        except OSError:
            return "hdd"
    if suffix in {".exe", ".bat", ".com"}:
        return "exe"
    if suffix in _ROM_EXTENSIONS:
        return "rom"
    return "unknown"


def file_type_from_path(path: Path) -> str:
    """Classify *path* into a FileType value, validated against the generated set.

    Every file_type written to the DB flows through here (items ingest, drive
    hydration). The SQLite column is a bare String and does not enforce the
    Literal, so an out-of-vocabulary value would persist silently and only crash
    later when a Pydantic read model rejects it. Validating at the single
    producer choke-point makes that drift fail loudly at ingest instead.
    """
    file_type = _classify_file_type(path)
    if file_type not in _VALID_FILE_TYPES:
        raise ValueError(
            f"file_type_from_path produced '{file_type}' for '{path}', which is "
            f"not a valid FileType {sorted(_VALID_FILE_TYPES)}. Add it to "
            f"config/constants.yaml file_types and regenerate constants."
        )
    return file_type


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
    folder_name = directory.name
    candidates: list[Path] = []
    for f in directory.iterdir():
        if f.is_file() and f.suffix.lower() in extensions and not is_drive_image(f, folder_name):
            candidates.append(f)
    if not candidates:
        raise ValueError(
            f"No supported media file found in '{directory}'. "
            f"Expected extensions for era '{era}': {', '.join(extensions)}."
        )
    candidates.sort(key=lambda f: (extensions.index(f.suffix.lower()), f.name))
    return candidates[0]
