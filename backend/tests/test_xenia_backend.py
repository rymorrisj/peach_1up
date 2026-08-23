"""Unit tests for backend/service/backends/xenia.py's launch() media guards.

xenia.py has no config-preparation step analogous to box86's _prepare_config
(test_prepare_config.py's pattern): it never writes a portable content/cache
directory itself. Those directories (emulators/xenia/content,
emulators/xenia/cache) are resolved generically for every emulator slug by
resolve_derived_path() in backend/service/utils/emulator_paths.py, not by
xenia.py, so there is nothing xenia-specific to write and read back here.

What launch() does own is failing loudly before it ever builds args or a
sandbox config: every check below (missing media, nonexistent media,
unsupported extension, an extracted XEX folder with no bootable title) is
raised before build_media_broker_config or launch_under_job_object are
reached, so those (and wincage's SandboxProcess/WindowsJobObject) never need
to be touched.
"""

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
