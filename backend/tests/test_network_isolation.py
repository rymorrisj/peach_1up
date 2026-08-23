"""Network isolation regression tests for backend/service/backends/.

SECURITY.md, "Network isolation is emulator-native": each emulator disables
its own network adapter when enable_networking is false on the active
profile, rather than relying on a host firewall rule. This file locks in the
config-writing side of that contract for the three backends whose isolation
write had zero coverage: box86.py (86Box, [Network] net_type), console.py
(PCSX2, [DEV9/Eth] EthEnable), and flycast.py ([network] Enable/GGPO).

Kept separate from test_prepare_config.py, which is scoped to box86's
general _prepare_config hardware/media behavior, not the cross-backend
network-isolation invariant this file is about (matches the grouping
SECURITY.md itself uses, one table row per emulator).

Only pure config-writing functions are exercised (_prepare_config,
ini_writer.set_ini_key). None of these tests call launch() or spawn a
process, thread, or Win32 handle.
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
# _prepare_config has no enable_networking parameter at all: the "networking
# disabled" state is simply _prepare_config's unconditional default. The
# override to "slirp" for an explicitly networked profile happens separately
# in launch() via patch_ini(), a one-line call gated on spec.enable_networking
# that is not reachable without invoking launch() (which would spawn 86Box).
# Both tests below therefore exercise _prepare_config only, matching
# SECURITY.md: "net_type = none in [Network], written on every launch."

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
        """Equivalent to a profile with enable_networking=False: launch()'s
        only networking-related step (the patch_ini override to "slirp") is
        conditional on enable_networking being truthy, so for the disabled
        case nothing runs after _prepare_config and its default must hold."""
        cfg = self._run(tmp_path, monkeypatch)
        assert _parse(cfg).get("Network", "net_type") == "none"


# ---------------------------------------------------------------------------
# PCSX2 (console.py): [DEV9/Eth] EthEnable, written via set_ini_key
# ---------------------------------------------------------------------------
#
# The disable write in console.py is a single inline set_ini_key(...) call
# guarded by `if not spec.enable_networking`, not a separate helper function.
# Isolating "just that computation" (per the task's own instruction for this
# shape of override logic) means calling set_ini_key directly with the exact
# section/key/value console.py uses, rather than invoking launch() (which
# would spawn PCSX2). This does not exercise the enable_networking gate
# itself, only the write's correctness and non-destructiveness.

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
# Same shape as PCSX2 above: flycast.py's disable path is two inline
# set_ini_key(...) calls guarded by `if not spec.enable_networking`, isolated
# here by calling set_ini_key directly with flycast.py's exact literals.

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
