"""Flycast backend for Peach 1UP.

Handles Dreamcast emulation via Flycast.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from backend.constants import ERA_MEDIA_TYPES
from backend.constants_generated import Era
from backend.core.logger import get_logger
from backend.service.utils.emulator_catalog import (
    get_container_enabled,
    get_container_config as get_emulator_container_config,
)
from backend.service.utils.process.launcher import launch_under_job_object
from backend.service.utils.sandbox_process import SandboxProcess
from backend.service.utils.process.job_objects import WindowsJobObject

logger = get_logger(__name__)

SUPPORTED_ERAS = {Era.DREAMCAST.value}
SUPPORTED_MEDIA = ERA_MEDIA_TYPES[Era.DREAMCAST]


def validate_bios_path(executable_path: str) -> None:
    """Verify that dc_boot.bin and dc_flash.bin exist in the data/ subdir.

    Raises:
        RuntimeError: If either BIOS file is absent, naming the missing files.
    """
    data_dir = Path(executable_path).parent / "data"
    missing = [
        name for name in ("dc_boot.bin", "dc_flash.bin")
        if not (data_dir / name).exists()
    ]
    if missing:
        raise RuntimeError(
            f"Flycast BIOS files missing from {data_dir}: {', '.join(missing)}. "
            "These files must be dumped from Sega Dreamcast hardware you own."
        )


def launch(
    media_path: Path,
    era: str,
    executable_path: str,
    enable_networking: bool = False,
) -> Tuple[SandboxProcess, WindowsJobObject]:
    """Launch Flycast with the given Dreamcast media under Job Object isolation.

    Args:
        media_path: Path to the disc image (.iso, .cdi, .gdi, .chd).
        era: Era name (must be ``'dreamcast'``).
        executable_path: Full path to the Flycast executable.
        enable_networking: Ignored; reserved for interface symmetry.

    Returns:
        Tuple of ``(process, job_object)``.

    Raises:
        FileNotFoundError: If the executable or media path does not exist.
        ValueError: If the era or media format is unsupported.
        RuntimeError: If BIOS files are missing from the data/ subdirectory.
    """
    if era not in SUPPORTED_ERAS:
        raise ValueError(
            f"Flycast backend does not support era '{era}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_ERAS))}"
        )

    if not Path(executable_path).exists():
        raise FileNotFoundError(f"Flycast executable not found: {executable_path}")

    validate_bios_path(executable_path)

    if not media_path.exists():
        raise FileNotFoundError(f"Media file not found: {media_path}")

    if media_path.suffix.lower() not in SUPPORTED_MEDIA:
        raise ValueError(
            f"Unsupported media format '{media_path.suffix}'. "
            f"Flycast supports: {', '.join(sorted(SUPPORTED_MEDIA))}"
        )

    args: list[str] = [str(media_path)]
    job_name = f"peach1up_flycast_{era}_{media_path.stem}"

    return launch_under_job_object(
        executable_path=executable_path,
        args=args,
        era=era,
        job_name=job_name,
        slug="flycast",
        cwd=str(Path(executable_path).parent),
        container_enabled=get_container_enabled("flycast"),
        sandbox_config=get_emulator_container_config("flycast", executable_path),
    )
