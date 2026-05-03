"""ROM pack detection utility for Peach 1UP."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def is_rom_pack_present(rom_path: Optional[str]) -> bool:
    """
    Check if 86Box ROM pack is present and non-empty.

    Returns True only if rom_path points to an existing, non-empty directory.
    Returns False if rom_path is None, empty, missing, or empty directory.
    Never raises exceptions.
    """
    if not rom_path:
        return False
    try:
        p = Path(rom_path)
        if not p.is_dir():
            return False
        return any(p.iterdir())
    except (PermissionError, OSError):
        return False
