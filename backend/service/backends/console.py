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
from backend.core.logger import get_logger
from backend.service.utils.platform.windows.process.launcher import launch_under_job_object
from backend.service.utils.platform.windows.sandbox import BrokerFile
from backend.service.utils.platform.windows.sandbox_process import SandboxProcess
from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject

logger = get_logger(__name__)

if TYPE_CHECKING:
    from backend.service.launch.launch_spec import LaunchSpec

_CONSOLE_SLUGS = frozenset({"mesen", "project64", "duckstation", "pcsx2"})


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

    if spec.slug == "duckstation":
        _write_ini_key(
            Path(spec.executable_path).parent / "settings.ini",
            "GameList", "RecursivePaths", str(spec.media_path.parent),
        )
    elif spec.slug == "pcsx2":
        _write_ini_key(
            Path(spec.executable_path).parent / "inis" / "PCSX2.ini",
            "GameList", "RecursivePaths", str(spec.media_path.parent),
        )

    cli_args_prefix = entry.get("cli_args_prefix", [])
    if spec.slug in {"duckstation", "pcsx2"}:
        args = cli_args_prefix + ["--", str(spec.media_path)]
    else:
        args = cli_args_prefix + [str(spec.media_path)]
    job_name = f"peach1up_{spec.slug}_{spec.media_path.stem}"

    catalog_enabled = get_container_enabled(spec.slug)
    container_enabled = spec.container_enabled if spec.container_enabled is not None else catalog_enabled

    if container_enabled:
        sandbox_config = get_emulator_container_config(spec.slug, spec.executable_path)
        if spec.media_path is not None:
            sandbox_config.broker_files.append(
                BrokerFile(path=str(spec.media_path.parent), access="r", mode="grant"))
            sandbox_config.broker_files.append(
                BrokerFile(path=str(spec.media_path), access="r", mode="inherit"))
    else:
        sandbox_config = None

    logger.debug("console.launch: slug=%s args=%s", spec.slug, args)
    cwd = str(Path(spec.executable_path).parent) if spec.slug == "project64" else None
    return launch_under_job_object(
        executable_path=spec.executable_path,
        args=args,
        era=spec.era,
        job_name=job_name,
        slug=spec.slug,
        cwd=cwd,
        container_enabled=container_enabled,
        sandbox_config=sandbox_config,
    )
