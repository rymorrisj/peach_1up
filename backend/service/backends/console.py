"""Consolidated console backend for Peach 1UP.

Handles NES (Mesen), N64 (Project64), PS1 (DuckStation), and PS2 (PCSX2)
launches via descriptor-driven dispatch. cli_args_prefix, supported_formats,
and BIOS paths are all read from config/emulators/<slug>.toml at runtime.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Tuple

from backend.service.utils.emulator_catalog import (
    get_emulator,
    get_container_enabled,
    get_container_config as get_emulator_container_config,
    validate_bios_from_descriptor,
)
from backend.service.utils.process.launcher import launch_under_job_object
from backend.service.utils.sandbox import BrokerFile
from backend.service.utils.sandbox_process import SandboxProcess
from backend.service.utils.process.job_objects import WindowsJobObject

if TYPE_CHECKING:
    from backend.service.launch.launch_spec import LaunchSpec

_CONSOLE_SLUGS = frozenset({"mesen", "project64", "duckstation", "pcsx2"})


def launch(spec: "LaunchSpec") -> Tuple[SandboxProcess, WindowsJobObject]:
    """Launch a console emulator under Job Object isolation.

    Args:
        spec: LaunchSpec with slug, era, media_path, executable_path set.
            slug must be one of 'mesen', 'project64', 'duckstation', 'pcsx2'.

    Returns:
        Tuple of (SandboxProcess, WindowsJobObject).

    Raises:
        ValueError: If slug is not a known console backend.
        FileNotFoundError: If the executable, media file, or BIOS directory is missing.
        ValueError: If the media extension is unsupported.
        RuntimeError: If process launch fails.
    """
    if spec.slug not in _CONSOLE_SLUGS:
        raise ValueError(f"Unknown console backend slug: {spec.slug!r}")

    entry = get_emulator(spec.slug)
    display_name = entry.get("display_name", spec.slug)
    supported_formats = set(entry.get("supported_formats", []))

    if not spec.executable_path or not Path(spec.executable_path).exists():
        raise FileNotFoundError(f"{display_name} executable not found: {spec.executable_path}")

    if spec.media_path is None or not spec.media_path.exists():
        raise FileNotFoundError(f"Media file not found: {spec.media_path}")
    if spec.media_path.suffix.lower() not in supported_formats:
        raise ValueError(
            f"Unsupported media format '{spec.media_path.suffix}'. "
            f"{display_name} supports: {', '.join(sorted(supported_formats))}"
        )

    validate_bios_from_descriptor(spec.slug)

    cli_args_prefix = entry.get("cli_args_prefix", [])
    args = cli_args_prefix + [str(spec.media_path)]
    job_name = f"peach1up_{spec.slug}_{spec.media_path.stem}"

    catalog_enabled = get_container_enabled(spec.slug)
    container_enabled = spec.container_enabled if spec.container_enabled is not None else catalog_enabled

    if container_enabled:
        sandbox_config = get_emulator_container_config(spec.slug, spec.executable_path)
        if spec.media_path is not None:
            sandbox_config.broker_files.append(
                BrokerFile(path=str(spec.media_path), access="r", mode="grant"))
    else:
        sandbox_config = None

    return launch_under_job_object(
        executable_path=spec.executable_path,
        args=args,
        era=spec.era,
        job_name=job_name,
        slug=spec.slug,
        container_enabled=container_enabled,
        sandbox_config=sandbox_config,
    )
