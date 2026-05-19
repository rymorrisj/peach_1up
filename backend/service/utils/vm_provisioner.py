"""VM provisioning for Peach 1UP.

Creates VirtualBox VMs and 86Box configs for Win9x/WinXP platforms on first
launch or platform creation. All output paths are resolved within OS_PATH and
validated before use. Subprocess args are constructed from validated, computed
values only — no user input reaches a subprocess call directly.
"""

from __future__ import annotations

import configparser
import os
import struct
import subprocess
import time
import uuid
from pathlib import Path

import yaml

from backend.core.logger import get_logger
from backend.core.settings import get_base_path
from backend.models.platform import Platform
from backend.service.utils.settings import get_binary_path, get_env_var

logger = get_logger(__name__)

_VDI_SIZE_MB: dict[str, int] = {
    "win95": 4096,
    "win98": 4096,
    "winxp": 10240,
}

_OS_TYPES: dict[str, str] = {
    "win95": "Windows95",
    "win98": "Windows98",
    "winxp": "WindowsXP",
}

_VM_MEMORY_MB: dict[str, int] = {
    "win95": 64,
    "win98": 128,
    "winxp": 512,
}

_WIN9X_ERAS = frozenset({"win95", "win98"})

# Per-era base machine hardware for 86Box 5.x (cpu_speed in Hz)
_MACHINE_BASE: dict[str, dict[str, str]] = {
    "win98": {
        "machine":    "prosignias31x_bx",
        "cpu_family": "pentium2_deschutes",
        "cpu_speed":  "350000000",
    },
    "win95": {
        "machine":    "p55t2p4",
        "cpu_family": "pentium_mmx",
        "cpu_speed":  "200000000",
    },
}

# Hardware profile → gfxcard / sndcard overrides
_HARDWARE_PROFILES: dict[str, dict[str, str]] = {
    "standard": {"gfxcard": "s3_virge_dx",          "sndcard": "sb16_pnp"},
    "3dfx":     {"gfxcard": "voodoo3_3500_si_agp",   "sndcard": "sb16_pnp"},
    "opl":      {"gfxcard": "s3_virge_dx",            "sndcard": "sb16"},
    "midi":     {"gfxcard": "s3_virge_dx",            "sndcard": "sb_awe32"},
}

_MIDI_PROFILES = frozenset({"midi"})


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


def _run_vbm(vbox_path: str, args: list[str], desc: str) -> None:
    result = subprocess.run([vbox_path] + args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"VBoxManage {desc} failed (exit {result.returncode}): {result.stderr.strip()}"
        )


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



def provision_virtualbox_vm(platform: Platform, vbox_path: str) -> str:
    """Create a VDI and register a VirtualBox VM for a Win9x/WinXP platform.

    Controller names ("SATA", "IDE") match those used by the virtualbox.py
    backend so that _ensure_registered's idempotency check is compatible.

    Args:
        platform: Platform record with ``era``, ``slug`` (or ``id``), and
            optionally ``base_image_path`` set.
        vbox_path: Absolute path to VBoxManage.exe, resolved from settings.

    Returns:
        Absolute path to the created VDI file as a string.

    Raises:
        ValueError: If era is unsupported or path validation fails.
        FileNotFoundError: If base_image_path does not exist on disk.
        RuntimeError: If any VBoxManage command fails (stderr included).
    """
    era = platform.era
    if era not in _VDI_SIZE_MB:
        raise ValueError(f"provision_virtualbox_vm: unsupported era '{era}'")

    os_base = Path(get_env_var("OS_PATH")).resolve()
    vm_name = _vm_name(platform)

    vdi_dir = _resolve_within(os_base, era, vm_name)
    vdi_dir.mkdir(parents=True, exist_ok=True)
    vdi_path = vdi_dir / "working.vdi"

    os_type = _OS_TYPES[era]
    size_mb = _VDI_SIZE_MB[era]
    memory_mb = _VM_MEMORY_MB[era]

    _run_vbm(vbox_path, [
        "createvm", "--name", vm_name, "--ostype", os_type, "--register",
    ], "createvm")

    _run_vbm(vbox_path, [
        "modifyvm", vm_name,
        "--memory", str(memory_mb),
        "--cpus", "1",
        "--nic1", "null",
    ], "modifyvm")

    _run_vbm(vbox_path, [
        "createhd", "--filename", str(vdi_path), "--size", str(size_mb),
    ], "createhd")

    _run_vbm(vbox_path, [
        "storagectl", vm_name,
        "--name", "SATA",
        "--add", "sata",
        "--bootable", "on",
    ], "storagectl SATA")

    _run_vbm(vbox_path, [
        "storageattach", vm_name,
        "--storagectl", "SATA",
        "--port", "0",
        "--device", "0",
        "--type", "hdd",
        "--medium", str(vdi_path),
    ], "storageattach HDD")

    _run_vbm(vbox_path, [
        "storagectl", vm_name,
        "--name", "IDE",
        "--add", "ide",
    ], "storagectl IDE")

    if platform.base_image_path:
        from backend.service.utils.path_utils import normalise_path
        iso_path = normalise_path(platform.base_image_path)
        if not iso_path.exists():
            raise FileNotFoundError(f"Base image not found: {iso_path}")
        _run_vbm(vbox_path, [
            "storageattach", vm_name,
            "--storagectl", "IDE",
            "--port", "0",
            "--device", "0",
            "--type", "dvddrive",
            "--medium", str(iso_path),
        ], "storageattach DVD")

    return str(vdi_path)


