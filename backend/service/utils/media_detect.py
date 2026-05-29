"""
Media detection utilities for Peach 1UP.
Handles file discovery and era detection for game media.
"""

import locale
import os
from pathlib import Path
from typing import List, Optional

from backend.constants_generated import Era
from backend.constants import ERA_MEDIA_TYPES


def _list_files(path: str) -> List[Path]:
    """
    List all files in directory with unicode-correct alphabetical sorting.

    Private helper function for media discovery.

    Args:
        path: Directory path to scan

    Returns:
        List of Path objects sorted alphanumerically using locale.strxfrm.
        Returns empty list if directory missing, unreadable, or any error occurs.
        Never raises exceptions.

    Notes:
        - Uses locale.strxfrm for proper unicode sorting
        - Filters out directories, returns files only
        - Safe against all I/O errors
    """
    try:
        if not os.path.exists(path) or not os.path.isdir(path):
            return []

        entries = os.listdir(path)
        files = []

        for entry in entries:
            entry_path = Path(path) / entry
            try:
                if entry_path.is_file():
                    files.append(entry_path)
            except (OSError, PermissionError):
                # Skip files we can't access
                continue

        # Sort using locale-aware comparison for proper unicode handling
        files.sort(key=lambda p: locale.strxfrm(p.name))
        return files

    except Exception:
        # Never raise exceptions, return empty list on any error
        return []


_BLOCKED_EXTENSIONS = frozenset({".img"})
_BLOCKED_FILENAMES = frozenset({"setup.exe", "setup.bat", "install.exe", "install.bat"})


def get_compatible_media(era: Era, path: str) -> List[Path]:
    """
    Find media files compatible with the specified gaming era.

    Args:
        era: Gaming era to filter media types for
        path: Directory path to search for media files

    Returns:
        List of Path objects for compatible media files, alphanumerically sorted.
        Returns empty list if no compatible files found or directory inaccessible.

    Notes:
        - Filters files by ERA_MEDIA_TYPES[era] extensions
        - Excludes .img files and common setup/installer filenames
        - Uses _list_files internally for consistent sorting
        - Case-insensitive extension and filename matching
    """
    all_files = _list_files(path)
    allowed_extensions = ERA_MEDIA_TYPES[era] - _BLOCKED_EXTENSIONS

    compatible_files = []
    for file_path in all_files:
        if file_path.suffix.lower() in allowed_extensions:
            if file_path.name.lower() not in _BLOCKED_FILENAMES:
                compatible_files.append(file_path)

    return compatible_files


def detect_media_type(path: Path) -> str:
    if path.is_dir():
        return "directory"
    suffix = path.suffix.lower()
    if suffix == ".iso":
        return "iso"
    if suffix == ".cue":
        return "cue"
    if suffix == ".img":
        try:
            return "floppy" if path.stat().st_size < 2 * 1024 * 1024 else "hdd"
        except OSError:
            return "hdd"
    if suffix in {".exe", ".bat", ".com"}:
        return "exe"
    return "unknown"


