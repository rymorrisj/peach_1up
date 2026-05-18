"""VM provisioning for Peach 1UP.

Creates VirtualBox VMs and 86Box configs for Win9x/WinXP platforms on first
launch or platform creation. All output paths are resolved within OS_PATH and
validated before use. Subprocess args are constructed from validated, computed
values only — no user input reaches a subprocess call directly.
"""

from __future__ import annotations

import configparser
import logging
import os
import subprocess
from pathlib import Path

from backend.models.platform import Platform
from backend.service.utils.settings import get, get_binary_path, get_env_var

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

logger = logging.getLogger(__name__)

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
) -> str:
    """Create an 86Box INI config file for a Win95/Win98 platform.

    Generates a complete INI config from the selected hardware profile and
    era machine base, writes it to OS_PATH/{era}/{vm_name}/86box.cfg, and
    returns that path. Stored as both working_image_path and config_path.

    Args:
        platform: Platform record with ``era``, ``slug`` (or ``id``), and
            optionally ``base_image_path`` and ``machine_override`` set.
        box86_path: Absolute path to 86Box.exe, resolved from settings.
        rom_path: Absolute path to the 86Box ROM pack directory.
        hardware_profile: One of the keys in ``_HARDWARE_PROFILES``.
            Defaults to ``"standard"`` if the key is unrecognised.

    Returns:
        Absolute path to the created 86box.cfg as a string.

    Raises:
        ValueError: If era is unsupported.
        OSError: If writing the config file fails.
    """
    era = platform.era
    if era not in _WIN9X_ERAS:
        raise ValueError(f"provision_86box_vm: unsupported era '{era}'")

    profile = _HARDWARE_PROFILES.get(hardware_profile, _HARDWARE_PROFILES["standard"])
    machine_base = _MACHINE_BASE[era]
    machine = getattr(platform, "machine_override", None) or machine_base["machine"]

    os_base = Path(get_env_var("OS_PATH")).resolve()
    vm_name = _vm_name(platform)
    cfg_dir = _resolve_within(os_base, era, vm_name)
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = cfg_dir / "86box.cfg"

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

    parser.add_section("Network")
    parser.set("Network", "net_type",    "none")
    parser.set("Network", "net_01_link", "0")

    if hardware_profile in _MIDI_PROFILES:
        parser.add_section("MIDI")
        parser.set("MIDI", "midi_device", "nuked_sc55")

    parser.add_section("Paths")
    parser.set("Paths", "rompath", os.path.normpath(rom_path))

    if platform.base_image_path:
        from backend.service.utils.path_utils import normalise_path
        iso_path = normalise_path(platform.base_image_path)
        if iso_path.exists():
            parser.add_section("CD-ROM")
            parser.set("CD-ROM", "cd_path", os.path.normpath(str(iso_path)))

    with cfg_path.open("w", encoding="utf-8") as fh:
        parser.write(fh)

    return str(cfg_path)


def provision_platform(platform: Platform) -> tuple[str | None, str | None]:
    """Provision a working image for a platform, selecting the backend by era.

    Provisions 86Box for win95/win98 (the new default), VirtualBox for winxp.
    Returns (None, None) for eras that do not need provisioning or when the
    required emulator paths are not configured.

    Args:
        platform: Platform record with ``era``, ``slug`` (or ``id``), and
            optionally ``base_image_path`` set.

    Returns:
        ``(working_image_path, config_path)`` — both are None if provisioning
        was skipped. For 86Box, both values are the cfg file path. For
        VirtualBox, config_path is None (config lives inside the VM).

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
        return working, None

    if era in _WIN9X_ERAS:
        box86_path = get_binary_path("box86")
        if not box86_path:
            raise RuntimeError(
                "BOX86_PATH is not configured — cannot provision 86Box config. "
                "Set the path in Settings or config/settings.yaml."
            )
        _rom_str = get("ROM_PATH") or ""
        rom_dir = Path(_rom_str) if _rom_str else _PROJECT_ROOT / "library" / "roms" / "86box"
        if not rom_dir.exists():
            raise RuntimeError(
                f"86Box ROM pack not found at {rom_dir}. "
                "Download the ROM pack from https://github.com/86Box/roms and place it at that path."
            )
        rom_path = str(rom_dir)
        hw_profile = getattr(platform, "hardware_profile", None) or "standard"
        cfg = provision_86box_vm(platform, box86_path, rom_path, hw_profile)
        return cfg, cfg

    return None, None
