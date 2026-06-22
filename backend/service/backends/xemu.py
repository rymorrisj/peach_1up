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
from backend.service.utils.emulator_catalog import (
    get_container_enabled,
    get_install_path,
    validate_bios_from_descriptor,
)
from backend.service.utils.xbox_image import detect_xbox_image_type
from backend.service.utils.platform.windows.process.launcher import launch_under_job_object
from backend.service.utils.platform.windows.sandbox import BrokerFile
from backend.service.utils.platform.windows.sandbox_process import SandboxProcess
from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject
from backend.core.logger import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from backend.service.launch.launch_spec import LaunchSpec

SUPPORTED_ERAS = {Era.XBOX.value}
SUPPORTED_MEDIA = ERA_MEDIA_TYPES[Era.XBOX]

# Portable-mode data root, next to the binary — matches Flycast's data/ convention.
DATA_DIR_NAME = "data"
# Single config shipped today. Named subdirectories under data/ are reserved
# for future per-game BIOS/HDD overrides (see resolve_launch_config).
DEFAULT_CONFIG_NAME = "default"


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


def resolve_launch_config() -> str:
    """Resolve which named BIOS/HDD config under data/ applies to this launch.

    Single responsibility: selection only — it does not read or validate any
    files itself. Returns the config name (a subdirectory of data/), which
    callers combine with the data root to get an actual directory.

    Stub: xemu has no per-game override selection mechanism yet, so this
    always returns DEFAULT_CONFIG_NAME. No parameters are taken because no
    selection input has been designed — add them when that mechanism exists.

    Returns:
        The config name to use, e.g. "default".
    """
    return DEFAULT_CONFIG_NAME


