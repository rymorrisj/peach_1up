"""VM provisioning for Peach 1UP.

Creates 86Box configs for Win95/Win98/WinXP platforms and xemu configs for
Xbox platforms on first launch or platform creation. 86Box VM files are placed
under emulators/86box/vms/{slug}/; xemu VM files under emulators/xemu/vms/{slug}/.
All output paths are resolved and validated before use. Subprocess args are
constructed from validated, computed values only — no user input reaches a
subprocess call directly.
"""

from __future__ import annotations

import configparser
import os
import shutil
import struct
import time
import uuid
from pathlib import Path

import yaml
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.core.logger import get_logger
from backend.core.settings import get_base_path
from backend.models.platform import Platform
from backend.service.utils.emulator_catalog import get_86box_profile
from backend.service.utils.settings import get_binary_path, get_env_var

logger = get_logger(__name__)

_86BOX_ERAS = frozenset({"win95", "win98", "winxp"})



def _build_vhd_footer(size_bytes: int) -> bytes:
    footer = bytearray(512)
    footer[0:8] = b"conectix"
    struct.pack_into(">I", footer, 8, 0x00000002)
    struct.pack_into(">I", footer, 12, 0x00010000)
    struct.pack_into(">Q", footer, 16, 0xFFFFFFFFFFFFFFFF)
    epoch_2000 = 946684800
    struct.pack_into(">I", footer, 24, max(0, int(time.time()) - epoch_2000))
    footer[28:32] = b"pe1u"
    struct.pack_into(">I", footer, 32, 0x00010000)
    footer[36:40] = b"Wi2k"
    struct.pack_into(">Q", footer, 40, size_bytes)
    struct.pack_into(">Q", footer, 48, size_bytes)
    cylinders = size_bytes // (16 * 63 * 512)
    struct.pack_into(">HBB", footer, 56, cylinders, 16, 63)
    struct.pack_into(">I", footer, 60, 0x00000002)
    struct.pack_into(">I", footer, 64, 0)
    footer[68:84] = uuid.uuid4().bytes
    checksum = (~sum(footer)) & 0xFFFFFFFF
    struct.pack_into(">I", footer, 64, checksum)
    return bytes(footer)


def _load_default_disk_size_mb(era: str) -> int:
    """Load default_disk_size_mb for *era* from eras.yaml.

    Raises:
        FileNotFoundError: If eras.yaml cannot be read, the era entry is
            absent, or the default_disk_size_mb key is missing.
    """
    eras_yaml = get_base_path() / "config" / "eras.yaml"
    try:
        with eras_yaml.open("r", encoding="utf-8") as fh:
            eras_config = yaml.safe_load(fh)
    except FileNotFoundError:
        raise FileNotFoundError(f"eras.yaml not found at {eras_yaml}")
    if not isinstance(eras_config, dict) or era not in eras_config:
        raise FileNotFoundError(
            f"Era '{era}' not found in eras.yaml — cannot determine disk size."
        )
    size = eras_config[era].get("default_disk_size_mb")
    if size is None:
        raise FileNotFoundError(
            f"default_disk_size_mb not defined for era '{era}' in eras.yaml."
        )
    return int(size)


def _resolve_within(base: Path, *parts: str) -> Path:
    """Resolve a sub-path and assert it has not escaped base via traversal."""
    base_resolved = base.resolve()
    target = (base_resolved / Path(*parts)).resolve()
    try:
        target.relative_to(base_resolved)
    except ValueError:
        raise ValueError(
            f"Computed path {target} escapes permitted base {base_resolved}"
        )
    return target


def _vm_name(platform: Platform) -> str:
    return platform.slug or f"p{platform.id}"



