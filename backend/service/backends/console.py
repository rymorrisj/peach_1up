"""Consolidated console backend for Peach 1UP.

Handles NES (Mesen), N64 (Project64), PS1 (DuckStation), and PS2 (PCSX2)
launches via a single dispatch table keyed by emulator slug.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Tuple

from backend.constants import ERA_MEDIA_TYPES
from backend.constants_generated import Era
from backend.service.utils.emulator_catalog import (
    get_container_enabled,
    get_container_config as get_emulator_container_config,
)
from backend.service.utils.process.launcher import launch_under_job_object
from backend.service.utils.sandbox_process import SandboxProcess
from backend.service.utils.process.job_objects import WindowsJobObject

if TYPE_CHECKING:
    from backend.service.launch.launch_spec import LaunchSpec


@dataclass
class ConsoleBackend:
    slug: str
    supported_eras: frozenset
    supported_media: frozenset
    cli_args_prefix: list
    display_name: str
    media_label: str = "Media file"
    bios_subpath: str | None = None
    bios_label: str | None = None
    hardware_label: str | None = None


_MESEN = ConsoleBackend(
    slug="mesen",
    supported_eras=frozenset({Era.NES.value}),
    supported_media=ERA_MEDIA_TYPES[Era.NES],
    cli_args_prefix=[],
    display_name="Mesen",
    media_label="ROM file",
)

_PROJECT64 = ConsoleBackend(
    slug="project64",
    supported_eras=frozenset({Era.N64.value}),
    supported_media=ERA_MEDIA_TYPES[Era.N64],
    cli_args_prefix=[],
    display_name="Project64",
    media_label="ROM file",
)

_DUCKSTATION = ConsoleBackend(
    slug="duckstation",
    supported_eras=frozenset({Era.PS1.value}),
    supported_media=ERA_MEDIA_TYPES[Era.PS1],
    cli_args_prefix=["-nogui"],
    display_name="DuckStation",
    bios_subpath="userdata/bios",
    bios_label="PS1",
    hardware_label="PlayStation hardware",
)

_PCSX2 = ConsoleBackend(
    slug="pcsx2",
    supported_eras=frozenset({Era.PS2.value}),
    supported_media=ERA_MEDIA_TYPES[Era.PS2],
    cli_args_prefix=["--nogui"],
    display_name="PCSX2",
    bios_subpath="userdata/bios",
    bios_label="PS2",
    hardware_label="PlayStation 2 hardware",
)

_BACKENDS: dict[str, ConsoleBackend] = {
    "mesen":       _MESEN,
    "project64":   _PROJECT64,
    "duckstation": _DUCKSTATION,
    "pcsx2":       _PCSX2,
}


def _validate_media(desc: ConsoleBackend, media_path: Path) -> None:
    if not media_path.exists():
        raise FileNotFoundError(f"{desc.media_label} not found: {media_path}")
    if media_path.suffix.lower() not in desc.supported_media:
        raise ValueError(
            f"Unsupported media format '{media_path.suffix}'. "
            f"{desc.display_name} supports: {', '.join(sorted(desc.supported_media))}"
        )


def _validate_bios_path(desc: ConsoleBackend, bios_path: Path) -> None:
    if not bios_path.exists():
        raise FileNotFoundError(
            f"{desc.bios_label} BIOS directory not found: {bios_path}. "
            f"{desc.bios_label} BIOS files must be dumped from {desc.hardware_label} you own. "
            f"Place your dumped BIOS files in {bios_path}."
        )
    if not bios_path.is_dir():
        raise ValueError(
            f"{desc.bios_label} BIOS path is not a directory: {bios_path}."
        )
    if not any(bios_path.iterdir()):
        raise FileNotFoundError(
            f"{desc.bios_label} BIOS directory is empty: {bios_path}. "
            f"{desc.bios_label} BIOS files must be dumped from {desc.hardware_label} you own. "
            f"Place your dumped BIOS files in {bios_path}."
        )


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
    desc = _BACKENDS.get(spec.slug)
    if desc is None:
        raise ValueError(f"Unknown console backend slug: {spec.slug!r}")

    if not spec.executable_path or not Path(spec.executable_path).exists():
        raise FileNotFoundError(f"{desc.display_name} executable not found: {spec.executable_path}")

    _validate_media(desc, spec.media_path)

    if desc.bios_subpath is not None:
        bios_path = Path(spec.executable_path).parent / desc.bios_subpath
        _validate_bios_path(desc, bios_path)

    args = desc.cli_args_prefix + [str(spec.media_path)]
    job_name = f"peach1up_{spec.slug}_{spec.media_path.stem}"

    return launch_under_job_object(
        executable_path=spec.executable_path,
        args=args,
        era=spec.era,
        job_name=job_name,
        slug=spec.slug,
        container_enabled=get_container_enabled(spec.slug),
        sandbox_config=get_emulator_container_config(spec.slug, spec.executable_path),
    )
