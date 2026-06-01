"""Flycast backend for Peach 1UP.

Handles Dreamcast emulation via Flycast.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Tuple

from backend.constants import ERA_MEDIA_TYPES
from backend.constants_generated import Era
from backend.service.utils.emulator_catalog import (
    get_container_enabled,
    get_container_config as get_emulator_container_config,
    validate_bios_from_descriptor,
)
from backend.service.utils.process.launcher import launch_under_job_object
from backend.service.utils.sandbox_process import SandboxProcess
from backend.service.utils.process.job_objects import WindowsJobObject

if TYPE_CHECKING:
    from backend.service.launch.launch_spec import LaunchSpec

SUPPORTED_ERAS = {Era.DREAMCAST.value}
SUPPORTED_MEDIA = ERA_MEDIA_TYPES[Era.DREAMCAST]


def launch(spec: "LaunchSpec") -> Tuple[SandboxProcess, WindowsJobObject]:
    """Launch Flycast with the given Dreamcast media under Job Object isolation.

    Args:
        spec: LaunchSpec with slug, era, media_path, executable_path set.
            enable_networking is accepted but ignored (no meaningful network
            capability per SECURITY.md).

    Returns:
        Tuple of ``(process, job_object)``.

    Raises:
        FileNotFoundError: If the executable or media path does not exist.
        ValueError: If the era or media format is unsupported.
        FileNotFoundError: If BIOS directory declared in flycast.toml is absent or empty.
    """
    if spec.era not in SUPPORTED_ERAS:
        raise ValueError(
            f"Flycast backend does not support era '{spec.era}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_ERAS))}"
        )

    if not spec.executable_path or not Path(spec.executable_path).exists():
        raise FileNotFoundError(f"Flycast executable not found: {spec.executable_path}")

    validate_bios_from_descriptor("flycast")

    if spec.media_path is None or not spec.media_path.exists():
        raise FileNotFoundError(f"Media file not found: {spec.media_path}")

    if spec.media_path.suffix.lower() not in SUPPORTED_MEDIA:
        raise ValueError(
            f"Unsupported media format '{spec.media_path.suffix}'. "
            f"Flycast supports: {', '.join(sorted(SUPPORTED_MEDIA))}"
        )

    args: list[str] = [str(spec.media_path)]
    job_name = f"peach1up_flycast_{spec.era}_{spec.media_path.stem}"

    return launch_under_job_object(
        executable_path=spec.executable_path,
        args=args,
        era=spec.era,
        job_name=job_name,
        slug="flycast",
        cwd=str(Path(spec.executable_path).parent),
        container_enabled=get_container_enabled("flycast"),
        sandbox_config=get_emulator_container_config("flycast", spec.executable_path),
    )
