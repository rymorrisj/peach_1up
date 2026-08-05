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
    resolve_container_enabled,
    build_media_broker_config,
    validate_bios_from_descriptor,
)
from backend.service.utils.file_types import supported_extensions_for_era
from backend.core.logger import get_logger
from backend.service.utils.ini_writer import set_ini_key
from backend.service.utils.platform.windows.process.launcher import launch_under_job_object
from backend.service.utils.platform.windows.sandbox_process import SandboxProcess
from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject

logger = get_logger(__name__)

if TYPE_CHECKING:
    from backend.service.launch.launch_spec import LaunchSpec

_CONSOLE_SLUGS = frozenset({"mesen", "project64", "duckstation", "pcsx2"})


def launch(spec: "LaunchSpec") -> Tuple[SandboxProcess, WindowsJobObject]:
    """Launch a console emulator under Job Object isolation.

    Args:
        spec: LaunchSpec with slug, era, media_path, executable_path set.
            slug must be one of 'mesen', 'project64', 'duckstation', 'pcsx2'.
            enable_networking is honored per-emulator, not universally: PCSX2
            emulates the PS2 DEV9/SMAP Ethernet adapter, so when networking is
            off its [DEV9/Eth] EthEnable key is forced false. Mesen (NES),
            Project64 (N64), and DuckStation (PS1) emulate consoles with no
            network hardware — there is nothing to disable, so enable_networking
            is intentionally ignored for those three.

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
    # eras.yaml is the single enforced source for launch-time format
    # validation (matches dosbox.py/flycast.py/xemu.py's pattern), not the
    # TOML descriptor's own supported_formats field, which stays display-only
    # (surfaced by GET /emulators) and is now cross-checked against eras.yaml
    # at startup by EmulatorDescriptor's validator instead of trusted here.
    # Mesen alone serves two eras (nes, snes, see mesen.toml's supported_eras);
    # every other console slug serves exactly one, so unioning
    # supported_eras-or-[era] here is correct for all four without a
    # slug-specific branch.
    _formats_eras = entry.get("supported_eras") or [entry.get("era")]
    supported_formats: set[str] = set()
    for _era in _formats_eras:
        if _era:
            supported_formats.update(supported_extensions_for_era(_era))

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
        set_ini_key(
            Path(spec.executable_path).parent / "settings.ini",
            "GameList", "RecursivePaths", str(spec.media_path.parent),
        )
    elif spec.slug == "pcsx2":
        pcsx2_ini = Path(spec.executable_path).parent / "inis" / "PCSX2.ini"
        set_ini_key(pcsx2_ini, "GameList", "RecursivePaths", str(spec.media_path.parent))
        if not spec.enable_networking:
            # PS2 DEV9/SMAP Ethernet: disable the network adapter unless the
            # profile explicitly opts in. Section is [DEV9/Eth], key EthEnable.
            set_ini_key(pcsx2_ini, "DEV9/Eth", "EthEnable", "false")

    cli_args_prefix = entry.get("cli_args_prefix", [])
    if spec.slug in {"duckstation", "pcsx2"}:
        args = cli_args_prefix + ["--", str(spec.media_path)]
    else:
        args = cli_args_prefix + [str(spec.media_path)]
    job_name_prefix = f"Peach1UP_{spec.slug}_{spec.media_path.stem}"

    container_enabled = resolve_container_enabled(spec.slug, spec.container_enabled)
    sandbox_config = build_media_broker_config(
        spec.slug, spec.executable_path, spec.media_path, spec.user_item_id, container_enabled)

    logger.debug("console.launch: slug=%s args=%s", spec.slug, args)
    cwd = str(Path(spec.executable_path).parent) if spec.slug == "project64" else None
    return launch_under_job_object(
        executable_path=spec.executable_path,
        args=args,
        era=spec.era,
        job_name_prefix=job_name_prefix,
        slug=spec.slug,
        cwd=cwd,
        container_enabled=container_enabled,
        sandbox_config=sandbox_config,
    )
