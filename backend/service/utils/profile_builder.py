"""Profile builder utilities for Peach 1UP.

Library scan pipeline. Pure business logic with no Textual dependencies,
callable from FastAPI route handlers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backend.service.utils.era_media import all_supported_extensions


_COVER_STEMS: frozenset[str] = frozenset({"cover"})
_COVER_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".webp"})

_EXECUTABLE_PRIORITY: list[str] = [".cue", ".iso", ".chd", ".xiso", ".zip", ".exe"]


@dataclass
class FolderScanEntry:
    """One item candidate found during a media folder scan.

    Attributes:
        folder_path:     Absolute path to the item's folder under library/media/.
        name:            Display name derived from the folder name (hyphens to spaces, title-cased).
        executable_path: Highest-priority launchable file in the folder, or None.
        cover_path:      Cover image found in the folder, or None.
    """
    folder_path: Path
    name: str
    executable_path: Optional[Path]
    cover_path: Optional[Path]


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


def scan_media_folders(base: Path) -> list[FolderScanEntry]:
    """Walk one level deep under ``base`` and return one entry per direct subfolder.

    Each non-hidden subfolder of ``base`` is treated as one library item. The
    best-guess launchable file is chosen from the folder's direct contents using
    the priority order defined in ``_EXECUTABLE_PRIORITY``
    (.cue > .iso > .chd > .xiso > .exe). The file matching ``{folder_name}.img``
    is always excluded — it is a drive image, not launchable media. Subdirectories
    that raise ``OSError`` or ``PermissionError`` are skipped silently.

    Args:
        base: Root directory to scan one level deep (library/media/).

    Returns:
        List of ``FolderScanEntry`` objects sorted by folder name (case-insensitive).
        Empty if ``base`` is unreadable or has no qualifying subdirectories.
    """
    entries: list[FolderScanEntry] = []
    supported_exts = all_supported_extensions()

    try:
        children = list(base.iterdir())
    except (OSError, PermissionError):
        return []

    subdirs = sorted(
        (p for p in children if p.is_dir() and not p.name.startswith(".")),
        key=lambda p: p.name.lower(),
    )
    loose_files = sorted(
        (p for p in children if p.is_file() and not p.name.startswith(".")),
        key=lambda p: p.name.lower(),
    )

    for folder in subdirs:
        folder_name = folder.name
        drive_img_lower = f"{folder_name}.img".lower()

        try:
            all_files = [f for f in folder.iterdir() if f.is_file()]
        except (OSError, PermissionError):
            all_files = []

        candidates = [f for f in all_files if f.name.lower() != drive_img_lower]

        executable: Optional[Path] = None
        for ext in _EXECUTABLE_PRIORITY:
            for f in candidates:
                if f.suffix.lower() == ext:
                    executable = f
                    break
            if executable is not None:
                break

        name = folder_name.replace("-", " ").title()
        cover = _find_cover(folder)

        entries.append(FolderScanEntry(
            folder_path=folder,
            name=name,
            executable_path=executable,
            cover_path=cover,
        ))

    for f in loose_files:
        ext = f.suffix.lower()
        if ext == ".zip":
            # zip extraction deferred
            entries.append(FolderScanEntry(
                folder_path=f.parent,
                name=f.stem.replace("-", " ").title(),
                executable_path=f,
                cover_path=None,
            ))
        elif ext in supported_exts:
            entries.append(FolderScanEntry(
                folder_path=f.parent,
                name=f.stem.replace("-", " ").title(),
                executable_path=f,
                cover_path=None,
            ))

    return entries
