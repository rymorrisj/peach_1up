"""Network isolation regression tests for backend/service/backends/.

SECURITY.md, "Network isolation is emulator-native": each emulator disables
its own network adapter when enable_networking is false on the active
profile, rather than relying on a host firewall rule. Covers the
config-writing side of that contract for box86.py (86Box, [Network]
net_type), console.py (PCSX2, [DEV9/Eth] EthEnable), and flycast.py
([network] Enable/GGPO).

box86's hardware/media config behavior is in test_prepare_config.py.

Config-writing functions only (_prepare_config, ini_writer.set_ini_key), no
launch() call, so no process, thread, or Win32 handle is created.
"""

import configparser
import sys
from pathlib import Path
from unittest.mock import MagicMock

# pycdlib is an optional runtime dependency not available in the test
# environment; stub it so `import backend.service.backends.box86` succeeds,
# same as test_prepare_config.py.
if "pycdlib" not in sys.modules:
    _pycdlib_stub = MagicMock()
    sys.modules["pycdlib"] = _pycdlib_stub
    sys.modules["pycdlib.pycdlibexception"] = _pycdlib_stub


_FAKE_86BOX_PROFILE = {
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


def _parse(cfg: Path) -> configparser.RawConfigParser:
    parser = configparser.RawConfigParser()
    parser.optionxform = str
    parser.read(str(cfg), encoding="utf-8")
    return parser


# ---------------------------------------------------------------------------
# 86Box: [Network] net_type, written unconditionally by _prepare_config
# ---------------------------------------------------------------------------
#
# _prepare_config takes no enable_networking parameter: "disabled" is its
# unconditional default (SECURITY.md, "net_type = none in [Network], written
# on every launch"). The "slirp" override for a networked profile is a
# separate patch_ini() call in launch(), gated on spec.enable_networking and
# unreachable without spawning 86Box, so only _prepare_config is exercised.
#
# INTEGRATION TEST NEEDED: that launch() writes net_type = slirp when and
# only when spec.enable_networking is true, over a config _prepare_config
# just wrote none into. Needs a real launch (the gate and the patch_ini call
# live inside it), asserting the on-disk value for both flag states.

class TestBox86NetworkIsolation:
    def _run(self, tmp_path: Path, monkeypatch) -> Path:
        import backend.service.backends.box86 as box86_mod
        monkeypatch.setattr(box86_mod, "get_86box_profile", lambda _: _FAKE_86BOX_PROFILE)

        img = tmp_path / "disk.vhd"
        img.write_bytes(b"\x00" * 512)

        cfg = tmp_path / "86box.cfg"
        cfg.write_text("[General]\nversion = 1\n", encoding="utf-8")

        rom_dir = tmp_path / "roms"
        rom_dir.mkdir()

        box86_mod._prepare_config(
            working_image_path=img,
            config_path=cfg,
            rom_path=rom_dir,
            hardware_profile="standard",
            platform_name="test-platform",
            base_image_path=None,
            media_path=None,
        )
        return cfg

    def test_net_type_is_none_after_prepare(self, tmp_path, monkeypatch):
        cfg = self._run(tmp_path, monkeypatch)
        assert _parse(cfg).get("Network", "net_type") == "none"

    def test_net_type_stays_none_when_networking_not_overridden(self, tmp_path, monkeypatch):
        """The enable_networking=False case: nothing runs after
        _prepare_config, so its default is the value 86Box sees."""
        cfg = self._run(tmp_path, monkeypatch)
        assert _parse(cfg).get("Network", "net_type") == "none"


# ---------------------------------------------------------------------------
# PCSX2 (console.py): [DEV9/Eth] EthEnable, written via set_ini_key
# ---------------------------------------------------------------------------
#
# console.py's disable write is an inline set_ini_key(...) guarded by
# `if not spec.enable_networking`, with no helper to call. These tests call
# set_ini_key with the exact section/key/value console.py passes, so they
# cover the write's correctness and non-destructiveness but not the gate.
#
# INTEGRATION TEST NEEDED: that launch() writes EthEnable = false when and
# only when spec.enable_networking is false. Same for flycast.py below
# ([network] Enable/GGPO). Needs a real launch to reach the gate.

class TestPcsx2NetworkIsolation:
    def test_eth_enable_false_written_to_dev9_eth_section(self, tmp_path):
        from backend.service.utils.ini_writer import set_ini_key
        ini_path = tmp_path / "PCSX2.ini"
        set_ini_key(ini_path, "DEV9/Eth", "EthEnable", "false")
        parser = _parse(ini_path)
        assert parser.get("DEV9/Eth", "EthEnable") == "false"

    def test_preexisting_unrelated_key_in_same_section_is_untouched(self, tmp_path):
        from backend.service.utils.ini_writer import set_ini_key
        ini_path = tmp_path / "PCSX2.ini"
        ini_path.write_text("[DEV9/Eth]\nEthApi = PCAP\n", encoding="utf-8")

        set_ini_key(ini_path, "DEV9/Eth", "EthEnable", "false")

        parser = _parse(ini_path)
        assert parser.get("DEV9/Eth", "EthApi") == "PCAP"
        assert parser.get("DEV9/Eth", "EthEnable") == "false"


# ---------------------------------------------------------------------------
# Flycast: [network] Enable / GGPO, written via set_ini_key
# ---------------------------------------------------------------------------
#
# Same shape as PCSX2 above: two inline set_ini_key(...) calls behind the
# same gate, exercised here with flycast.py's exact literals.

class TestFlycastNetworkIsolation:
    def test_enable_and_ggpo_written_no(self, tmp_path):
        from backend.service.utils.ini_writer import set_ini_key
        ini_path = tmp_path / "emu.cfg"
        set_ini_key(ini_path, "network", "Enable", "no")
        set_ini_key(ini_path, "network", "GGPO", "no")

        parser = _parse(ini_path)
        assert parser.get("network", "Enable") == "no"
        assert parser.get("network", "GGPO") == "no"

    def test_preexisting_unrelated_key_in_same_section_is_untouched(self, tmp_path):
        from backend.service.utils.ini_writer import set_ini_key
        ini_path = tmp_path / "emu.cfg"
        ini_path.write_text("[network]\nActAsServer = no\n", encoding="utf-8")

        set_ini_key(ini_path, "network", "Enable", "no")
        set_ini_key(ini_path, "network", "GGPO", "no")

        parser = _parse(ini_path)
        assert parser.get("network", "ActAsServer") == "no"
        assert parser.get("network", "Enable") == "no"
        assert parser.get("network", "GGPO") == "no"
