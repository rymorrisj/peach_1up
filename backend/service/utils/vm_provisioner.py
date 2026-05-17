"""VM provisioning for Peach 1UP.

Creates VirtualBox VMs and 86Box configs for Win9x/WinXP platforms on first
launch or platform creation. All output paths are resolved within OS_PATH and
validated before use. Subprocess args are constructed from validated, computed
values only — no user input reaches a subprocess call directly.

SECURITY: base_image_path from the platform record is re-validated at the
point of use (SECURITY.md: validate at the point of use, not only at input).
"""

from __future__ import annotations

import configparser
import logging
import subprocess
from pathlib import Path

import yaml

from backend.models.platform import Platform
from backend.service.utils.settings import get_binary_path, get_env_var

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


def _validate_iso_within_library(iso_path: Path) -> None:
    """Assert iso_path is within OS_PATH or LIBRARY_PATH (SECURITY.md allowlist)."""
    os_base = Path(get_env_var("OS_PATH")).resolve()
    lib_base = Path(get_env_var("LIBRARY_PATH")).resolve()
    resolved = iso_path.resolve()
    within_os = resolved == os_base or os_base in resolved.parents
    within_lib = resolved == lib_base or lib_base in resolved.parents
    if not within_os and not within_lib:
        raise ValueError(
            f"Base image path {resolved} is not within a permitted directory "
            f"({os_base} or {lib_base})"
        )


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
        _validate_iso_within_library(iso_path)
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


def provision_86box_vm(platform: Platform, box86_path: str, rom_path: str) -> str:
    """Create an 86Box INI config file for a Win95/Win98 platform.

    Reads the era hardware template from config/templates/86box_{era}.yaml,
    writes an INI config with the ROM path and optional installer ISO attached,
    and returns the config file path. This path is stored as both
    working_image_path and config_path on the platform record.

    Args:
        platform: Platform record with ``era``, ``slug`` (or ``id``), and
            optionally ``base_image_path`` set.
        box86_path: Absolute path to 86Box.exe, resolved from settings.
        rom_path: Absolute path to the 86Box ROM pack directory.

    Returns:
        Absolute path to the created 86box.cfg as a string.

    Raises:
        ValueError: If era is unsupported or the template is not a valid mapping.
        FileNotFoundError: If the era template file does not exist.
        OSError: If writing the config file fails.
    """
    era = platform.era
    if era not in _WIN9X_ERAS:
        raise ValueError(f"provision_86box_vm: unsupported era '{era}'")

    template_path = Path("config") / "templates" / f"86box_{era}.yaml"
    if not template_path.exists():
        raise FileNotFoundError(
            f"86Box template not found: {template_path}. "
            "Expected config/templates/86box_{era}.yaml."
        )
    with template_path.open("r", encoding="utf-8") as fh:
        template = yaml.safe_load(fh)
    if not isinstance(template, dict):
        raise ValueError(
            f"86Box template '{template_path.name}' is not a valid YAML mapping."
        )

    os_base = Path(get_env_var("OS_PATH")).resolve()
    vm_name = _vm_name(platform)

    cfg_dir = _resolve_within(os_base, era, vm_name)
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = cfg_dir / "86box.cfg"

    parser = configparser.RawConfigParser(optionxform=str)
    for section, values in template.items():
        if isinstance(values, dict):
            parser.add_section(section)
            for key, val in values.items():
                parser.set(section, key, str(val))

    if not parser.has_section("Paths"):
        parser.add_section("Paths")
    parser.set("Paths", "rompath", rom_path)

    if platform.base_image_path:
        from backend.service.utils.path_utils import normalise_path
        iso_path = normalise_path(platform.base_image_path)
        _validate_iso_within_library(iso_path)
        if iso_path.exists():
            if not parser.has_section("CD-ROM"):
                parser.add_section("CD-ROM")
            parser.set("CD-ROM", "cd_path", str(iso_path))

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
        rom_path = get_env_var("ROM_PATH")
        if not box86_path:
            raise RuntimeError(
                "BOX86_PATH is not configured — cannot provision 86Box config. "
                "Set the path in Settings or config/settings.yaml."
            )
        if not rom_path:
            raise RuntimeError(
                "ROM_PATH is not configured — cannot provision 86Box config. "
                "Download the ROM pack from: https://github.com/86Box/roms"
            )
        cfg = provision_86box_vm(platform, box86_path, rom_path)
        return cfg, cfg

    return None, None
