import configparser
import sys
from pathlib import Path
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
_GAME_CDROM_KEY = "cdrom_01_image_path"


def _run(tmp_path: Path, monkeypatch, *, mbr: bool, iso: bool = False, media_path: Path | None = None):
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

    box86_mod._prepare_config(
        working_image_path=img,
        config_path=cfg,
        rom_path=rom_dir,
        hardware_profile="standard",
        platform_name="test-platform",
        base_image_path=iso_path,
        media_path=media_path,
    )
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


# ---------------------------------------------------------------------------
# Game/app media (cdrom_01) — independent of base_image_path/cdrom_02
# ---------------------------------------------------------------------------

class TestPrepareConfigGameMedia:
    def test_iso_media_is_mounted_on_cdrom_01(self, tmp_path, monkeypatch):
        media = tmp_path / "game.iso"
        media.write_bytes(b"\x00" * 2048)
        cfg, _, _ = _run(tmp_path, monkeypatch, mbr=True, media_path=media)
        parser = _parse(cfg)
        assert parser.has_option(_CDROM_SECTION, _GAME_CDROM_KEY)
        expected = str(media.resolve()).replace("\\", "/")
        assert parser.get(_CDROM_SECTION, _GAME_CDROM_KEY) == expected
        assert parser.get(_CDROM_SECTION, "cdrom_01_parameters") == "1, atapi"
        assert parser.get(_CDROM_SECTION, "cdrom_01_ide_channel") == "1:0"

    def test_cue_media_is_mounted_on_cdrom_01(self, tmp_path, monkeypatch):
        media = tmp_path / "game.cue"
        media.write_bytes(b"")
        cfg, _, _ = _run(tmp_path, monkeypatch, mbr=True, media_path=media)
        parser = _parse(cfg)
        assert parser.has_option(_CDROM_SECTION, _GAME_CDROM_KEY)

    def test_no_media_path_writes_nothing_on_cdrom_01(self, tmp_path, monkeypatch):
        cfg, _, _ = _run(tmp_path, monkeypatch, mbr=True, media_path=None)
        parser = _parse(cfg)
        has_cdrom_01 = (
            parser.has_section(_CDROM_SECTION)
            and parser.has_option(_CDROM_SECTION, _GAME_CDROM_KEY)
        )
        assert not has_cdrom_01

    def test_non_disc_media_is_skipped(self, tmp_path, monkeypatch):
        media = tmp_path / "install.exe"
        media.write_bytes(b"")
        cfg, _, _ = _run(tmp_path, monkeypatch, mbr=True, media_path=media)
        parser = _parse(cfg)
        has_cdrom_01 = (
            parser.has_section(_CDROM_SECTION)
            and parser.has_option(_CDROM_SECTION, _GAME_CDROM_KEY)
        )
        assert not has_cdrom_01

    def test_directory_media_is_skipped(self, tmp_path, monkeypatch):
        media = tmp_path / "loose_game_dir"
        media.mkdir()
        cfg, _, _ = _run(tmp_path, monkeypatch, mbr=True, media_path=media)
        parser = _parse(cfg)
        has_cdrom_01 = (
            parser.has_section(_CDROM_SECTION)
            and parser.has_option(_CDROM_SECTION, _GAME_CDROM_KEY)
        )
        assert not has_cdrom_01

    def test_cdrom_01_cleared_when_switching_from_media_to_no_media(self, tmp_path, monkeypatch):
        """A later launch of a different (or no) game must not inherit a
        prior launch's cdrom_01 entry — same reset guarantee cdrom_02
        already has for base_image_path."""
        import backend.service.backends.box86 as box86_mod
        monkeypatch.setattr(box86_mod, "get_86box_profile", lambda _: _FAKE_PROFILE)

        media = tmp_path / "game.iso"
        media.write_bytes(b"\x00" * 2048)
        cfg, img, _ = _run(tmp_path, monkeypatch, mbr=True, media_path=media)
        assert _parse(cfg).has_option(_CDROM_SECTION, _GAME_CDROM_KEY)

        rom_dir = tmp_path / "roms"
        box86_mod._prepare_config(
            working_image_path=img,
            config_path=cfg,
            rom_path=rom_dir,
            hardware_profile="standard",
            platform_name="test-platform",
            base_image_path=None,
            media_path=None,
        )
        parser = _parse(cfg)
        has_cdrom_01 = (
            parser.has_section(_CDROM_SECTION)
            and parser.has_option(_CDROM_SECTION, _GAME_CDROM_KEY)
        )
        assert not has_cdrom_01

    def test_game_media_coexists_with_base_image_on_cdrom_02(self, tmp_path, monkeypatch):
        """cdrom_01 (game media) and cdrom_02 (base OS-install ISO) are
        independent slots and can both be populated in the same launch."""
        media = tmp_path / "game.iso"
        media.write_bytes(b"\x00" * 2048)
        cfg, _, iso_path = _run(tmp_path, monkeypatch, mbr=False, iso=True, media_path=media)
        parser = _parse(cfg)
        assert parser.has_option(_CDROM_SECTION, _GAME_CDROM_KEY)
        assert parser.has_option(_CDROM_SECTION, _CDROM_KEY)
        expected_base = str(iso_path.resolve()).replace("\\", "/")
        assert parser.get(_CDROM_SECTION, _CDROM_KEY) == expected_base
        assert parser.get(_CDROM_SECTION, "cdrom_01_ide_channel") != parser.get(_CDROM_SECTION, "cdrom_02_ide_channel")
