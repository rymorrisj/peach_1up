"""Consolidated console backend for Peach 1UP.

Handles NES (Mesen), N64 (Project64), PS1 (DuckStation), and PS2 (PCSX2)
launches via a single dispatch table keyed by emulator slug.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

from backend.constants import ERA_MEDIA_TYPES
from backend.constants_generated import Era
from backend.service.utils.emulator_catalog import (
    get_container_enabled,
    get_container_config as get_emulator_container_config,
)
from backend.service.utils.process.launcher import launch_under_job_object
from backend.service.utils.sandbox_process import SandboxProcess
from backend.service.utils.process.job_objects import WindowsJobObject
from backend.service.utils.settings import get_env_var


@dataclass
class ConsoleBackend:
    slug: str
    supported_eras: frozenset
    supported_media: frozenset
    cli_args_prefix: list
    display_name: str
    media_label: str = "Media file"
    bios_env_var: str | None = None
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
    bios_env_var="PS1_BIOS_PATH",
    bios_label="PS1",
    hardware_label="PlayStation hardware",
)

_PCSX2 = ConsoleBackend(
    slug="pcsx2",
    supported_eras=frozenset({Era.PS2.value}),
    supported_media=ERA_MEDIA_TYPES[Era.PS2],
    cli_args_prefix=["--nogui"],
    display_name="PCSX2",
    bios_env_var="PS2_BIOS_PATH",
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
            f"{desc.bios_label} BIOS path not found: {bios_path}. "
            f"{desc.bios_label} BIOS files must be dumped from {desc.hardware_label} you own. "
            f"Configure {desc.bios_env_var} in config/settings.yaml to the directory "
            f"containing your dumped BIOS files, then configure {desc.display_name} to "
            "use the same directory."
        )
    if not bios_path.is_dir():
        raise ValueError(
            f"{desc.bios_label} BIOS path is not a directory: {bios_path}. "
            f"{desc.bios_env_var} must point to a directory containing your dumped BIOS files."
        )
    if not any(bios_path.iterdir()):
        raise FileNotFoundError(
            f"{desc.bios_label} BIOS directory is empty: {bios_path}. "
            f"{desc.bios_label} BIOS files must be dumped from {desc.hardware_label} you own. "
            f"Place your dumped BIOS files in the directory configured as {desc.bios_env_var}."
        )


def launch(slug: str, media_path: Path, era: str, executable_path: str) -> Tuple[SandboxProcess, WindowsJobObject]:
    """Launch a console emulator by slug under Job Object isolation.

    Args:
        slug: Emulator slug — one of 'mesen', 'project64', 'duckstation', 'pcsx2'.
        media_path: Path to the ROM or disc image.
        era: Era string matching the slug's supported era.
        executable_path: Full path to the emulator executable.

    Returns:
        Tuple of (SandboxProcess, WindowsJobObject).

    Raises:
        ValueError: If slug is not a known console backend.
        FileNotFoundError: If the executable, media file, or BIOS path is missing.
        ValueError: If the media extension is unsupported.
        RuntimeError: If a required BIOS path env var is not configured or process launch fails.
    """
    desc = _BACKENDS.get(slug)
    if desc is None:
        raise ValueError(f"Unknown console backend slug: {slug!r}")

    if not Path(executable_path).exists():
        raise FileNotFoundError(f"{desc.display_name} executable not found: {executable_path}")

    _validate_media(desc, media_path)

    if desc.bios_env_var is not None:
        bios_path_str = get_env_var(desc.bios_env_var)
        if not bios_path_str:
            raise RuntimeError(
                f"{desc.bios_env_var} is not configured. "
                f"Set it in config/settings.yaml to the directory containing your {desc.bios_label} BIOS files. "
                f"{desc.bios_label} BIOS files must be dumped from {desc.hardware_label} you own."
            )
        _validate_bios_path(desc, Path(bios_path_str))

    args = desc.cli_args_prefix + [str(media_path)]
    job_name = f"peach1up_{slug}_{media_path.stem}"

    return launch_under_job_object(
        executable_path=executable_path,
        args=args,
        era=era,
        job_name=job_name,
        slug=slug,
        container_enabled=get_container_enabled(slug),
        sandbox_config=get_emulator_container_config(slug, executable_path),
    )
