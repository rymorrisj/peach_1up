"""Project64 backend for Peach 1UP.

Handles Nintendo 64 launches. Validates the binary path and ROM file, then
launches Project64 under Job Objects with network blocked. No BIOS files
required.
"""

from __future__ import annotations

from pathlib import Path
from subprocess import Popen
from typing import Tuple

from backend.service.utils.job_objects import launch_direct, WindowsJobObject


SUPPORTED_MEDIA = {'.z64', '.n64', '.v64'}
SUPPORTED_ERAS = {'n64'}


def validate_media(media_path: Path) -> None:
    """Validate that the ROM file exists and has a supported extension.

    Args:
        media_path: Path to the N64 ROM file.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file extension is not supported.
    """
    if not media_path.exists():
        raise FileNotFoundError(f"ROM file not found: {media_path}")
    if media_path.suffix.lower() not in SUPPORTED_MEDIA:
        raise ValueError(
            f"Unsupported media format '{media_path.suffix}'. "
            f"Project64 supports: {', '.join(sorted(SUPPORTED_MEDIA))}"
        )


def build_args(media_path: Path) -> list[str]:
    """Build Project64 command line arguments for the given ROM file.

    Args:
        media_path: Path to the N64 ROM file.

    Returns:
        List of command line arguments (excludes the executable path).
    """
    return [str(media_path)]


def launch(media_path: Path, era: str, executable_path: str) -> Tuple[Popen, WindowsJobObject]:
    """Launch Project64 with the given N64 ROM under Job Object isolation.

    Args:
        media_path: Path to the N64 ROM file to load.
        era: Era string — must be 'n64'.
        executable_path: Full path to the Project64 executable.

    Returns:
        Tuple of (subprocess.Popen process, WindowsJobObject instance).
        Caller is responsible for cleanup via job_object.terminate_all().

    Raises:
        FileNotFoundError: If the executable or ROM file does not exist.
        ValueError: If the file extension is unsupported.
        RuntimeError: If process launch fails.
    """
    if not Path(executable_path).exists():
        raise FileNotFoundError(f"Project64 executable not found: {executable_path}")

    validate_media(media_path)

    args = build_args(media_path)
    job_name = f"peach1up_project64_{media_path.stem}"

    return launch_direct(
        executable_path=executable_path,
        args=args,
        era=era,
        job_name=job_name,
    )