def provision_xemu_defaults(exe_path: Path, data_dir: Path, dvd_path: str | None = None) -> Path:
    """Write (or overwrite) the xemu.toml portable-mode sentinel; return its path.

    xemu detects xemu.toml next to its own binary on startup and treats that
    directory as its data root (see EMULATORS.md) — so the sentinel is always
    written to exe_path.parent, never into data_dir. Always overwrites any
    existing xemu.toml so stale configs from previous broken runs are
    corrected on every launch. Uses an atomic rename so a failed write never
    leaves a partial config on disk.

    BIOS files (mcpx_1.0.bin, flash *.bin, eeprom.bin) and xbox_hdd.qcow2 are
    read from data_dir — the config directory resolved by
    resolve_launch_config() (e.g. emulators/xemu/data/default/) — not from
    the executable's directory. Peach 1UP does not provide, link to, or
    assist with acquiring these files.

    Args:
        exe_path: Absolute path to the xemu executable (xemu.exe).
        data_dir: Resolved config directory holding the BIOS/HDD asset files
            for this launch.

    Returns:
        Path to the xemu.toml sentinel file inside exe_path.parent.

    Raises:
        FileNotFoundError: If the MCPX ROM, flash BIOS, or xbox_hdd.qcow2 are
            absent from data_dir.
    """
    import os

    exe_dir = exe_path.parent
    toml_path = exe_dir / "xemu.toml"
    hdd_path = data_dir / "xbox_hdd.qcow2"
    eeprom_path = data_dir / "eeprom.bin"

    if not hdd_path.exists():
        raise FileNotFoundError(
            f"Xbox HDD image not found: {hdd_path}. "
            "xemu requires a properly formatted 8 GB qcow2 image named xbox_hdd.qcow2 "
            f"placed in {data_dir}. "
            "See https://xemu.app/docs/required-files/ for instructions on obtaining "
            "or creating this image from your own Xbox hardware."
        )

    mcpx = data_dir / "mcpx_1.0.bin"
    if not mcpx.exists():
        raise FileNotFoundError(
            f"MCPX boot ROM not found: {mcpx}. "
            f"Place mcpx_1.0.bin in {data_dir} before launching."
        )

    flash_bins = [
        f for f in sorted(data_dir.glob("*.bin"))
        if f.name.lower() not in ("mcpx_1.0.bin", "eeprom.bin")
    ]
    if not flash_bins:
        raise FileNotFoundError(
            f"Flash BIOS not found in {data_dir}. "
            f"Place your Xbox flash BIOS .bin file in {data_dir} before launching."
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


def validate_bios_path(data_dir: Path) -> None:
    """Validate that the BIOS/HDD asset files for the resolved config exist on disk.

    Checks for mcpx_1.0.bin, a flash BIOS *.bin file, and xbox_hdd.qcow2 inside
    data_dir — the config directory resolved by resolve_launch_config().

    Args:
        data_dir: Resolved config directory (e.g. emulators/xemu/data/default/).

    Raises:
        RuntimeError: If data_dir is absent or any required file is missing.
    """
    if not data_dir.exists() or not data_dir.is_dir():
        raise RuntimeError(
            f"xemu config directory not found: {data_dir}. "
            "Place your BIOS and HDD image files there before launching."
        )

    missing: list[str] = []

    mcpx = data_dir / "mcpx_1.0.bin"
    if not mcpx.exists():
        missing.append(f"  bootrom_path: {mcpx}")

    flash_bins = [
        f for f in sorted(data_dir.glob("*.bin"))
        if f.name.lower() not in ("mcpx_1.0.bin", "eeprom.bin")
    ]
    if not flash_bins:
        missing.append(f"  flashrom_path: <no flash BIOS *.bin found in {data_dir}>")

    hdd_path = data_dir / "xbox_hdd.qcow2"
    if not hdd_path.exists():
        missing.append(f"  hdd_path: {hdd_path}")

    if missing:
        lines = "\n".join(missing)
        raise RuntimeError(
            f"xemu asset files not found:\n{lines}\n"
            f"Place the missing files in {data_dir}."
        )


def launch(spec: "LaunchSpec") -> Tuple[SandboxProcess, WindowsJobObject]:
    """Launch xemu with the given Xbox disc image under Job Object isolation.

    Provisions the xemu.toml portable-mode sentinel beside the binary on
    every launch, sourcing BIOS/HDD assets from the resolved config under
    emulators/xemu/data/. No Platform record is required — xemu behaves like
    all other console backends (DuckStation, PCSX2, Mesen, Project64).

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
        RuntimeError: If XEMU_PATH is not configured, the data/ directory
            declared in xemu.toml is missing/empty, or launch fails.
    """
    _xemu_install = get_install_path("xemu")
    executable_path = str(_xemu_install) if _xemu_install and _xemu_install.is_file() else ""
    if not executable_path:
        raise RuntimeError(
            "xemu executable not found. Install it via the Emulators page."
        )
    if not Path(executable_path).exists():
        raise FileNotFoundError(f"xemu executable not found: {executable_path}")

    validate_bios_from_descriptor("xemu")

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

    exe_path = Path(executable_path)
    vm_dir = exe_path.parent
    config_name = resolve_launch_config()
    data_dir = vm_dir / DATA_DIR_NAME / config_name
    logger.debug(
        "xemu.launch: dvd_posix=%s vm_dir=%s data_dir=%s", dvd_posix, vm_dir, data_dir
    )
    validate_bios_path(data_dir)
    config_path = provision_xemu_defaults(exe_path, data_dir, dvd_path=dvd_posix)

    args = ["-dvd_path", dvd_posix] if dvd_posix else []

    job_name_prefix = f"Peach1UP_xemu_{spec.era}"

    catalog_enabled = get_container_enabled("xemu")
    container_enabled = spec.container_enabled if spec.container_enabled is not None else catalog_enabled

    if container_enabled:
        from backend.service.utils.platform.windows.app_container import (
            get_container_config as _build_sandbox_cfg,
        )
        hdd_path = data_dir / "xbox_hdd.qcow2"
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
        job_name_prefix=job_name_prefix,
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
