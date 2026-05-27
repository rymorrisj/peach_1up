"""PCSX2 backend for Peach 1UP.

Handles PlayStation 2 launches. Validates the binary path, media file, and
PS2 BIOS directory, then launches PCSX2 under Job Objects with network blocked.

BIOS files must be dumped from PlayStation 2 hardware the user owns. Peach 1UP
does not provide, link to, or assist with acquiring BIOS files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from backend.constants import ERA_MEDIA_TYPES
from backend.constants_generated import Era
from backend.service.utils.emulator_catalog import (
    get_container_enabled,
    get_container_config as get_emulator_container_config,
)
from backend.service.utils.launcher import launch_under_job_object
from backend.service.utils.sandbox_process import SandboxProcess
from backend.service.utils.job_objects import WindowsJobObject
from backend.service.utils.settings import get_env_var

SUPPORTED_ERAS = {Era.PS2.value}
SUPPORTED_MEDIA = ERA_MEDIA_TYPES[Era.PS2]


def validate_media(media_path: Path) -> None:
    """Validate that the media file exists and has a supported extension.

    Args:
        media_path: Path to the media file.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file extension is not supported.
    """
    if not media_path.exists():
        raise FileNotFoundError(f"Media file not found: {media_path}")
    if media_path.suffix.lower() not in SUPPORTED_MEDIA:
        raise ValueError(
            f"Unsupported media format '{media_path.suffix}'. "
            f"PCSX2 supports: {', '.join(sorted(SUPPORTED_MEDIA))}"
        )


def validate_bios_path(bios_path: Path) -> None:
    """Validate that the PS2 BIOS directory exists.

    Args:
        bios_path: Path to the directory containing PS2 BIOS files.

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If the path is not a directory.
    """
    if not bios_path.exists():
        raise FileNotFoundError(
            f"PS2 BIOS path not found: {bios_path}. "
            "PS2 BIOS files must be dumped from PlayStation 2 hardware you own. "
            "Configure PS2_BIOS_PATH in config/settings.yaml to the directory "
            "containing your dumped BIOS files, then configure PCSX2 to use "
            "the same directory."
        )
    if not bios_path.is_dir():
        raise ValueError(
            f"PS2 BIOS path is not a directory: {bios_path}. "
            "PS2_BIOS_PATH must point to a directory containing your dumped BIOS files."
        )


def build_args(media_path: Path) -> list[str]:
    """Build PCSX2 command line arguments for the given media file.

    Args:
        media_path: Path to the PS2 disc image.

    Returns:
        List of command line arguments (excludes the executable path).
    """
    return ["--nogui", str(media_path)]


def launch(media_path: Path, era: str, executable_path: str) -> Tuple[SandboxProcess, WindowsJobObject]:
    """Launch PCSX2 with the given PS2 media under Job Object isolation.

    Args:
        media_path: Path to the PS2 disc image to mount.
        era: Era string — must be 'ps2'.
        executable_path: Full path to the PCSX2 executable.

    Returns:
        Tuple of (subprocess.Popen process, WindowsJobObject instance).
        Caller is responsible for cleanup via job_object.teardown().

    Raises:
        FileNotFoundError: If the executable, media file, or BIOS path is missing.
        ValueError: If the media extension is unsupported.
        RuntimeError: If PS2_BIOS_PATH is not configured or process launch fails.
    """
    if not Path(executable_path).exists():
        raise FileNotFoundError(f"PCSX2 executable not found: {executable_path}")

    validate_media(media_path)

    bios_path_str = get_env_var("PS2_BIOS_PATH")
    if not bios_path_str:
        raise RuntimeError(
            "PS2_BIOS_PATH is not configured. "
            "Set it in config/settings.yaml to the directory containing your PS2 BIOS files. "
            "PS2 BIOS files must be dumped from PlayStation 2 hardware you own."
        )
    validate_bios_path(Path(bios_path_str))

    args = build_args(media_path)
    job_name = f"peach1up_pcsx2_{media_path.stem}"

    return launch_under_job_object(
        executable_path=executable_path,
        args=args,
        era=era,
        job_name=job_name,
        slug="pcsx2",
        container_enabled=get_container_enabled("pcsx2"),
        sandbox_config=get_emulator_container_config("pcsx2", executable_path),
    )
