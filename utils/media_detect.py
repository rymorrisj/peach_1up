"""
Media detection utilities for Peach 1UP.
Handles file discovery and era detection for game media.
"""

import locale
import os
from pathlib import Path
from typing import List, Optional

from .constants import Era, ERA_MEDIA_TYPES


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
        - Uses _list_files internally for consistent sorting
        - Case-insensitive extension matching
    """
    all_files = _list_files(path)
    allowed_extensions = ERA_MEDIA_TYPES[era]

    compatible_files = []
    for file_path in all_files:
        if file_path.suffix.lower() in allowed_extensions:
            compatible_files.append(file_path)

    return compatible_files


def detect_era(media_path: Path) -> Optional[Era]:
    """
    Detect the most likely gaming era for a media file.

    Stub implementation - returns None for P0. Full implementation in P1-3.

    Args:
        media_path: Path to media file to analyze

    Returns:
        Most likely Era for the media file, or None if detection fails.
        Always returns None in P0 implementation.

    Notes:
        - P0: Stub only, always returns None
        - P1-3: Will analyze file contents/metadata for era detection
    """
    return None