def provision_86box_vm(
    platform: Platform,
    box86_path: str,
    rom_path: str,
    hardware_profile: str = "standard",
) -> tuple[str | None, str, str]:
    """Create a raw fixed-size VHD and 86Box INI config for a Win95/Win98 platform.

    Creates a raw VHD at OS_PATH/{era}/{vm_name}/disk.vhd sized per
    eras.yaml default_disk_size_mb and appends a valid 512-byte VHD footer,
    then writes a complete INI config at OS_PATH/{era}/{vm_name}/86box.cfg.

    Args:
        platform: Platform record with ``era``, ``slug`` (or ``id``), and
            optionally ``base_image_path`` and ``machine_override`` set.
        box86_path: Absolute path to 86Box.exe, resolved from settings.
        rom_path: Absolute path to the 86Box ROM pack directory.
        hardware_profile: One of the keys in ``_HARDWARE_PROFILES``.
            Defaults to ``"standard"`` if the key is unrecognised.

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
    if era not in _WIN9X_ERAS:
        raise ValueError(f"provision_86box_vm: unsupported era '{era}'")

    disk_size_mb = _load_default_disk_size_mb(era)
    size_bytes = disk_size_mb * 1024 * 1024
    cylinders = size_bytes // (16 * 63 * 512)

    profile = _HARDWARE_PROFILES.get(hardware_profile, _HARDWARE_PROFILES["standard"])
    machine_base = _MACHINE_BASE[era]
    machine = getattr(platform, "machine_override", None) or machine_base["machine"]

    os_base = Path(get_env_var("OS_PATH")).resolve()
    vm_name = _vm_name(platform)
    cfg_dir = _resolve_within(os_base, era, vm_name)
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = cfg_dir / "86box.cfg"
    vhd_path = cfg_dir / "disk.vhd"

    footer = _build_vhd_footer(size_bytes)
    with vhd_path.open("wb") as f:
        f.seek(size_bytes - 512 - 1)
        f.write(b"\x00")
        f.write(footer)

    if platform.base_image_path:
        from backend.service.utils.path_utils import normalise_path
        iso_path = normalise_path(platform.base_image_path)
        if not iso_path.exists():
            raise FileNotFoundError(
                f"Base image not found: {iso_path}. "
                "Ensure base_image_path is set to a valid ISO before provisioning."
            )
    else:
        iso_path = None

    parser = configparser.RawConfigParser()
    parser.optionxform = str

    parser.add_section("Machine")
    parser.set("Machine", "machine",         machine)
    parser.set("Machine", "cpu_family",      machine_base["cpu_family"])
    parser.set("Machine", "cpu_speed",       machine_base["cpu_speed"])
    parser.set("Machine", "mem_size",        "131072")
    parser.set("Machine", "cpu_use_dynarec", "1")
    parser.set("Machine", "fpu_type",        "internal")

    parser.add_section("Video")
    parser.set("Video", "gfxcard",      profile["gfxcard"])
    parser.set("Video", "vid_renderer", "qt_software")

    parser.add_section("Sound")
    parser.set("Sound", "sndcard", profile["sndcard"])

    if hardware_profile in _MIDI_PROFILES:
        parser.add_section("MIDI")
        parser.set("MIDI", "midi_device", "nuked_sc55")

    vhd_fwd = str(vhd_path).replace("\\", "/")
    parser.add_section("Hard disks")
    parser.set("Hard disks", "hdd_01_fn",          vhd_fwd)
    parser.set("Hard disks", "hdd_01_ide_channel",  "0:0")
    parser.set("Hard disks", "hdd_01_parameters",   f"63, 16, {cylinders}, 0, ide")
    parser.set("Hard disks", "hdd_01_speed",         "ramdisk")

    if iso_path is not None:
        iso_fwd = str(iso_path).replace("\\", "/")
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

    return str(iso_path) if iso_path else None, str(vhd_path), str(cfg_path)


def provision_platform(platform: Platform) -> tuple[str | None, str | None, str | None]:
    """Provision a working image for a platform, selecting the backend by era.

    Provisions 86Box for win95/win98 (the new default), VirtualBox for winxp.
    Returns (None, None, None) for eras that do not need provisioning or when
    the required emulator paths are not configured.

    Args:
        platform: Platform record with ``era``, ``slug`` (or ``id``), and
            optionally ``base_image_path`` set.

    Returns:
        ``(base_image_path, working_image_path, config_path)`` — all None if
        provisioning was skipped. base_image_path is the resolved ISO path for
        86Box, or None for VirtualBox. config_path is None for VirtualBox.

    Raises:
        RuntimeError: If required emulator paths are not configured.
        FileNotFoundError: If templates or the base image are missing.
        ValueError: If path validation fails.
    """
    era = platform.era

    if era == "winxp":
        vbox_path = get_binary_path("virtualbox")
        if not vbox_path:
            raise RuntimeError(
                "VIRTUALBOX_PATH is not configured — cannot provision WinXP VM. "
                "Set the path in Settings or config/settings.yaml."
            )
        if not Path(vbox_path).exists():
            raise FileNotFoundError(
                f"VBoxManage not found at {vbox_path}. "
                "Download VirtualBox from: https://www.virtualbox.org"
            )
        working = provision_virtualbox_vm(platform, vbox_path)
        return None, working, None

    if era in _WIN9X_ERAS:
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
        if iso_path and not platform.base_image_path:
            platform.base_image_path = iso_path
        return iso_path, img_path, cfg_path

    return None, None, None
