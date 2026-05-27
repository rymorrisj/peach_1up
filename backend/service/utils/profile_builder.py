"""Profile builder utilities for Peach 1UP.

Library scan pipeline. Pure business logic with no Textual dependencies,
callable from FastAPI route handlers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backend.constants_generated import Era


_COVER_STEMS: frozenset[str] = frozenset({"cover"})
_COVER_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".webp"})


def sanitize_name(stem: str) -> str:
    """Produce a safe profile name from a filename stem.

    Strips characters invalid in a YAML filename stem, collapses runs of
    whitespace and hyphens to underscores, and truncates to 50 characters.

    Args:
        stem: The filename stem to sanitise (no extension).

    Returns:
        A non-empty safe profile name string.
    """
    name = re.sub(r"[^\w\s\-]", "", stem).strip()
    name = re.sub(r"[\s\-]+", "_", name)
    return name[:50] or "unnamed"


@dataclass
class ScanEntry:
    """A single media file found during a library scan.

    Attributes:
        path: Absolute path to the media file.
        era: Detected era, or ``None`` if detection was uncertain.
        name: Sanitised profile name derived from the filename stem.
        folder_path: Absolute path to the item's folder (library/games/{era}/{slug}/),
            or ``None`` when scanning a flat directory.
        cover_path: Absolute path to cover.{jpg,jpeg,png,webp} found in
            ``folder_path``, or ``None`` if absent.
        selected: Whether this entry is marked for import. Defaults to True.
    """
    path: Path
    era: Optional[Era]
    name: str
    folder_path: Optional[Path] = None
    cover_path: Optional[Path] = None
    selected: bool = True


def _find_cover(folder: Path) -> Optional[Path]:
    """Return the first cover image found in ``folder``, or ``None``."""
    try:
        for p in folder.iterdir():
            if (
                p.is_file()
                and p.stem.lower() in _COVER_STEMS
                and p.suffix.lower() in _COVER_EXTENSIONS
            ):
                return p
    except (OSError, PermissionError):
        pass
    return None


def scan_directory(base: Path, era: Era) -> list[ScanEntry]:
    """Walk ``base`` recursively and return a ``ScanEntry`` for each media file.

    Recognises the library/games/{era}/{slug}/ layout: when a media file is
    found directly inside a two-level subdirectory of ``base``, the slug
    folder is recorded as ``folder_path`` and any cover.{jpg,jpeg,png,webp}
    in that folder is recorded as ``cover_path``. Flat layouts (media not
    inside a two-level slug folder) leave both fields as ``None``.

    Skips files and directories that raise ``OSError`` or ``PermissionError``
    rather than aborting the scan. Returns results sorted by path.

    Args:
        base: Directory to scan recursively.
        era: Gaming era used to determine compatible extensions and apply the
            blocklist defined in ``get_compatible_media``.

    Returns:
        Sorted list of ``ScanEntry`` objects for compatible media files.
        Empty if none are found or ``base`` is unreadable.
    """
    from backend.service.utils.media_detect import detect_era, get_compatible_media

    all_dirs: list[Path] = [base]
    try:
        for p in base.rglob("*"):
            try:
                if p.is_dir():
                    all_dirs.append(p)
            except (OSError, PermissionError):
                continue
    except (OSError, PermissionError):
        pass

    seen: set[Path] = set()
    found: list[Path] = []
    for d in all_dirs:
        for f in get_compatible_media(era, str(d)):
            if f not in seen:
                seen.add(f)
                found.append(f)
    found.sort()

    entries: list[ScanEntry] = []
    for p in found:
        # Check whether the file sits at base/{era}/{slug}/media — two levels deep.
        try:
            rel = p.relative_to(base)
        except ValueError:
            rel = None
        folder_path: Optional[Path] = None
        cover_path: Optional[Path] = None
        if rel is not None and len(rel.parts) == 3:
            slug_folder = base / rel.parts[0] / rel.parts[1]
            if slug_folder.is_dir():
                folder_path = slug_folder
                cover_path = _find_cover(slug_folder)
        entries.append(
            ScanEntry(
                path=p,
                era=detect_era(p),
                name=sanitize_name(p.stem),
                folder_path=folder_path,
                cover_path=cover_path,
            )
        )
    return entries


