"""VM provisioning for Peach 1UP.

Creates 86Box configs for Win95/Win98/WinXP platforms and xemu configs for
Xbox platforms on first launch or platform creation. 86Box VM files are placed
under emulators/86box/vms/{slug}/; xemu VM files under emulators/xemu/vms/{slug}/.
All output paths are resolved and validated before use. Subprocess args are
constructed from validated, computed values only — no user input reaches a
subprocess call directly.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.core.logger import get_logger
from backend.core.settings import get_base_path
from backend.models.platform import Platform
from backend.service.utils.emulator_catalog import get_86box_profile
from backend.service.utils.ini_writer import patch_ini
from backend.service.utils.settings import get_binary_path
from backend.service.utils.vm.vhd import _build_vhd_footer

logger = get_logger(__name__)

_86BOX_ERAS = frozenset({"win95", "win98", "winxp"})


def _load_default_disk_size_mb(era: str) -> int:
    """Load default_disk_size_mb for *era* from eras.yaml."""
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
    """Create a raw fixed-size VHD and 86Box INI config for a Win95/Win98 platform."""
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

    edits: dict[str, dict[str, str]] = {
        "General": {"boot_order": "cdrom_fdd_hdd"},
        "Machine": {
            "machine":         machine,
            "cpu_family":      profile["cpu_family"],
            "cpu_speed":       str(profile["cpu_speed"]),
            "cpu_multi":       str(profile["cpu_multi"]),
            "mem_size":        str(profile["mem_size"]),
            "cpu_use_dynarec": str(profile["cpu_use_dynarec"]),
            "fpu_type":        profile["fpu_type"],
        },
        "Video": {
            "gfxcard":      profile["gfxcard"],
            "vid_renderer": profile["vid_renderer"],
        },
        "Sound": {"sndcard": profile["sndcard"]},
        "Keyboard": {"keyboard_type": profile["keyboard_type"]},
        "Mouse":    {"mouse_type":    profile["mouse_type"]},
        "Hard disks": {
            "hdd_01_fn":         vhd_path.name,
            "hdd_01_ide_channel": "0:0",
            "hdd_01_parameters":  f"63, 16, {cylinders}, 0, ide",
            "hdd_01_speed":       "ramdisk",
        },
        "Paths":   {"rompath":    str(Path(rom_path)).replace("\\", "/")},
        "Network": {"net_01_link": "0"},
    }

    if profile.get("slug") == "midi":
        edits["MIDI"] = {"midi_device": "nuked_sc55"}

    if effective_iso_path is not None:
        iso_fwd = effective_iso_path.resolve().as_posix()
        edits["Floppy and CD-ROM drives"] = {
            "cdrom_02_image_path": iso_fwd,
            "cdrom_02_parameters":  "1, atapi",
            "cdrom_02_ide_channel": "0:1",
        }

    patch_ini(cfg_path, edits)

    return str(effective_iso_path) if effective_iso_path else None, str(vhd_path), str(cfg_path)


def provision_xemu_vm(platform: Platform) -> tuple[str | None, str, str]:
    """Create a VM directory and xemu.toml config for an Xbox platform."""
    vm_name = _vm_name(platform)
    vms_base = (get_base_path() / "emulators" / "xemu" / "vms").resolve()
    vm_dir = _resolve_within(vms_base, vm_name)
    vm_dir.mkdir(parents=True, exist_ok=True)

    base = get_base_path()
    global_toml = base / "emulators" / "xemu" / "xemu.toml"
    flash_path = ""
    bios_path = ""
    if global_toml.exists():
        try:
            import tomllib as _tomllib
            _cfg = _tomllib.loads(global_toml.read_text(encoding="utf-8"))
            _sys = _cfg.get("system", {})
            for _key, _attr in (("flash_path", "flash_path"), ("bios_path", "bios_path")):
                _raw = _sys.get(_key, "")
                if _raw:
                    _p = Path(_raw)
                    _resolved = str((_p if _p.is_absolute() else (base / _p).resolve()).as_posix())
                    if _key == "flash_path":
                        flash_path = _resolved
                    else:
                        bios_path = _resolved
        except Exception:
            pass

    global_hdd = base / "emulators" / "xemu" / "xbox_hdd.qcow2"
    vm_hdd = vm_dir / "xbox_hdd.qcow2"
    if not vm_hdd.exists() and global_hdd.exists():
        shutil.copy2(str(global_hdd), str(vm_hdd))
    hdd_path = vm_hdd.resolve().as_posix()

    toml_path = vm_dir / "xemu.toml"
    if not toml_path.exists():
        with toml_path.open("w", encoding="utf-8") as fh:
            fh.write("[system]\n")
            fh.write(f'flash_path = "{flash_path}"\n')
            fh.write(f'bios_path = "{bios_path}"\n')
            fh.write("[storage]\n")
            fh.write(f'hdd_path = "{hdd_path}"\n')
            fh.write('dvd_path = ""\n')
            fh.write("\n[net]\nenabled = false\n")

    return None, str(vm_hdd), str(toml_path)


def provision_platform(platform: Platform, db: Session | None = None) -> tuple[str | None, str | None, str | None]:
    """Provision a working image for a platform, selecting the backend by era."""
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
