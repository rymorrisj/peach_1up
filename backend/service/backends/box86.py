"""86Box backend for Peach 1UP.

Handles Win95 and Win98 accuracy mode launches. Accepts a registered OSPlatform,
loads the era hardware template, validates all identifiers, optionally injects
game media into the config file, and launches 86Box under Job Objects.
"""

from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Optional

from backend.constants_generated import Era
from backend.core.logger import get_logger
from backend.core.settings import get_base_path
from backend.models.platform import Platform
from backend.service.utils.disk_utils import has_valid_mbr
from backend.service.utils.emulator_catalog import (
    get_86box_profile,
    get_container_enabled,
    get_container_config as get_emulator_container_config,
)
from backend.service.utils.launcher import launch_under_job_object
from backend.service.utils.media_attach import build_86box_attachment
from backend.service.utils.settings import get_binary_path

logger = get_logger(__name__)

SUPPORTED_ERAS = {Era.WIN95.value, Era.WIN98.value}


def validate_rom_path(rom_path: Path) -> None:
    """Validate that the 86Box ROM path exists and is a directory.

    Args:
        rom_path: Path to the ROM directory.

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If the path exists but is not a directory.
    """
    if not rom_path.exists():
        raise FileNotFoundError(
            f"ROM path not found: {rom_path}. "
            "Download the 86Box ROM pack from: https://github.com/86Box/roms"
        )
    if not rom_path.is_dir():
        raise ValueError(
            f"ROM path is not a directory: {rom_path}. "
            "ROM_PATH must point to the directory containing 86Box ROM files."
        )


def _resolve_rom_path(box86_binary: Path) -> Path:
    """Derive the effective ROM path from the 86Box binary location.

    Looks in the directory containing the binary for a single versioned
    ROM subdirectory (e.g. roms-5.3). No fallback — the subdirectory must
    exist and be the only subdirectory present.

    Raises:
        FileNotFoundError: If no single ROM subdirectory is found.
    """
    from backend.service.utils.emulator_catalog import get_emulator

    base = box86_binary.parent
    try:
        entries = list(base.iterdir())
    except OSError as exc:
        raise FileNotFoundError(f"Cannot read 86Box directory: {base}") from exc

    subdirs = [e for e in entries if e.is_dir()]
    rom_dirs = [e for e in subdirs if e.name.startswith("roms")]
    if len(rom_dirs) == 1:
        return rom_dirs[0]

    try:
        catalog_entry = get_emulator("86box")
        rom_pack_version = catalog_entry.get("rom_pack_version", "")
        rom_pack_url = catalog_entry.get("rom_pack_url", "https://github.com/86Box/roms")
    except Exception:
        rom_pack_version = ""
        rom_pack_url = "https://github.com/86Box/roms"

    expected_name = f"roms-{rom_pack_version}" if rom_pack_version else "roms-<version>"
    expected_path = base / expected_name
    raise FileNotFoundError(
        f"No ROM directory found alongside the 86Box binary at {base}. "
        f"Expected a versioned subdirectory at {expected_path}. "
        f"Download the 86Box ROM pack from: {rom_pack_url}"
    )


def _ensure_section(parser: configparser.RawConfigParser, section: str) -> None:
    if not parser.has_section(section):
        parser.add_section(section)


