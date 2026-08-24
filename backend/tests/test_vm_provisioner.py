"""Unit tests for backend/service/utils/vm/provisioner.py.

Covers _resolve_within's traversal guard, _load_default_disk_size_mb against
the real eras.yaml (the pattern test_sandbox.py uses for _load_era_limits),
provision_86box_vm's path structure with the image write stubbed out, and
provision_dosbox_drive's preconditions.
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
        """Unpatched, against the shipped config/eras.yaml."""
        from backend.service.utils.vm.provisioner import _load_default_disk_size_mb
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
    """Only the 86Box path has a fixed layout to assert on
    (emulators/86box/vms/<slug>/); provision_dosbox_drive writes to a
    caller-supplied working_image_path.

    The image write is stubbed two ways so nothing large lands on disk:
    _build_vhd_footer returns fixed bytes, and the disk size is patched to
    1 MB so the inline seek/write stays tiny.
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

    def test_unsupported_era_raises_before_any_directory_is_created(self, tmp_path, monkeypatch):
        import backend.service.utils.vm.provisioner as provisioner_mod

        monkeypatch.setattr(provisioner_mod, "get_base_path", lambda: tmp_path)
        platform = types.SimpleNamespace(era="ps2", slug="my-test-env", id=42)

        with pytest.raises(ValueError, match="unsupported era 'ps2'"):
            provisioner_mod.provision_86box_vm(
                platform, box86_path="unused", rom_path=str(tmp_path / "roms"),
            )

        assert not (tmp_path / "emulators").exists()


# ---------------------------------------------------------------------------
# provision_dosbox_drive preconditions
# ---------------------------------------------------------------------------

class TestProvisionDosboxDrive:
    def test_existing_working_image_is_returned_without_reformatting(self, tmp_path, monkeypatch):
        """CLAUDE.md: never write to or overwrite an existing image. A second
        provision pass on an already-provisioned environment must be a no-op,
        not a reformat that discards the user's installed DOS software."""
        import backend.service.utils.vm.provisioner as provisioner_mod
        from backend.service.utils import fat as fat_mod

        existing = tmp_path / "drives" / "c.img"
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b"\xf8" * 1024)

        def _format_should_not_be_called(*a, **kw):
            raise AssertionError("format_fat16 must not touch an existing image")
        monkeypatch.setattr(fat_mod, "format_fat16", _format_should_not_be_called)

        platform = types.SimpleNamespace(
            era="dos", slug="my-dos-env", id=1, working_image_path=str(existing),
        )

        result = provisioner_mod.provision_dosbox_drive(platform)

        assert result == (None, str(existing.resolve()), None, None, None)
        assert existing.read_bytes() == b"\xf8" * 1024

    def test_missing_working_image_path_raises(self, tmp_path):
        """The path is preset when the environment row is seeded, so an unset
        one means seeding is broken; fail loudly rather than inventing a path."""
        import backend.service.utils.vm.provisioner as provisioner_mod

        platform = types.SimpleNamespace(
            era="dos", slug="my-dos-env", id=1, working_image_path=None,
        )

        with pytest.raises(RuntimeError, match="no.*working_image_path"):
            provisioner_mod.provision_dosbox_drive(platform)

    def test_unsupported_era_raises(self, tmp_path):
        import backend.service.utils.vm.provisioner as provisioner_mod

        platform = types.SimpleNamespace(
            era="win95", slug="my-env", id=1, working_image_path=str(tmp_path / "c.img"),
        )

        with pytest.raises(ValueError, match="unsupported era 'win95'"):
            provisioner_mod.provision_dosbox_drive(platform)


# INTEGRATION TEST NEEDED: the VHD write itself is stubbed above
# (_build_vhd_footer plus a 1 MB size), so nothing verifies that a
# full-size image with a real footer is one 86Box actually mounts, or that
# the insufficient-disk-space guards fire against a real volume.
