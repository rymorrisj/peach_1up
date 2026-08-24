"""Unit tests for backend/service/backends/xenia.py's launch() preflight
guards and _warn_if_risky_gpu.

xenia.py has no config-preparation step to test the way box86 does
(test_prepare_config.py): its content/cache directories are resolved
generically for every slug by resolve_derived_path() in emulator_paths.py.

What launch() does own is failing loudly first. Every guard below (missing
executable, missing media, nonexistent media, unsupported extension, an
extracted XEX folder with no bootable title) raises before
build_media_broker_config or launch_under_job_object, so no wincage
SandboxProcess or WindowsJobObject is ever constructed.
"""

import logging
from pathlib import Path

import pytest


def _make_install_path(tmp_path: Path) -> Path:
    install_dir = tmp_path / "emulators" / "xenia"
    install_dir.mkdir(parents=True)
    exe = install_dir / "xenia.exe"
    exe.write_bytes(b"")
    return exe


def _patch_common(monkeypatch, xenia_mod, install_path: Path):
    monkeypatch.setattr(xenia_mod, "get_emulator", lambda slug: {"display_name": "Xenia"})
    monkeypatch.setattr(xenia_mod, "get_install_path", lambda slug: install_path)


class TestXeniaLaunchExecutableGuard:
    def test_uninstalled_executable_raises_before_any_media_check(self, tmp_path, monkeypatch):
        """get_install_path returns None until the emulator is downloaded.
        This must be the first guard, so an uninstalled Xenia reports itself
        as uninstalled rather than as a media problem."""
        import backend.service.backends.xenia as xenia_mod
        from backend.service.launch.launch_spec import LaunchSpec

        monkeypatch.setattr(xenia_mod, "get_emulator", lambda slug: {"display_name": "Xenia"})
        monkeypatch.setattr(xenia_mod, "get_install_path", lambda slug: None)

        spec = LaunchSpec(slug="xenia", era="xbox360", media_path=None)

        with pytest.raises(FileNotFoundError, match="executable not found"):
            xenia_mod.launch(spec)

    def test_install_path_that_is_a_directory_raises(self, tmp_path, monkeypatch):
        """A path that exists but is not a file (a half-extracted install
        leaving only the directory) must be rejected the same way."""
        import backend.service.backends.xenia as xenia_mod
        from backend.service.launch.launch_spec import LaunchSpec

        install_dir = tmp_path / "emulators" / "xenia"
        install_dir.mkdir(parents=True)
        monkeypatch.setattr(xenia_mod, "get_emulator", lambda slug: {"display_name": "Xenia"})
        monkeypatch.setattr(xenia_mod, "get_install_path", lambda slug: install_dir)

        spec = LaunchSpec(slug="xenia", era="xbox360", media_path=None)

        with pytest.raises(FileNotFoundError, match="executable not found"):
            xenia_mod.launch(spec)


