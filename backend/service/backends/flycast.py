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
from backend.service.utils.platform.windows.process.launcher import launch_under_job_object
from backend.service.utils.platform.windows.sandbox import BrokerFile
from backend.service.utils.platform.windows.sandbox_process import SandboxProcess
from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject

if TYPE_CHECKING:
    from backend.service.launch.launch_spec import LaunchSpec

SUPPORTED_ERAS = {Era.DREAMCAST.value}
SUPPORTED_MEDIA = ERA_MEDIA_TYPES[Era.DREAMCAST]


def _write_ini_key(ini_path: Path, section: str, key: str, value: str) -> None:
    """Update a single key in an INI file, preserving all other content exactly."""
    if not ini_path.exists():
        ini_path.parent.mkdir(parents=True, exist_ok=True)
        ini_path.write_text(f"[{section}]\n{key} = {value}\n", encoding="utf-8")
        return
    lines = ini_path.read_text(encoding="utf-8").splitlines(keepends=True)
    in_target = False
    section_found = False
    key_written = False
    insert_before: int | None = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if stripped[1:-1] == section:
                in_target = True
                section_found = True
            elif in_target and not key_written:
                insert_before = i
                in_target = False
            else:
                in_target = False
        elif in_target and "=" in line:
            k = line.split("=", 1)[0].strip()
            if k == key:
                lines[i] = f"{key} = {value}\n"
                key_written = True
                in_target = False
    if not key_written:
        new_line = f"{key} = {value}\n"
        if insert_before is not None:
            lines.insert(insert_before, new_line)
        elif section_found:
            lines.append(new_line)
        else:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(f"\n[{section}]\n{new_line}")
    ini_path.write_text("".join(lines), encoding="utf-8")


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

    _write_ini_key(
        Path(spec.executable_path).parent / "emu.cfg",
        "config", "Dreamcast.ContentPath", str(spec.media_path.parent),
    )

    args: list[str] = [str(spec.media_path.resolve())]
    job_name = f"peach1up_flycast_{spec.era}_{spec.media_path.stem}"

    catalog_enabled = get_container_enabled("flycast")
    container_enabled = spec.container_enabled if spec.container_enabled is not None else catalog_enabled

    if container_enabled:
        sandbox_config = get_emulator_container_config("flycast", spec.executable_path)
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
        job_name=job_name,
        slug="flycast",
        cwd=str(Path(spec.executable_path).parent),
        container_enabled=container_enabled,
        sandbox_config=sandbox_config,
    )