def provision_86box_vm(
    platform: Platform,
    box86_path: str,
    rom_path: str,
    hardware_profile: str = "standard",
) -> tuple[str | None, str, str]:
    """Create a raw fixed-size VHD and 86Box INI config for a Win95/Win98 platform.

    Creates a raw VHD at emulators/86box/vms/{slug}/disk.vhd sized per
    eras.yaml default_disk_size_mb and appends a valid 512-byte VHD footer,
    then writes a complete INI config at emulators/86box/vms/{slug}/86box.cfg.

    Args:
        platform: Platform record with ``era``, ``slug`` (or ``id``), and
            optionally ``base_image_path`` and ``machine_override`` set.
        box86_path: Absolute path to 86Box.exe, resolved from settings.
        rom_path: Absolute path to the 86Box ROM pack directory.
        hardware_profile: Slug of a profile defined in config/86box-profiles/.
            Raises ValueError if the slug is not found.

    Returns:
        Tuple of (base_image_path, working_image_path, config_path).
        base_image_path is the resolved ISO string, or None if not set;
        working_image_path is the raw VHD disk file;
        config_path is the 86box.cfg.

    Raises:
        ValueError: If era is unsupported.
        FileNotFoundError: If eras.yaml is missing, the era entry lacks
            default_disk_size_mb, or base_image_path is set but does not exist.
        OSError: If creating the disk image or writing the config fails.
    """
    era = platform.era
    if era not in _86BOX_ERAS:
        raise ValueError(f"provision_86box_vm: unsupported era '{era}'")

    disk_size_mb = _load_default_disk_size_mb(era)
    size_bytes = disk_size_mb * 1024 * 1024
    cylinders = size_bytes // (16 * 63 * 512)

    profile = get_86box_profile(hardware_profile)
    machine = getattr(platform, "machine_override", None) or profile["machine"]

    vms_base = (get_base_path() / "emulators" / "86box" / "vms").resolve()
    vm_name = _vm_name(platform)
    cfg_dir = _resolve_within(vms_base, vm_name)
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = cfg_dir / "86box.cfg"

    # Resolve base image and decide working image strategy.
    effective_iso_path = None
    if platform.base_image_path:
        from backend.service.utils.path_utils import normalise_path
        from backend.service.utils.disk_utils import has_valid_mbr
        base_img = normalise_path(platform.base_image_path)
        if not base_img.exists():
            raise FileNotFoundError(
                f"Base image not found: {base_img}. "
                "Ensure base_image_path is set to a valid image before provisioning."
            )
        try:
            is_pre_installed = (
                base_img.suffix.lower() not in {".iso", ".cue"}
                and has_valid_mbr(base_img)
            )
        except (ValueError, OSError):
            is_pre_installed = False
    else:
        base_img = None
        is_pre_installed = False

    if is_pre_installed:
        vhd_path = cfg_dir / ("disk" + base_img.suffix.lower())
        try:
            shutil.copy2(str(base_img), str(vhd_path))
        except OSError as exc:
            raise OSError(
                f"Failed to copy pre-installed image '{base_img}' to VM directory: {exc}"
            ) from exc
    else:
        vhd_path = cfg_dir / "disk.vhd"
        footer = _build_vhd_footer(size_bytes)
        with vhd_path.open("wb") as f:
            f.seek(size_bytes - 512 - 1)
            f.write(b"\x00")
            f.write(footer)
        if base_img is not None and base_img.suffix.lower() in {".iso", ".cue"}:
            effective_iso_path = base_img

    parser = configparser.RawConfigParser()
    parser.optionxform = str

    parser.add_section("General")
    parser.set("General", "boot_order", "cdrom_fdd_hdd")

    parser.add_section("Machine")
    parser.set("Machine", "machine",         machine)
    parser.set("Machine", "cpu_family",      profile["cpu_family"])
    parser.set("Machine", "cpu_speed",       str(profile["cpu_speed"]))
    parser.set("Machine", "cpu_multi",       str(profile["cpu_multi"]))
    parser.set("Machine", "mem_size",        str(profile["mem_size"]))
    parser.set("Machine", "cpu_use_dynarec", str(profile["cpu_use_dynarec"]))
    parser.set("Machine", "fpu_type",        profile["fpu_type"])

    parser.add_section("Video")
    parser.set("Video", "gfxcard",      profile["gfxcard"])
    parser.set("Video", "vid_renderer", profile["vid_renderer"])

    parser.add_section("Sound")
    parser.set("Sound", "sndcard", profile["sndcard"])

    if profile.get("slug") == "midi":
        parser.add_section("MIDI")
        parser.set("MIDI", "midi_device", "nuked_sc55")

    parser.add_section("Keyboard")
    parser.set("Keyboard", "keyboard_type", profile["keyboard_type"])

    parser.add_section("Mouse")
    parser.set("Mouse", "mouse_type", profile["mouse_type"])

    parser.add_section("Hard disks")
    parser.set("Hard disks", "hdd_01_fn",          vhd_path.name)
    parser.set("Hard disks", "hdd_01_ide_channel",  "0:0")
    parser.set("Hard disks", "hdd_01_parameters",   f"63, 16, {cylinders}, 0, ide")
    parser.set("Hard disks", "hdd_01_speed",         "ramdisk")

    if effective_iso_path is not None:
        iso_fwd = effective_iso_path.resolve().as_posix()
        parser.add_section("Floppy and CD-ROM drives")
        parser.set("Floppy and CD-ROM drives", "cdrom_02_image_path", iso_fwd)
        parser.set("Floppy and CD-ROM drives", "cdrom_02_parameters",  "1, atapi")
        parser.set("Floppy and CD-ROM drives", "cdrom_02_ide_channel", "0:1")

    parser.add_section("Paths")
    parser.set("Paths", "rompath", str(Path(rom_path)).replace("\\", "/"))

    parser.add_section("Network")
    parser.set("Network", "net_01_link", "0")

    with cfg_path.open("w", encoding="utf-8") as fh:
        parser.write(fh)

    return str(effective_iso_path) if effective_iso_path else None, str(vhd_path), str(cfg_path)


