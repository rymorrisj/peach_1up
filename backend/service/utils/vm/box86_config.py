"""86Box config preparation logic used at launch time."""

import configparser
from pathlib import Path

from backend.service.utils.disk_utils import has_valid_mbr
from backend.service.utils.emulator_catalog import get_86box_profile
from backend.service.utils.ini_writer import write_ini


def _ensure_section(parser: configparser.RawConfigParser, section: str) -> None:
    if not parser.has_section(section):
        parser.add_section(section)


def _set_if_absent(parser: configparser.RawConfigParser, section: str, key: str, value: str) -> None:
    if not parser.has_option(section, key) or parser.get(section, key) == "":
        parser.set(section, key, value)


def _prepare_config(platform, cfg_path: str, rom_path: Path) -> None:
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
    _set_if_absent(parser, "Machine", "machine",         hw_profile["machine"])
    _set_if_absent(parser, "Machine", "cpu_family",      hw_profile["cpu_family"])
    _set_if_absent(parser, "Machine", "cpu_speed",       str(hw_profile["cpu_speed"]))
    _set_if_absent(parser, "Machine", "cpu_multi",       str(hw_profile["cpu_multi"]))
    _set_if_absent(parser, "Machine", "mem_size",        str(hw_profile["mem_size"]))
    _set_if_absent(parser, "Machine", "cpu_use_dynarec", str(hw_profile["cpu_use_dynarec"]))
    _set_if_absent(parser, "Machine", "fpu_type",        hw_profile["fpu_type"])

    _ensure_section(parser, "Video")
    _set_if_absent(parser, "Video", "gfxcard",      hw_profile["gfxcard"])
    _set_if_absent(parser, "Video", "vid_renderer", hw_profile["vid_renderer"])

    _ensure_section(parser, "Sound")
    _set_if_absent(parser, "Sound", "sndcard", hw_profile["sndcard"])

    for _stale in ("Keyboard", "Mouse"):
        if parser.has_section(_stale):
            parser.remove_section(_stale)
    _ensure_section(parser, "Input devices")
    _set_if_absent(parser, "Input devices", "mouse_type",    "ps2")
    _set_if_absent(parser, "Input devices", "keyboard_type", "keyboard_ps2")

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
    parser.set("Network", "net_card", "none")
    parser.set("Network", "net_01_link", "0")

    write_ini(cp, parser)
