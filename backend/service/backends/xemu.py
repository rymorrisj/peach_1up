"""xemu backend for Peach 1UP.

Handles original Xbox launches. Validates the binary path, disc image, and
Xbox BIOS directory, then launches xemu under Job Objects with network blocked.

Xbox BIOS files (MCPX ROM and BIOS ROM) must be dumped from original Xbox
hardware the user owns. Peach 1UP does not provide, link to, or assist with
acquiring BIOS files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from backend.constants import ERA_MEDIA_TYPES
from backend.constants_generated import Era
from backend.service.utils.launcher import launch_under_job_object
from backend.service.utils.sandbox_process import SandboxProcess
from backend.service.utils.job_objects import WindowsJobObject
from backend.service.utils.settings import get_env_var

SUPPORTED_ERAS = {Era.XBOX.value}
SUPPORTED_MEDIA = ERA_MEDIA_TYPES[Era.XBOX]


def validate_media(media_path: Path) -> None:
    """Validate that the disc image exists and has a supported extension.

    Args:
        media_path: Path to the Xbox disc image.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file extension is not supported.
    """
    if not media_path.exists():
        raise FileNotFoundError(f"Media file not found: {media_path}")
    if media_path.suffix.lower() not in SUPPORTED_MEDIA:
        raise ValueError(
            f"Unsupported media format '{media_path.suffix}'. "
            f"xemu supports: {', '.join(sorted(SUPPORTED_MEDIA))}"
        )


def validate_bios_path(bios_path: Path) -> None:
    """Validate that the Xbox BIOS directory exists.

    xemu requires an MCPX ROM (mcpx_1.0.bin) and a BIOS ROM. Both must be
    present in the configured directory and xemu must be pre-configured to
    reference them.

    Args:
        bios_path: Path to the directory containing Xbox BIOS files.

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If the path is not a directory.
    """
    if not bios_path.exists():
        raise FileNotFoundError(
            f"Xbox BIOS path not found: {bios_path}. "
            "Xbox BIOS files (MCPX ROM and BIOS ROM) must be dumped from "
            "original Xbox hardware you own. "
            "Configure XBOX_BIOS_PATH in config/settings.yaml to the directory "
            "containing your dumped BIOS files, then configure xemu to use them."
        )
    if not bios_path.is_dir():
        raise ValueError(
            f"Xbox BIOS path is not a directory: {bios_path}. "
            "XBOX_BIOS_PATH must point to a directory containing your dumped BIOS files."
        )


def build_args(media_path: Path) -> list[str]:
    """Build xemu command line arguments for the given disc image.

    Args:
        media_path: Path to the Xbox ISO disc image.

    Returns:
        List of command line arguments (excludes the executable path).
    """
    return ["-dvd_path", str(media_path)]


def launch(media_path: Path, era: str, executable_path: str) -> Tuple[SandboxProcess, WindowsJobObject]:
    """Launch xemu with the given Xbox disc image under Job Object isolation.

    Args:
        media_path: Path to the Xbox disc image to mount.
        era: Era string — must be 'xbox'.
        executable_path: Full path to the xemu executable.

    Returns:
        Tuple of (subprocess.Popen process, WindowsJobObject instance).
        Caller is responsible for cleanup via job_object.terminate_all().

    Raises:
        FileNotFoundError: If the executable, media file, or BIOS path is missing.
        ValueError: If the media extension is unsupported.
        RuntimeError: If XBOX_BIOS_PATH is not configured or process launch fails.
    """
    if not Path(executable_path).exists():
        raise FileNotFoundError(f"xemu executable not found: {executable_path}")

    validate_media(media_path)

    bios_path_str = get_env_var("XBOX_BIOS_PATH")
    if not bios_path_str:
        raise RuntimeError(
            "XBOX_BIOS_PATH is not configured. "
            "Set it in config/settings.yaml to the directory containing your Xbox BIOS files. "
            "Xbox BIOS files must be dumped from original Xbox hardware you own."
        )
    validate_bios_path(Path(bios_path_str))

    args = build_args(media_path)
    job_name = f"peach1up_xemu_{media_path.stem}"

    return launch_under_job_object(
        executable_path=executable_path,
        args=args,
        media_paths=[str(media_path)],
        era=era,
        job_name=job_name,
    )
