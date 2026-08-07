"""Tests for H4: game_executable sanitisation in dosbox.py.

Tests verify that game_executable values are sanitised before reaching the
autoexec block. Tests cover _validate_game_executable directly and the
write_launch_conf call path.
"""

import shutil
import pytest

from backend.service.backends.dosbox import _validate_game_executable, write_launch_conf
from backend.service.launch.launch_spec import LaunchSpec


# ---------------------------------------------------------------------------
# _validate_game_executable, direct unit tests
# ---------------------------------------------------------------------------

class TestValidateGameExecutable:
    def test_clean_path_passes(self):
        _validate_game_executable("GAME.EXE", "C:")

    def test_clean_path_with_subdirectory_passes(self):
        _validate_game_executable("GAMES\\DOOM\\DOOM.EXE", "C:")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            _validate_game_executable("", "C:")

    def test_newline_raises(self):
        with pytest.raises(ValueError, match="newline"):
            _validate_game_executable("GAME.EXE\nBAD", "C:")

    def test_carriage_return_raises(self):
        with pytest.raises(ValueError, match="newline"):
            _validate_game_executable("GAME.EXE\rBAD", "C:")

    def test_null_byte_raises(self):
        with pytest.raises(ValueError):
            _validate_game_executable("GAME\x00.EXE", "C:")

    def test_bracket_prefix_raises(self):
        with pytest.raises(ValueError, match="meta-character"):
            _validate_game_executable("[autoexec]", "C:")

    def test_at_prefix_raises(self):
        with pytest.raises(ValueError, match="meta-character"):
            _validate_game_executable("@echo off", "C:")

    def test_wrong_drive_raises(self):
        with pytest.raises(ValueError, match="drive"):
            _validate_game_executable("D:\\GAME.EXE", "C:")

    def test_matching_drive_passes(self):
        _validate_game_executable("C:\\GAME.EXE", "C:")

    def test_none_raises(self):
        with pytest.raises(ValueError):
            _validate_game_executable(None, "C:")

    def test_hash_character_raises(self):
        with pytest.raises(ValueError, match="#"):
            _validate_game_executable("GAME.EXE # comment", "C:")


# ---------------------------------------------------------------------------
# write_launch_conf, game_executable pipeline tests
# ---------------------------------------------------------------------------

class TestWriteLaunchConfGameExecutable:
    def _conf_content(self, tmp_path, game_executable=None, suffix=".img"):
        media = tmp_path / f"game{suffix}"
        exe = tmp_path / "dosbox-x.exe"
        spec = LaunchSpec(
            slug="dosbox-x",
            era="dos",
            media_path=media,
            executable_path=str(exe),
        )
        conf_path = write_launch_conf(spec, game_executable=game_executable)
        try:
            return conf_path.read_text(encoding="utf-8")
        finally:
            shutil.rmtree(str(conf_path.parent), ignore_errors=True)

    def _autoexec_lines(self, content):
        """Return non-empty lines from the [autoexec] section."""
        idx = content.index("[autoexec]")
        section = content[idx:]
        return [line.strip() for line in section.splitlines() if line.strip()]

    def test_clean_executable_appears_in_autoexec(self, tmp_path):
        content = self._conf_content(tmp_path, game_executable="GAME.EXE")
        lines = self._autoexec_lines(content)
        assert "GAME.EXE" in lines

    def test_clean_executable_appears_after_drive_letter(self, tmp_path):
        content = self._conf_content(tmp_path, game_executable="GAME.EXE")
        lines = self._autoexec_lines(content)
        drive_idx = lines.index("C:")
        exe_idx = lines.index("GAME.EXE")
        assert exe_idx > drive_idx

    def test_executable_with_spaces_passes_through(self, tmp_path):
        content = self._conf_content(tmp_path, game_executable="MY GAME.EXE")
        lines = self._autoexec_lines(content)
        assert "MY GAME.EXE" in lines

    def test_none_executable_not_in_autoexec(self, tmp_path):
        content = self._conf_content(tmp_path, game_executable=None)
        lines = self._autoexec_lines(content)
        # Only [autoexec] header, mount line, and drive letter
        assert len(lines) == 3

    def test_empty_executable_not_in_autoexec(self, tmp_path):
        content = self._conf_content(tmp_path, game_executable="")
        lines = self._autoexec_lines(content)
        assert len(lines) == 3

    def test_newline_in_executable_raises_before_write(self, tmp_path):
        with pytest.raises(ValueError, match="newline"):
            self._conf_content(tmp_path, game_executable="GAME.EXE\nINJECTED")

    def test_iso_media_uses_d_drive(self, tmp_path):
        content = self._conf_content(tmp_path, game_executable="GAME.EXE", suffix=".iso")
        lines = self._autoexec_lines(content)
        assert "D:" in lines
        assert "GAME.EXE" in lines