class TestXeniaLaunchMediaGuards:
    def test_missing_media_path_raises_file_not_found(self, tmp_path, monkeypatch):
        import backend.service.backends.xenia as xenia_mod
        from backend.service.launch.launch_spec import LaunchSpec

        install_path = _make_install_path(tmp_path)
        _patch_common(monkeypatch, xenia_mod, install_path)

        spec = LaunchSpec(slug="xenia", era="xbox360", media_path=None)

        with pytest.raises(FileNotFoundError, match="requires a disc image"):
            xenia_mod.launch(spec)

    def test_nonexistent_media_path_raises_file_not_found(self, tmp_path, monkeypatch):
        import backend.service.backends.xenia as xenia_mod
        from backend.service.launch.launch_spec import LaunchSpec

        install_path = _make_install_path(tmp_path)
        _patch_common(monkeypatch, xenia_mod, install_path)

        missing_media = tmp_path / "does_not_exist.iso"
        spec = LaunchSpec(slug="xenia", era="xbox360", media_path=missing_media)

        with pytest.raises(FileNotFoundError, match="Media file not found"):
            xenia_mod.launch(spec)

    def test_unsupported_media_extension_raises_value_error(self, tmp_path, monkeypatch):
        import backend.service.backends.xenia as xenia_mod
        from backend.service.launch.launch_spec import LaunchSpec

        install_path = _make_install_path(tmp_path)
        _patch_common(monkeypatch, xenia_mod, install_path)
        monkeypatch.setattr(xenia_mod, "supported_extensions_for_era", lambda era: frozenset({".iso"}))

        media = tmp_path / "game.bin"
        media.write_bytes(b"\x00")
        spec = LaunchSpec(slug="xenia", era="xbox360", media_path=media)

        with pytest.raises(ValueError, match="Unsupported media format"):
            xenia_mod.launch(spec)

    def test_directory_without_bootable_xex_raises_file_not_found(self, tmp_path, monkeypatch):
        import backend.service.backends.xenia as xenia_mod
        from backend.service.launch.launch_spec import LaunchSpec

        install_path = _make_install_path(tmp_path)
        _patch_common(monkeypatch, xenia_mod, install_path)
        monkeypatch.setattr(xenia_mod, "resolve_xex_target", lambda media_dir: None)

        media_dir = tmp_path / "extracted_game"
        media_dir.mkdir()
        spec = LaunchSpec(slug="xenia", era="xbox360", media_path=media_dir)

        with pytest.raises(FileNotFoundError, match="No bootable Xbox 360 title found"):
            xenia_mod.launch(spec)


class TestWarnIfRiskyGpu:
    """The module docstring pins this as warn-only: it must never write to
    xenia.config.toml, whatever it finds there."""

    def _write_config(self, tmp_path: Path, text: str) -> Path:
        install_dir = tmp_path / "emulators" / "xenia"
        install_dir.mkdir(parents=True)
        (install_dir / "xenia.config.toml").write_text(text, encoding="utf-8")
        return install_dir

    def test_absent_gpu_key_is_treated_as_the_risky_default(self, tmp_path, caplog):
        """Xenia's own default is "any", so a config with no [GPU].gpu is the
        crash-prone case, not a safe one."""
        import backend.service.backends.xenia as xenia_mod

        install_dir = self._write_config(tmp_path, "[GPU]\nvsync = true\n")

        # get_logger() caps this module's logger at ERROR outside
        # PEACH_ENV=development, so caplog must name it (see test_xex.py).
        with caplog.at_level(logging.WARNING, logger="backend.service.backends.xenia"):
            xenia_mod._warn_if_risky_gpu(install_dir)

        assert any("AMD driver timeout" in rec.getMessage() for rec in caplog.records)

    def test_vulkan_does_not_warn(self, tmp_path, caplog):
        import backend.service.backends.xenia as xenia_mod

        install_dir = self._write_config(tmp_path, '[GPU]\ngpu = "vulkan"\n')

        with caplog.at_level(logging.WARNING, logger="backend.service.backends.xenia"):
            xenia_mod._warn_if_risky_gpu(install_dir)

        assert not any("AMD driver timeout" in rec.getMessage() for rec in caplog.records)

    def test_malformed_config_is_swallowed_not_raised(self, tmp_path):
        """A hand-broken config must not block a launch from a warn-only step."""
        import backend.service.backends.xenia as xenia_mod

        install_dir = self._write_config(tmp_path, "this is not valid toml [[[")

        xenia_mod._warn_if_risky_gpu(install_dir)

    def test_absent_config_file_is_a_noop(self, tmp_path):
        import backend.service.backends.xenia as xenia_mod

        install_dir = tmp_path / "emulators" / "xenia"
        install_dir.mkdir(parents=True)

        xenia_mod._warn_if_risky_gpu(install_dir)

        assert list(install_dir.iterdir()) == []


# INTEGRATION TEST NEEDED: everything past the guards. Nothing here confirms
# launch() passes --target=<resolved path> (the .xex, not the folder, for a
# directory source), or that build_media_broker_config receives target_path
# rather than spec.media_path, which is what gives the broker a file handle
# instead of failing on a directory. Needs a real launch_under_job_object
# call to observe the args and the SandboxConfig it is handed.
