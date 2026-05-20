import configparser
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# pycdlib is an optional runtime dependency not available in the test environment.
# Stub it and its submodule so importing box86 -> media_attach succeeds.
if "pycdlib" not in sys.modules:
    _pycdlib_stub = MagicMock()
    sys.modules["pycdlib"] = _pycdlib_stub
    sys.modules["pycdlib.pycdlibexception"] = _pycdlib_stub


_FAKE_PROFILE = {
    "slug": "standard",
    "machine": "bf6",
    "cpu_family": "pentium2_deschutes",
    "cpu_speed": 300000000,
    "cpu_multi": 3.5,
    "cpu_use_dynarec": 1,
    "fpu_type": "internal",
    "mem_size": 131072,
    "gfxcard": "px_trio64vplus_pci",
    "vid_renderer": "qt_software",
    "sndcard": "sb16_pnp",
    "keyboard_type": "keyboard_ps2",
    "mouse_type": "ps2",
}

_CDROM_SECTION = "Floppy and CD-ROM drives"
_CDROM_KEY = "cdrom_02_image_path"


def _run(tmp_path: Path, monkeypatch, *, mbr: bool, iso: bool = False):
    """Set up a _prepare_config scenario and return (cfg_path, img_path, iso_path)."""
    import backend.service.backends.box86 as box86_mod
    monkeypatch.setattr(box86_mod, "get_86box_profile", lambda _: _FAKE_PROFILE)

    img = tmp_path / "disk.vhd"
    if mbr:
        data = bytearray(512)
        data[510] = 0x55
        data[511] = 0xAA
        img.write_bytes(bytes(data))
    else:
        img.write_bytes(b"\x00" * 512)

    cfg = tmp_path / "86box.cfg"
    cfg.write_text("[General]\nversion = 1\n", encoding="utf-8")

    rom_dir = tmp_path / "roms"
    rom_dir.mkdir()

    iso_path = None
    if iso:
        iso_path = tmp_path / "install.iso"
        iso_path.write_bytes(b"\x00" * 2048)

    platform = SimpleNamespace(
        working_image_path=str(img),
        base_image_path=str(iso_path) if iso_path else None,
        hardware_profile="standard",
        name="test-platform",
    )
    box86_mod._prepare_config(platform, str(cfg), rom_dir)
    return cfg, img, iso_path


def _parse(cfg: Path) -> configparser.RawConfigParser:
    parser = configparser.RawConfigParser()
    parser.optionxform = str
    parser.read(str(cfg), encoding="utf-8")
    return parser


# ---------------------------------------------------------------------------
# Case A — pre-installed image: MBR signature present
# ---------------------------------------------------------------------------

class TestPrepareConfigCaseA:
    def test_boot_order_is_hdd_first(self, tmp_path, monkeypatch):
        cfg, _, _ = _run(tmp_path, monkeypatch, mbr=True)
        assert _parse(cfg).get("General", "boot_order") == "hdd_cdrom_fdd"

    def test_hdd_fn_is_working_image_filename(self, tmp_path, monkeypatch):
        cfg, img, _ = _run(tmp_path, monkeypatch, mbr=True)
        assert _parse(cfg).get("Hard disks", "hdd_01_fn") == img.name

    def test_no_cdrom_image_path_written(self, tmp_path, monkeypatch):
        cfg, _, _ = _run(tmp_path, monkeypatch, mbr=True)
        parser = _parse(cfg)
        has_cdrom = (
            parser.has_section(_CDROM_SECTION)
            and parser.has_option(_CDROM_SECTION, _CDROM_KEY)
        )
        assert not has_cdrom


# ---------------------------------------------------------------------------
# Case B — blank disk with ISO: MBR absent, base_image_path set
# ---------------------------------------------------------------------------

class TestPrepareConfigCaseB:
    def test_boot_order_is_cdrom_first(self, tmp_path, monkeypatch):
        cfg, _, _ = _run(tmp_path, monkeypatch, mbr=False, iso=True)
        assert _parse(cfg).get("General", "boot_order") == "cdrom_fdd_hdd"

    def test_hdd_fn_is_disk_vhd(self, tmp_path, monkeypatch):
        cfg, _, _ = _run(tmp_path, monkeypatch, mbr=False, iso=True)
        assert _parse(cfg).get("Hard disks", "hdd_01_fn") == "disk.vhd"

    def test_cdrom_image_path_is_written(self, tmp_path, monkeypatch):
        cfg, _, iso_path = _run(tmp_path, monkeypatch, mbr=False, iso=True)
        parser = _parse(cfg)
        assert parser.has_section(_CDROM_SECTION)
        assert parser.has_option(_CDROM_SECTION, _CDROM_KEY)
        expected = str(iso_path.resolve()).replace("\\", "/")
        assert parser.get(_CDROM_SECTION, _CDROM_KEY) == expected


# ---------------------------------------------------------------------------
# Case C — blank disk, no ISO: MBR absent, no base_image_path
# ---------------------------------------------------------------------------

class TestPrepareConfigCaseC:
    def test_boot_order_is_cdrom_first(self, tmp_path, monkeypatch):
        cfg, _, _ = _run(tmp_path, monkeypatch, mbr=False)
        assert _parse(cfg).get("General", "boot_order") == "cdrom_fdd_hdd"

    def test_hdd_fn_is_disk_vhd(self, tmp_path, monkeypatch):
        cfg, _, _ = _run(tmp_path, monkeypatch, mbr=False)
        assert _parse(cfg).get("Hard disks", "hdd_01_fn") == "disk.vhd"

    def test_no_cdrom_image_path_written(self, tmp_path, monkeypatch):
        cfg, _, _ = _run(tmp_path, monkeypatch, mbr=False)
        parser = _parse(cfg)
        has_cdrom = (
            parser.has_section(_CDROM_SECTION)
            and parser.has_option(_CDROM_SECTION, _CDROM_KEY)
        )
        assert not has_cdrom
