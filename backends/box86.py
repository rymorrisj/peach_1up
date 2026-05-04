"""
86Box backend for Peach 1UP
Handles Windows 95, 98, and XP era games using 86Box natively on Windows host.
"""

import os
from pathlib import Path
from typing import List, Tuple
from subprocess import Popen

from utils.job_objects import launch_under_job_object, WindowsJobObject
from utils.rom_check import is_rom_pack_present


# Supported file extensions for 86Box backend
SUPPORTED_MEDIA = {'.iso', '.img', '.cue'}

# Supported eras for 86Box backend
SUPPORTED_ERAS = {'win95', 'win98', 'winxp'}


def validate_media(media_path: Path) -> None:
    """
    Validate media file for 86Box backend.

    Checks that file exists and has supported extension.

    Args:
        media_path: Path to media file

    Raises:
        FileNotFoundError: If media file does not exist
        ValueError: If media file extension is not supported
    """
    if not media_path.exists():
        raise FileNotFoundError(f"Media file not found: {media_path}")

    if media_path.suffix.lower() not in SUPPORTED_MEDIA:
        raise ValueError(f"Unsupported media format '{media_path.suffix}'. "
                        f"86Box backend supports: {', '.join(sorted(SUPPORTED_MEDIA))}")


def validate_rom_pack(rom_path: str) -> None:
    """
    Validate that 86Box ROM pack is present and accessible.

    Args:
        rom_path: Path to ROM directory from environment variable

    Raises:
        RuntimeError: If ROM pack is missing or inaccessible
    """
    if not is_rom_pack_present(rom_path):
        raise RuntimeError(
            f"86Box ROM pack not found or empty in ROM_PATH: {rom_path}. "
            f"86Box requires official ROM files to function. "
            f"Download from: https://github.com/86Box/roms"
        )


def build_args(era: str, rom_path: str) -> List[str]:
    """
    Build 86Box command line arguments for given era and ROM path.

    Args:
        era: Era name ('win95', 'win98', or 'winxp')
        rom_path: Path to ROM directory

    Returns:
        List of command line arguments (excludes executable path)

    Raises:
        ValueError: If era is not in supported set {'win95', 'win98', 'winxp'}

    Notes:
        Hardware profiles and media mounting are config-file driven in 86Box.
        This function only sets ROM path via CLI. Hardware config deferred to P2.
    """
    if era not in SUPPORTED_ERAS:
        raise ValueError(f"Era '{era}' not supported by 86Box backend. "
                        f"Supported: {', '.join(sorted(SUPPORTED_ERAS))}")

    # Only ROM path via CLI — hardware profiles are config-file driven
    return ['--rom-path', rom_path]


def launch(media_path: Path, era: str, executable_path: str) -> Tuple[Popen, WindowsJobObject]:
    """
    Launch 86Box with given media file under Job Object isolation.

    Single entry point for 86Box backend. Validates media, ROM pack, builds arguments,
    and launches process under Job Object with network blocking and memory limits.

    Args:
        media_path: Path to media file to mount
        era: Era name ('win95', 'win98', or 'winxp')
        executable_path: Full path to 86Box executable

    Returns:
        Tuple of (subprocess.Popen process, WindowsJobObject instance)
        Caller is responsible for cleanup via job_object.terminate_all()

    Raises:
        FileNotFoundError: If executable_path or media_path does not exist
        ValueError: If era or media extension not supported
        RuntimeError: If ROM pack missing or Job Object creation/process launch fails
    """
    if not os.path.exists(executable_path):
        raise FileNotFoundError(f"86Box executable not found: {executable_path}")

    validate_media(media_path)

    rom_path = os.getenv('ROM_PATH', '')
    if not rom_path:
        raise RuntimeError("ROM_PATH environment variable not set. "
                          "86Box requires ROM files to function. "
                          "Set ROM_PATH to the directory containing 86Box ROM pack.")

    validate_rom_pack(rom_path)

    args = build_args(era, rom_path)

    job_name = f"peach1up_86box_{era}_{media_path.stem}"

    return launch_under_job_object(
        executable_path=executable_path,
        args=args,
        media_paths=[str(media_path)],
        era=era,
        job_name=job_name
    )