def _prepare_config(platform: Platform, cfg_path: str, rom_path: Path) -> None:
    """Patch all required 86Box config keys before every launch.

    Reads the existing config (BOM-tolerant), overwrites only the keys this
    function manages, and writes back without BOM. All other sections and keys
    that 86Box has written are preserved unchanged.

    Idempotent: calling twice with the same inputs produces the same file.

    Raises:
        FileNotFoundError: If the config file or disk image does not exist.
        OSError: If the disk image cannot be read or the atomic write fails.
    """
    cp = Path(cfg_path)
    if not cp.exists():
        raise FileNotFoundError(f"86Box config not found: {cp}")

    parser = configparser.RawConfigParser()
    parser.optionxform = str
    parser.read(str(cp), encoding="utf-8-sig")

    img_path = Path(str(platform.working_image_path))
    try:
        disk_has_mbr = has_valid_mbr(img_path)
    except (ValueError, OSError) as exc:
        raise OSError(
            f"Cannot read disk image for platform '{platform.name}': {img_path}"
        ) from exc

    _ensure_section(parser, "General")
    parser.set("General", "boot_order", "hdd_cdrom_fdd" if disk_has_mbr else "cdrom_fdd_hdd")

    hw_profile = get_86box_profile(platform.hardware_profile or "standard")
    _ensure_section(parser, "Machine")
    parser.set("Machine", "machine",         hw_profile["machine"])
    parser.set("Machine", "cpu_family",      hw_profile["cpu_family"])
    parser.set("Machine", "cpu_speed",       str(hw_profile["cpu_speed"]))
    parser.set("Machine", "cpu_multi",       str(hw_profile["cpu_multi"]))
    parser.set("Machine", "mem_size",        str(hw_profile["mem_size"]))
    parser.set("Machine", "cpu_use_dynarec", str(hw_profile["cpu_use_dynarec"]))
    parser.set("Machine", "fpu_type",        hw_profile["fpu_type"])

    _ensure_section(parser, "Video")
    parser.set("Video", "gfxcard",      hw_profile["gfxcard"])
    parser.set("Video", "vid_renderer", hw_profile["vid_renderer"])

    _ensure_section(parser, "Sound")
    parser.set("Sound", "sndcard", hw_profile["sndcard"])

    for _stale in ("Keyboard", "Mouse"):
        if parser.has_section(_stale):
            parser.remove_section(_stale)
    _ensure_section(parser, "Input devices")
    parser.set("Input devices", "mouse_type",    "ps2")
    parser.set("Input devices", "keyboard_type", "keyboard_ps2")

    _ensure_section(parser, "Hard disks")
    parser.set("Hard disks", "hdd_01_fn", img_path.name)
    parser.set("Hard disks", "hdd_01_ide_channel", "0:0")
    parser.set("Hard disks", "hdd_01_parameters", "63, 16, 4161, 0, ide")
    parser.set("Hard disks", "hdd_01_speed", "ramdisk")

    cdrom_section = "Floppy and CD-ROM drives"
    is_iso = (
        not disk_has_mbr
        and platform.base_image_path is not None
        and Path(str(platform.base_image_path)).suffix.lower() in {".iso", ".cue"}
        and Path(str(platform.base_image_path)).exists()
    )
    if is_iso:
        iso = Path(str(platform.base_image_path))
        _ensure_section(parser, cdrom_section)
        iso_fwd = str(iso.resolve()).replace("\\", "/")
        parser.set(cdrom_section, "cdrom_02_image_path", iso_fwd)
        parser.set(cdrom_section, "cdrom_02_parameters", "1, atapi")
        parser.set(cdrom_section, "cdrom_02_ide_channel", "0:1")
    else:
        if parser.has_section(cdrom_section) and parser.has_option(cdrom_section, "cdrom_02_image_path"):
            parser.remove_option(cdrom_section, "cdrom_02_image_path")

    _ensure_section(parser, "Paths")
    parser.set("Paths", "rompath", str(rom_path.resolve()))

    _ensure_section(parser, "Network")
    parser.set("Network", "net_01_link", "0")

    tmp_path = cp.with_suffix(cp.suffix + ".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as fh:
            parser.write(fh)
        os.replace(str(tmp_path), str(cp))
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise


def _inject_media(attachment: dict) -> None:
    """Inject a media path into an 86Box config file atomically.

    Reads the existing config, sets the attachment section/key, then writes to
    a temp file and renames it into place via os.replace(). If the rename fails
    the temp file is cleaned up and the original config is left untouched — a
    missing or corrupt config is a hard launch failure with no recovery path.

    RawConfigParser(optionxform=str) preserves the mixed-case section names and
    keys that 86Box expects (e.g. the CD-ROM section header).

    Args:
        attachment: Dict from ``build_86box_attachment`` — must contain
            ``config_path``, ``section``, ``key``, and ``value``.

    Raises:
        FileNotFoundError: If the config file does not exist.
        OSError: If reading, writing, or the atomic rename fails.
    """
    config_path = Path(attachment["config_path"])
    if not config_path.exists():
        raise FileNotFoundError(
            f"86Box config file not found: {config_path}. "
            "Ensure the platform config_path is set correctly."
        )

    parser = configparser.RawConfigParser()
    parser.optionxform = str
    parser.read(str(config_path), encoding="utf-8-sig")

    section = attachment["section"]
    if not parser.has_section(section):
        parser.add_section(section)
    parser.set(section, attachment["key"], attachment["value"])

    tmp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as fh:
            parser.write(fh)
        os.replace(str(tmp_path), str(config_path))
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise


def launch(
    platform: Platform,
    media_path: Optional[Path] = None,
    enable_networking: bool = False,
) -> tuple:
    """Launch 86Box in accuracy mode under Job Objects.

    Validates platform state and environment, patches the 86Box config for
    this launch, optionally injects game media, then launches 86Box with
    resource limits applied.

    Args:
        platform: Registered OSPlatform. ``era``, ``working_image_path``, and
            ``config_path`` must all be set before calling.
        media_path: Optional game media to attach at launch time. When
            provided, the cd_path key is injected into the 86Box config
            before launch.
        enable_networking: When True, overrides the default net_01_link=0 set
            by _prepare_config to allow network traffic.

    Raises:
        ValueError: If the era is unsupported or required platform fields are
            unset.
        FileNotFoundError: If ``working_image_path``, ``config_path``,
            ``BOX86_PATH``, or ``ROM_PATH`` do not exist on disk.
        RuntimeError: If ``BOX86_PATH`` or ``ROM_PATH`` env vars are unset.
        OSError: If config injection or Job Object launch fails.
    """
    if platform.era not in SUPPORTED_ERAS:
        raise ValueError(
            f"86Box backend does not support era '{platform.era}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_ERAS))}"
        )

    if platform.working_image_path is None:
        raise ValueError(
            f"Platform '{platform.name}' has no working_image_path set. "
            "Complete platform registration (including image copy) before launching."
        )

    img_path = Path(str(platform.working_image_path))
    if not img_path.exists():
        raise ValueError(
            f"Platform '{platform.name}' working_image_path does not exist on disk: {img_path}. "
            "Re-register the platform to provision a new disk image."
        )
    if img_path.suffix.lower() not in {".img", ".vhd"}:
        raise ValueError(
            f"Platform '{platform.name}' working_image_path must be a disk image "
            f"(.img or .vhd), not '{img_path.suffix}': {img_path}. "
            "working_image_path is set to a config file — re-register the platform."
        )

    if platform.config_path is None:
        raise ValueError(
            f"Platform '{platform.name}' has no config_path set. "
            "Complete platform registration before launching."
        )

    box86_path = get_binary_path("box86")
    if not box86_path:
        raise RuntimeError(
            "86Box binary path is not configured. "
            "Set BOX86_PATH in your .env file or add an override in Settings."
        )
    if not Path(box86_path).exists():
        raise FileNotFoundError(f"86Box executable not found: {box86_path}")

    effective_rom_path = _resolve_rom_path(Path(box86_path))

    _prepare_config(platform, platform.config_path, effective_rom_path)

    if enable_networking:
        _inject_media({
            "config_path": platform.config_path,
            "section": "Network",
            "key": "net_01_link",
            "value": "1",
        })

    job_paths = [str(platform.working_image_path)]

    if media_path is not None:
        attachment = build_86box_attachment(media_path, platform.config_path)
        _inject_media(attachment)
        job_paths.append(str(media_path))

    if platform.base_image_path is not None:
        iso = Path(str(platform.base_image_path))
        if iso.exists():
            job_paths.append(str(iso))

    vm_dir = Path(str(platform.config_path)).parent.resolve()

    args = [
        "--config", str(platform.config_path),
        "--rompath", str(effective_rom_path),
        "--vmpath", str(vm_dir),
    ]

    job_name = f"peach1up_86box_{platform.era}_{platform.slug}"

    return launch_under_job_object(
        executable_path=box86_path,
        args=args,
        media_paths=job_paths,
        era=platform.era,
        job_name=job_name,
        slug="86box",
        cwd=str(vm_dir),
        container_enabled=get_container_enabled("86box"),
        sandbox_config=get_emulator_container_config("86box", box86_path),
    )
