"""Unit tests for backend/service/utils/vm/provisioner.py.

Covers _resolve_within's traversal guard and success path,
_load_default_disk_size_mb against the real eras.yaml (same pattern
test_sandbox.py uses for _load_era_limits), and provision_86box_vm's path
structure with the actual image-byte write stubbed out.
"""

from pathlib import Path
import types

import pytest


# ---------------------------------------------------------------------------
# _resolve_within
# ---------------------------------------------------------------------------

class TestResolveWithin:
    def test_escaping_path_raises_and_names_target_and_base(self, tmp_path):
        from backend.service.utils.vm.provisioner import _resolve_within

        base = tmp_path / "vms"
        base.mkdir()

        with pytest.raises(ValueError) as excinfo:
            _resolve_within(base, "..", "escape")

        message = str(excinfo.value)
        expected_target = (base.resolve().parent / "escape").resolve()
        assert str(expected_target) in message
        assert str(base.resolve()) in message

    def test_path_within_base_resolves(self, tmp_path):
        from backend.service.utils.vm.provisioner import _resolve_within

        base = tmp_path / "vms"
        base.mkdir()

        result = _resolve_within(base, "my-slug", "86box.cfg")
        assert result == (base.resolve() / "my-slug" / "86box.cfg").resolve()


# ---------------------------------------------------------------------------
# _load_default_disk_size_mb
# ---------------------------------------------------------------------------

class TestLoadDefaultDiskSizeMb:
    def test_known_era_returns_real_default_from_eras_yaml(self):
        from backend.service.utils.vm.provisioner import _load_default_disk_size_mb
        # config/eras.yaml: win95.default_disk_size_mb == 1024
        assert _load_default_disk_size_mb("win95") == 1024

    def test_unknown_era_raises_file_not_found_naming_the_era(self):
        from backend.service.utils.vm.provisioner import _load_default_disk_size_mb
        with pytest.raises(FileNotFoundError, match="nonexistent_era_xyz"):
            _load_default_disk_size_mb("nonexistent_era_xyz")


# ---------------------------------------------------------------------------
# provision_86box_vm, path structure (image bytes stubbed)
# ---------------------------------------------------------------------------

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


class TestProvision86BoxVmPathStructure:
    """provision_86box_vm is exercised here rather than provision_dosbox_drive:
    only the 86Box path writes under emulators/86box/vms/<slug>/, the
    documented VM directory layout (CHANGELOG.md, 2026-05-19). DOS's
    provision_dosbox_drive writes to platform.working_image_path directly, a
    caller-supplied path with no such layout to assert on.

    The real image write is two steps, _build_vhd_footer (footer bytes) then
    an inline seek/write in provision_86box_vm sized off the disk size. Both
    are neutralized here: _build_vhd_footer is stubbed, and
    _load_default_disk_size_mb is monkeypatched to 1 MB so even the
    unstubbed seek/write stays tiny.
    """

    def test_image_and_config_land_under_vms_slug_dir_not_cwd(self, tmp_path, monkeypatch):
        import backend.service.utils.vm.provisioner as provisioner_mod

        monkeypatch.setattr(provisioner_mod, "get_base_path", lambda: tmp_path)
        monkeypatch.setattr(provisioner_mod, "get_86box_profile", lambda _: _FAKE_PROFILE)
        monkeypatch.setattr(provisioner_mod, "_load_default_disk_size_mb", lambda era: 1)

        footer_calls = []

        def _fake_build_vhd_footer(size_bytes):
            footer_calls.append(size_bytes)
            return b"\x00" * 512

        monkeypatch.setattr(provisioner_mod, "_build_vhd_footer", _fake_build_vhd_footer)

        platform = types.SimpleNamespace(
            era="win95",
            slug="my-test-env",
            id=42,
            base_image_path=None,
            machine_override=None,
        )

        iso_path, vhd_path_str, cfg_path_str = provisioner_mod.provision_86box_vm(
            platform, box86_path="unused", rom_path=str(tmp_path / "roms"), hardware_profile="standard",
        )

        expected_vm_dir = (tmp_path / "emulators" / "86box" / "vms" / "my-test-env").resolve()
        vhd_path = Path(vhd_path_str)
        cfg_path = Path(cfg_path_str)

        assert iso_path is None
        assert vhd_path.parent == expected_vm_dir
        assert cfg_path.parent == expected_vm_dir
        assert vhd_path.name == "disk.vhd"
        assert cfg_path.name == "86box.cfg"
        assert vhd_path.exists()
        assert cfg_path.exists()
        assert footer_calls == [1 * 1024 * 1024]

        cwd = Path.cwd().resolve()
        assert cwd not in vhd_path.parents
        assert cwd not in cfg_path.parents
