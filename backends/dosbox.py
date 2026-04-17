"""
DOSBox-X backend for Peach 1UP
Handles DOS and Windows 3.1 era games using DOSBox-X natively on Windows host.
"""

import os
from pathlib import Path
from typing import List, Tuple
from subprocess import Popen

from ..utils.job_objects import launch_under_job_object, WindowsJobObject


# Supported file extensions for DOSBox-X backend
SUPPORTED_MEDIA = {'.iso', '.img', '.cue'}

# Supported eras for DOSBox-X backend
SUPPORTED_ERAS = {'dos', 'win31'}


def validate_media(media_path: Path) -> None:
    """
    Validate media file for DOSBox-X backend.

    Checks that file exists and has supported extension.

    Args:
        media_path: Path to media file

    Raises:
        FileNotFoundError: If media file does not exist
        ValueError: If media file extension is not supported
    """
    # Check if file exists
    if not media_path.exists():
        raise FileNotFoundError(f"Media file not found: {media_path}")

    # Check if file extension is supported
    if media_path.suffix.lower() not in SUPPORTED_MEDIA:
        raise ValueError(f"Unsupported media format '{media_path.suffix}'. "
                        f"DOSBox-X backend supports: {', '.join(sorted(SUPPORTED_MEDIA))}")


def build_args(media_path: Path, era: str) -> List[str]:
    """
    Build DOSBox-X command line arguments for given media and era.

    Pure function with no I/O operations.

    Args:
        media_path: Path to media file
        era: Era name ('dos' or 'win31')

    Returns:
        List of command line arguments (excludes executable path)

    Raises:
        ValueError: If era is not in supported set {'dos', 'win31'}
        ValueError: If media suffix is not in supported set {'.iso', '.img', '.cue'}
    """
    # Validate era
    if era not in SUPPORTED_ERAS:
        raise ValueError(f"Era '{era}' not supported by DOSBox-X backend. "
                        f"Supported: {', '.join(sorted(SUPPORTED_ERAS))}")

    # Validate media suffix
    suffix = media_path.suffix.lower()
    if suffix not in SUPPORTED_MEDIA:
        raise ValueError(f"Media suffix '{suffix}' not supported by DOSBox-X backend. "
                        f"Supported: {', '.join(sorted(SUPPORTED_MEDIA))}")

    # Build arguments based on media type
    media_str = str(media_path)

    if suffix == '.img':
        # Mount IMG as hard disk
        return ['-c', f'imgmount C "{media_str}" -t hdd', '-c', 'C:']
    elif suffix in {'.iso', '.cue'}:
        # Mount ISO/CUE as optical disc
        return ['-c', f'imgmount D "{media_str}" -t iso', '-c', 'D:']
    else:
        # This should never be reached due to validation above
        raise ValueError(f"Unhandled media suffix '{suffix}'. This indicates a programming error.")


def launch(media_path: Path, era: str, executable_path: str) -> Tuple[Popen, WindowsJobObject]:
    """
    Launch DOSBox-X with given media file under Job Object isolation.

    Single entry point for DOSBox-X backend. Validates media, builds arguments,
    and launches process under Job Object with network blocking and memory limits.

    Args:
        media_path: Path to media file to mount
        era: Era name ('dos' or 'win31')
        executable_path: Full path to DOSBox-X executable

    Returns:
        Tuple of (subprocess.Popen process, WindowsJobObject instance)
        Caller is responsible for cleanup via job_object.terminate_all()

    Raises:
        FileNotFoundError: If executable_path or media_path does not exist
        ValueError: If era or media extension not supported
        RuntimeError: If Job Object creation or process launch fails
    """
    # Check if DOSBox-X executable exists
    if not os.path.exists(executable_path):
        raise FileNotFoundError(f"DOSBox-X executable not found: {executable_path}")

    # Validate media file
    validate_media(media_path)

    # Build command line arguments
    args = build_args(media_path, era)

    # Generate unique job name
    job_name = f"peach1up_dosbox_{era}_{media_path.stem}"

    # Launch under Job Object isolation
    return launch_under_job_object(
        executable_path=executable_path,
        args=args,
        media_paths=[str(media_path)],
        era=era,
        job_name=job_name
    )