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
from backend.service.utils.ini_writer import set_ini_key
from backend.service.utils.platform.windows.process.launcher import launch_under_job_object
from backend.service.utils.platform.windows.sandbox import BrokerFile
from backend.service.utils.platform.windows.sandbox_process import SandboxProcess
from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject

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

    set_ini_key(
        Path(spec.executable_path).parent / "emu.cfg",
        "config", "Dreamcast.ContentPath", str(spec.media_path.parent),
    )

    args: list[str] = [str(spec.media_path.resolve())]
    job_name_prefix = f"Peach1UP_flycast_{spec.era}_{spec.media_path.stem}"

    catalog_enabled = get_container_enabled("flycast")
    container_enabled = spec.container_enabled if spec.container_enabled is not None else catalog_enabled

    if container_enabled:
        sandbox_config = get_emulator_container_config("flycast", spec.executable_path, user_id=spec.user_id)
        if spec.media_path is not None:
            sandbox_config.broker_files.append(
                BrokerFile(path=str(spec.media_path.parent), access="r", mode="grant"))
            sandbox_config.broker_files.append(
                BrokerFile(path=str(spec.media_path), access="r", mode="inherit"))
    else:
        sandbox_config = None

    return launch_under_job_object(
        executable_path=spec.executable_path,
        args=args,
        era=spec.era,
        job_name_prefix=job_name_prefix,
        slug="flycast",
        cwd=str(Path(spec.executable_path).parent),
        container_enabled=container_enabled,
        sandbox_config=sandbox_config,
    )
