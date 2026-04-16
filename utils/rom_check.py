"""
ROM pack detection utility for Peach 1UP.
Checks if 86Box ROM pack is present for Windows 95/98/XP eras.
"""

import os


def is_rom_pack_present(rom_path: str) -> bool:
    """
    Check if 86Box ROM pack is present and non-empty.

    Args:
        rom_path: Path to ROM directory. If empty, reads from ROM_PATH env var.

    Returns:
        True if ROM directory exists and contains files, False otherwise.
        Never raises exceptions - returns False for any error condition.

    Notes:
        - Returns False if ROM_PATH env var is missing when rom_path is empty
        - Returns False if directory does not exist
        - Returns False if directory exists but is empty
        - Returns True only if directory exists and contains at least one item
    """
    try:
        # Use provided path or fall back to environment variable
        if not rom_path:
            rom_path = os.getenv('ROM_PATH')
            if not rom_path:
                return False

        # Check if directory exists
        if not os.path.exists(rom_path):
            return False

        if not os.path.isdir(rom_path):
            return False

        # Check if directory is non-empty
        try:
            return len(os.listdir(rom_path)) > 0
        except (PermissionError, OSError):
            return False

    except Exception:
        # Never surface exceptions to caller
        return False