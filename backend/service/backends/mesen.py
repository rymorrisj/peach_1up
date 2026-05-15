"""Mesen backend for Peach 1UP.

Handles NES launches. Validates the binary path and ROM file, then launches
Mesen under Job Objects with network blocked. No BIOS files required.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from backend.constants import ERA_MEDIA_TYPES
from backend.constants_generated import Era
from backend.service.utils.launcher import launch_under_job_object
from backend.service.utils.sandbox_process import SandboxProcess
from backend.service.utils.job_objects import WindowsJobObject

SUPPORTED_ERAS = {Era.NES.value}
SUPPORTED_MEDIA = ERA_MEDIA_TYPES[Era.NES]


def validate_media(media_path: Path) -> None:
    """Validate that the ROM file exists and has a supported extension.

    Args:
        media_path: Path to the NES ROM file.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file extension is not supported.
    """
    if not media_path.exists():
        raise FileNotFoundError(f"ROM file not found: {media_path}")
    if media_path.suffix.lower() not in SUPPORTED_MEDIA:
        raise ValueError(
            f"Unsupported media format '{media_path.suffix}'. "
            f"Mesen supports: {', '.join(sorted(SUPPORTED_MEDIA))}"
        )


def build_args(media_path: Path) -> list[str]:
    """Build Mesen command line arguments for the given ROM file.

    Args:
        media_path: Path to the NES ROM file.

    Returns:
        List of command line arguments (excludes the executable path).
    """
    return [str(media_path)]


def launch(media_path: Path, era: str, executable_path: str) -> Tuple[SandboxProcess, WindowsJobObject]:
    """Launch Mesen with the given NES ROM under Job Object isolation.

    Args:
        media_path: Path to the NES ROM file to load.
        era: Era string — must be 'nes'.
        executable_path: Full path to the Mesen executable.

    Returns:
        Tuple of (subprocess.Popen process, WindowsJobObject instance).
        Caller is responsible for cleanup via job_object.terminate_all().

    Raises:
        FileNotFoundError: If the executable or ROM file does not exist.
        ValueError: If the file extension is unsupported.
        RuntimeError: If process launch fails.
    """
    if not Path(executable_path).exists():
        raise FileNotFoundError(f"Mesen executable not found: {executable_path}")

    validate_media(media_path)

    args = build_args(media_path)
    job_name = f"peach1up_mesen_{media_path.stem}"

    return launch_under_job_object(
        executable_path=executable_path,
        args=args,
        media_paths=[str(media_path)],
        era=era,
        job_name=job_name,
    )
