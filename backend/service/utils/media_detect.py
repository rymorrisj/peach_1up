"""
Media detection utilities for Peach 1UP.
Handles file discovery and era detection for game media.
"""

import locale
import os
from pathlib import Path
from typing import List, Optional

from backend.service.utils.constants import Era, ERA_MEDIA_TYPES


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
    Best-effort detection of gaming era from a media file.

    Tries filename heuristics first, then ISO 9660 volume label for .iso/.cue files.
    Returns None if detection is uncertain — caller must confirm with user.

    Args:
        media_path: Path to media file to analyse

    Returns:
        Detected Era, or None if uncertain.
    """
    if not media_path.exists():
        return None

    era = _detect_from_filename(media_path)
    if era is not None:
        return era

    suffix = media_path.suffix.lower()
    if suffix == ".iso":
        return _detect_from_iso(media_path)
    if suffix == ".cue":
        bin_path = _cue_bin_path(media_path)
        if bin_path is not None:
            return _detect_from_iso(bin_path)

    return None


def _detect_from_filename(media_path: Path) -> Optional[Era]:
    name = media_path.stem.lower()
    if any(k in name for k in ("win95", "windows95", "win_95", "chicago")):
        return Era.WIN95
    if any(k in name for k in ("win98", "windows98", "win_98", "memphis")):
        return Era.WIN98
    if any(k in name for k in ("winxp", "windowsxp", "win_xp", "whistler")):
        return Era.WINXP
    if any(k in name for k in ("win31", "win3.1", "windows31", "wfw", "win311")):
        return Era.WIN31
    if any(k in name for k in ("msdos", "ms-dos", "freedos", "pcdos")):
        return Era.DOS
    return None


def _detect_from_iso(iso_path: Path) -> Optional[Era]:
    """Read ISO 9660 Primary Volume Descriptor and match volume label to known OS strings."""
    try:
        with iso_path.open("rb") as fh:
            fh.seek(32768)          # sector 16, 2048 bytes per sector
            pvd = fh.read(2048)
        if len(pvd) < 72 or pvd[0] != 1:   # must be PVD type
            return None
        vol_id = pvd[40:72].decode("ascii", errors="replace").strip().lower()
        if any(k in vol_id for k in ("win95", "windows 95", "chicago")):
            return Era.WIN95
        if any(k in vol_id for k in ("win98", "windows 98", "memphis")):
            return Era.WIN98
        if any(k in vol_id for k in ("winxp", "windows xp", "whistler", "xp_")):
            return Era.WINXP
        if any(k in vol_id for k in ("win31", "windows 3.1")):
            return Era.WIN31
        return None
    except Exception:
        return None


def _cue_bin_path(cue_path: Path) -> Optional[Path]:
    """Return the binary track path referenced in a .cue file, or None."""
    try:
        for line in cue_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.upper().startswith("FILE "):
                parts = line.split('"')
                if len(parts) >= 2:
                    candidate = cue_path.parent / parts[1]
                    if candidate.exists():
                        return candidate
        return None
    except Exception:
        return None