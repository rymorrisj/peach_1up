"""xemu backend for Peach 1UP.

Handles original Xbox launches. Validates the binary path, disc image, and
Xbox BIOS directory, then launches xemu under Job Objects with network blocked.

Xbox BIOS files (MCPX ROM and BIOS ROM) must be dumped from original Xbox
hardware the user owns. Peach 1UP does not provide, link to, or assist with
acquiring BIOS files.
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Tuple

from backend.constants import ERA_MEDIA_TYPES
from backend.constants_generated import Era
from backend.service.utils.emulator_catalog import get_container_enabled
from backend.service.utils.xbox_image import detect_xbox_image_type
from backend.service.utils.platform.windows.process.launcher import launch_under_job_object
from backend.service.utils.platform.windows.sandbox import BrokerFile
from backend.service.utils.platform.windows.sandbox_process import SandboxProcess
from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject
from backend.core.logger import get_logger
from backend.core.settings import get_base_path
from backend.service.utils.emulator_catalog import get_install_path

logger = get_logger(__name__)

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


def _clear_dvd_path_on_exit(proc, toml_path: Path) -> None:
    try:
        while proc.poll() is None:
            time.sleep(0.5)
    except Exception:
        pass
    try:
        text = toml_path.read_text(encoding="utf-8")
        cleared = re.sub(
            r'^(dvd_path\s*=\s*)"[^"]*"',
            r'\1""',
            text,
            flags=re.MULTILINE,
        )
        toml_path.write_text(cleared, encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to clear dvd_path in xemu.toml after exit: %s", exc)


def provision_xemu_defaults(exe_path: Path, vm_dir: Path, dvd_path: str | None = None) -> Path:
    """Write (or overwrite) the per-VM xemu.toml; return its path.

    Always overwrites any existing xemu.toml so stale configs from previous broken
    runs are corrected on every launch. Uses an atomic rename so a failed write
    never leaves a partial config on disk.

    # xemu.toml is written per-VM (emulators/xemu/vms/<profile_id>/xemu.toml) rather
    # than shared alongside the executable. A shared path causes a race when two
    # profiles launch xemu concurrently — the second write corrupts the first's config
    # mid-start. The same class of bug was fixed for DOSBox-X in PX-2-8.

    BIOS files (mcpx_1.0.bin, flash *.bin, eeprom.bin) and xbox_hdd.qcow2 must
    all reside in the same directory as the xemu executable. Peach 1UP does not
    provide, link to, or assist with acquiring these files.

    Args:
        exe_path: Absolute path to the xemu executable (xemu.exe).
        vm_dir: Per-profile directory where xemu.toml will be written.
            Typically emulators/xemu/vms/<profile_id>/. Created if absent.

    Returns:
        Path to the xemu.toml config file inside vm_dir.

    Raises:
        FileNotFoundError: If the MCPX ROM, flash BIOS, or xbox_hdd.qcow2 are absent.
    """
    import os

    exe_dir = exe_path.parent
    vm_dir.mkdir(parents=True, exist_ok=True)
    hdd_path = exe_dir / "xbox_hdd.qcow2"
    toml_path = vm_dir / "xemu.toml"
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
        "[sys.files]\n"
        f'bootrom_path = "{mcpx.resolve().as_posix()}"\n'
        f'flashrom_path = "{flash_bins[0].resolve().as_posix()}"\n'
        f'eeprom_path = "{eeprom_path.resolve().as_posix()}"\n'
        f'hdd_path = "{hdd_path.resolve().as_posix()}"\n'
        f'dvd_path = "{dvd_path or ""}"\n'
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

    files = config.get("sys", {}).get("files", {})

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


def launch(spec: "LaunchSpec") -> Tuple[SandboxProcess, WindowsJobObject]:
    """Launch xemu with the given Xbox disc image under Job Object isolation.

    Provisions a per-profile xemu.toml (emulators/xemu/vms/<profile_id>/xemu.toml)
    on every launch. No Platform record is required — xemu behaves like all
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
    _xemu_install = get_install_path("xemu")
    executable_path = str(_xemu_install) if _xemu_install and _xemu_install.is_file() else ""
    if not executable_path:
        raise RuntimeError(
            "xemu executable not found. Install it via the Emulators page."
        )
    if not Path(executable_path).exists():
        raise FileNotFoundError(f"xemu executable not found: {executable_path}")

    if spec.media_path is not None:
        validate_media(spec.media_path)
        image_type = detect_xbox_image_type(spec.media_path)
        if image_type != "xiso":
            if image_type == "dvd_rip":
                raise ValueError(
                    "This disc image appears to be a raw Xbox DVD rip (7–8 GB with a video partition). "
                    "xemu requires xiso format. Use extract-xiso to convert it: "
                    "https://github.com/xboxdev/extract-xiso"
                )
            elif image_type == "iso9660":
                raise ValueError(
                    "This disc image is a standard ISO 9660 image, not an Xbox disc image. "
                    "Verify you have the correct file."
                )
            else:
                raise ValueError(
                    "This disc image could not be identified as an Xbox disc image (xiso format). "
                    "xemu requires xiso format. Use extract-xiso to convert it: "
                    "https://github.com/xboxdev/extract-xiso"
                )

    dvd_posix = spec.media_path.resolve().as_posix() if spec.media_path is not None else None

    vm_dir = Path(executable_path).parent
    logger.debug("xemu.launch: dvd_posix=%s vm_dir=%s", dvd_posix, vm_dir)
    config_path = provision_xemu_defaults(Path(executable_path), vm_dir, dvd_path=dvd_posix)
    validate_bios_path(config_path)

    args = ["-dvd_path", dvd_posix] if dvd_posix else []

    job_name = f"peach1up_xemu_{spec.era}_shared"

    catalog_enabled = get_container_enabled("xemu")
    container_enabled = spec.container_enabled if spec.container_enabled is not None else catalog_enabled

    if container_enabled:
        from backend.service.utils.platform.windows.app_container import (
            get_container_config as _build_sandbox_cfg,
        )
        hdd_path = Path(executable_path).parent / "xbox_hdd.qcow2"
        sandbox_config = _build_sandbox_cfg(
            "xemu",
            executable_path,
            launch_paths={"hdd_image": str(hdd_path)},
        )
        if spec.media_path is not None:
            sandbox_config.broker_files.append(
                BrokerFile(path=str(spec.media_path.parent), access="r", mode="grant"))
            sandbox_config.broker_files.append(
                BrokerFile(path=str(spec.media_path), access="r", mode="inherit"))
        logger.debug(
            "xemu.launch: broker_files=[%s]",
            ", ".join(
                f"{bf.mode}:{bf.access}:{bf.path}" for bf in sandbox_config.broker_files
            ),
        )
    else:
        sandbox_config = None

    logger.debug(
        "xemu.launch: args=%s config_path=%s",
        args, config_path,
    )
    result = launch_under_job_object(
        executable_path=executable_path,
        args=args,
        era=spec.era,
        job_name=job_name,
        slug="xemu",
        cwd=str(vm_dir),
        container_enabled=container_enabled,
        sandbox_config=sandbox_config,
    )

    if dvd_posix:
        threading.Thread(
            target=_clear_dvd_path_on_exit,
            args=(result[0], config_path),
            daemon=True,
            name=f"xemu_dvd_cleanup_{result[0].pid}",
        ).start()

    return result
