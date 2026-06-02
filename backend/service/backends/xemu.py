"""xemu backend for Peach 1UP.

Handles original Xbox launches. Validates the binary path, disc image, and
Xbox BIOS directory, then launches xemu under Job Objects with network blocked.

Xbox BIOS files (MCPX ROM and BIOS ROM) must be dumped from original Xbox
hardware the user owns. Peach 1UP does not provide, link to, or assist with
acquiring BIOS files.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional, Tuple

from backend.constants import ERA_MEDIA_TYPES
from backend.constants_generated import Era
from backend.service.utils.emulator_catalog import (
    get_container_enabled,
    get_container_config as get_emulator_container_config,
)
from backend.service.utils.process.launcher import launch_under_job_object
from backend.service.utils.sandbox_process import SandboxProcess
from backend.service.utils.process.job_objects import WindowsJobObject
from backend.core.settings import get_base_path
from backend.service.utils.settings import get_binary_path

if TYPE_CHECKING:
    from backend.service.launch.launch_spec import LaunchSpec

SUPPORTED_ERAS = {Era.XBOX.value}
SUPPORTED_MEDIA = ERA_MEDIA_TYPES[Era.XBOX]


def validate_media(media_path: Path) -> None:
    """Validate that the disc image exists and has a supported extension.

    Args:
        media_path: Path to the Xbox disc image.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file extension is not supported.
    """
    if not media_path.exists():
        raise FileNotFoundError(f"Media file not found: {media_path}")
    if media_path.suffix.lower() not in SUPPORTED_MEDIA:
        raise ValueError(
            f"Unsupported media format '{media_path.suffix}'. "
            f"xemu supports: {', '.join(sorted(SUPPORTED_MEDIA))}"
        )


def provision_xemu_defaults(exe_path: Path) -> Path:
    """Write (or overwrite) the xemu.toml alongside the executable; return its path.

    Always overwrites any existing xemu.toml so stale configs from previous broken
    runs are corrected on every launch. Uses an atomic rename so a failed write
    never leaves a partial config on disk.

    BIOS files (mcpx_1.0.bin, flash *.bin, eeprom.bin) and xbox_hdd.qcow2 must
    all reside in the same directory as the xemu executable. Peach 1UP does not
    provide, link to, or assist with acquiring these files.

    Args:
        exe_path: Absolute path to the xemu executable (xemu.exe).

    Returns:
        Path to the xemu.toml config file alongside the executable.

    Raises:
        FileNotFoundError: If the MCPX ROM, flash BIOS, or xbox_hdd.qcow2 are absent.
    """
    import os

    exe_dir = exe_path.parent
    hdd_path = exe_dir / "xbox_hdd.qcow2"
    toml_path = exe_dir / "xemu.toml"
    eeprom_path = exe_dir / "eeprom.bin"

    if not hdd_path.exists():
        raise FileNotFoundError(
            f"Xbox HDD image not found: {hdd_path}. "
            "xemu requires a properly formatted 8 GB qcow2 image named xbox_hdd.qcow2 "
            f"placed in {exe_dir}. "
            "See https://xemu.app/docs/required-files/ for instructions on obtaining "
            "or creating this image from your own Xbox hardware."
        )

    mcpx = exe_dir / "mcpx_1.0.bin"
    if not mcpx.exists():
        raise FileNotFoundError(
            f"MCPX boot ROM not found: {mcpx}. "
            "Place mcpx_1.0.bin in emulators/xemu/ before launching."
        )

    flash_bins = [
        f for f in sorted(exe_dir.glob("*.bin"))
        if f.name.lower() not in ("mcpx_1.0.bin", "eeprom.bin")
    ]
    if not flash_bins:
        raise FileNotFoundError(
            f"Flash BIOS not found in {exe_dir}. "
            "Place your Xbox flash BIOS .bin file in emulators/xemu/ before launching."
        )

    content = (
        "[general]\n"
        "show_welcome = false\n\n"
        "[system]\n"
        "memory_mib = 64\n\n"
        "[system.files]\n"
        f'bootrom_path = "{mcpx.resolve().as_posix()}"\n'
        f'flashrom_path = "{flash_bins[0].resolve().as_posix()}"\n'
        f'eeprom_path = "{eeprom_path.resolve().as_posix()}"\n'
        f'hdd_path = "{hdd_path.resolve().as_posix()}"\n'
    )

    tmp = toml_path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, toml_path)

    return toml_path


def validate_bios_path(config_path: Path) -> None:
    """Validate that the asset files declared in the per-VM xemu.toml exist on disk.

    Reads bootrom_path, flashrom_path, and hdd_path from the per-VM config and verifies
    each file is present. Paths may be absolute or relative to the project root.

    Args:
        config_path: Path to the per-VM xemu.toml (emulators/xemu/vms/{slug}/xemu.toml).

    Raises:
        RuntimeError: If the per-VM toml is absent, a key is unset, or a file is absent.
    """
    import tomllib

    if not config_path.exists():
        raise RuntimeError(
            f"xemu per-VM config not found: {config_path}. "
            "Register the Xbox platform before launching."
        )

    with config_path.open("rb") as fh:
        config = tomllib.load(fh)

    files = config.get("system", {}).get("files", {})

    checks = [
        ("bootrom_path", files.get("bootrom_path", "")),
        ("flashrom_path", files.get("flashrom_path", "")),
        ("hdd_path", files.get("hdd_path", "")),
    ]

    base = get_base_path()
    missing: list[str] = []
    for key, raw in checks:
        if not raw:
            raise RuntimeError(
                f"xemu config key '{key}' is not set in {config_path}. "
                "Re-register the Xbox platform or update the config manually."
            )
        resolved = Path(raw) if Path(raw).is_absolute() else base / raw
        if not resolved.exists():
            missing.append(f"  {key}: {resolved}")

    if missing:
        lines = "\n".join(missing)
        raise RuntimeError(
            f"xemu asset files not found:\n{lines}\n"
            f"Update these paths in {config_path}."
        )


def build_args(media_path: Path) -> list[str]:
    """Build xemu command line arguments for the given disc image.

    Args:
        media_path: Path to the Xbox ISO disc image.

    Returns:
        List of command line arguments (excludes the executable path).
    """
    return ["-dvd_path", str(media_path)]


def launch(spec: "LaunchSpec") -> Tuple[SandboxProcess, WindowsJobObject]:
    """Launch xemu with the given Xbox disc image under Job Object isolation.

    Provisions the shared xemu config (emulators/xemu/xemu.toml) on first
    launch if absent. No Platform record is required — xemu behaves like all
    other console backends (DuckStation, PCSX2, Mesen, Project64).

    Args:
        spec: LaunchSpec with era set. media_path is optional — omit to boot
            with no disc. enable_networking is accepted but ignored (no
            meaningful network capability per SECURITY.md).

    Returns:
        Tuple of (SandboxProcess, WindowsJobObject instance).
        Caller is responsible for cleanup via job_object.teardown().

    Raises:
        FileNotFoundError: If the executable, BIOS files, or xbox_hdd.qcow2
            are missing.
        ValueError: If the media extension is unsupported.
        RuntimeError: If XEMU_PATH is not configured or launch fails.
    """
    executable_path = get_binary_path("xemu")
    if not executable_path:
        raise RuntimeError(
            "xemu binary path is not configured. "
            "Set XEMU_PATH in config/settings.yaml or via the Settings page."
        )
    if not Path(executable_path).exists():
        raise FileNotFoundError(f"xemu executable not found: {executable_path}")

    if spec.media_path is not None:
        validate_media(spec.media_path)

    config_path = provision_xemu_defaults(Path(executable_path))
    validate_bios_path(config_path)

    vm_dir = config_path.parent

    args = ["-config_path", str(config_path)]
    if spec.media_path is not None:
        args += build_args(spec.media_path)

    job_name = f"peach1up_xemu_{spec.era}_shared"

    return launch_under_job_object(
        executable_path=executable_path,
        args=args,
        era=spec.era,
        job_name=job_name,
        slug="xemu",
        cwd=str(vm_dir),
        container_enabled=get_container_enabled("xemu"),
        sandbox_config=get_emulator_container_config("xemu", executable_path),
    )