def provision_xemu_vm(platform: Platform) -> tuple[str | None, str, str]:
    """Create a VM directory and xemu.toml config for an Xbox platform.

    Creates the VM directory at
    get_base_path()/emulators/xemu/vms/{slug} and writes a minimal
    xemu.toml pointing to BIOS files in XBOX_BIOS_PATH and to a
    colocated xbox_hdd.qcow2 HDD image. The HDD image is not created
    here — it must be provided separately by the user.

    Args:
        platform: Platform record with ``era`` == "xbox" and ``slug`` set.

    Returns:
        Tuple of (base_image_path, working_image_path, config_path).
        base_image_path is always None (Xbox HDD is not an ISO);
        working_image_path is the expected path to xbox_hdd.qcow2;
        config_path is the written xemu.toml.

    Raises:
        ValueError: If path validation fails.
        OSError: If creating the directory or writing the config fails.
    """
    vm_name = _vm_name(platform)
    vms_base = (get_base_path() / "emulators" / "xemu" / "vms").resolve()
    vm_dir = _resolve_within(vms_base, vm_name)
    vm_dir.mkdir(parents=True, exist_ok=True)

    bios_path_str = get_env_var("XBOX_BIOS_PATH")
    if bios_path_str:
        bios_dir = Path(bios_path_str).resolve()
        bootrom = str(bios_dir / "mcpx_1.0.bin").replace("\\", "/")
        flashrom = str(bios_dir / "bios.bin").replace("\\", "/")
    else:
        bootrom = ""
        flashrom = ""

    toml_path = vm_dir / "xemu.toml"
    with toml_path.open("w", encoding="utf-8") as fh:
        fh.write("[sys]\n")
        fh.write(f'bootrom_path = "{bootrom}"\n')
        fh.write(f'flashrom_path = "{flashrom}"\n')
        fh.write('hdd_path = "xbox_hdd.qcow2"\n')
        fh.write('dvd_path = ""\n')
        fh.write("\n[net]\nenabled = false\n")

    return None, str(vm_dir / "xbox_hdd.qcow2"), str(toml_path)


def provision_platform(platform: Platform, db: Session | None = None) -> tuple[str | None, str | None, str | None]:
    """Provision a working image for a platform, selecting the backend by era.

    Provisions 86Box for win95/win98/winxp, xemu for Xbox.
    Returns (None, None, None) for eras that do not need provisioning or when
    the required emulator paths are not configured.

    Args:
        platform: Platform record with ``era``, ``slug`` (or ``id``), and
            optionally ``base_image_path`` set.

    Returns:
        ``(base_image_path, working_image_path, config_path)`` — all None if
        provisioning was skipped. base_image_path is the resolved ISO path, or
        None if no ISO was attached.

    Raises:
        RuntimeError: If required emulator paths are not configured.
        FileNotFoundError: If templates or the base image are missing.
        ValueError: If path validation fails.
    """
    era = platform.era

    if era in _86BOX_ERAS:
        box86_path = get_binary_path("box86")
        if not box86_path:
            raise RuntimeError(
                "BOX86_PATH is not configured — cannot provision 86Box config. "
                "Set the path in Settings or config/settings.yaml."
            )
        from backend.service.backends.box86 import _resolve_rom_path
        rom_dir = _resolve_rom_path(Path(box86_path))
        hw_profile = getattr(platform, "hardware_profile", None) or "standard"
        iso_path, img_path, cfg_path = provision_86box_vm(platform, box86_path, str(rom_dir), hw_profile)
        if iso_path and not platform.base_image_path and db is not None:
            # Explicit ORM update — avoids relying on session change-tracking for
            # a destructive write. db.commit() is the caller's responsibility.
            db.execute(
                update(Platform)
                .where(Platform.id == platform.id)
                .values(base_image_path=str(iso_path))
            )
            db.flush()
        return iso_path, img_path, cfg_path

    if era == "xbox":
        iso_path, img_path, cfg_path = provision_xemu_vm(platform)
        return iso_path, img_path, cfg_path

    return None, None, None
