"""Tests for backend.service.utils.smart_media_detector.iso_detect."""

import textwrap
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# _cue_bin_path — multi-FILE fallthrough
# ---------------------------------------------------------------------------

class TestCueBinPath:
    """Unit tests for the internal _cue_bin_path() helper."""

    def _call(self, cue_path: Path) -> Path | None:
        from backend.service.utils.smart_media_detector.iso_detect import _cue_bin_path
        return _cue_bin_path(cue_path)

    def test_returns_none_when_no_file_lines(self, tmp_path: Path):
        cue = tmp_path / "game.cue"
        cue.write_text("TRACK 01 MODE2/2352\n  INDEX 01 00:00:00\n")
        assert self._call(cue) is None

    def test_returns_first_file_when_it_exists(self, tmp_path: Path):
        bin_file = tmp_path / "game.bin"
        bin_file.write_bytes(b"\x00" * 16)
        cue = tmp_path / "game.cue"
        cue.write_text(f'FILE "{bin_file.name}" BINARY\n  TRACK 01 MODE2/2352\n')
        result = self._call(cue)
        assert result == bin_file

    def test_falls_through_to_second_file_when_first_missing(self, tmp_path: Path):
        """The primary regression test: first FILE entry points to a nonexistent
        path; _cue_bin_path() must continue and return the second entry."""
        real_bin = tmp_path / "game_track02.bin"
        real_bin.write_bytes(b"\x00" * 16)

        cue_content = textwrap.dedent(f"""\
            FILE "MISSING_track01.bin" BINARY
              TRACK 01 MODE2/2352
                INDEX 01 00:00:00
            FILE "{real_bin.name}" BINARY
              TRACK 02 MODE2/2352
                INDEX 01 03:27:00
        """)
        cue = tmp_path / "game.cue"
        cue.write_text(cue_content)

        result = self._call(cue)
        assert result == real_bin, (
            "_cue_bin_path() must return the second FILE entry when the first "
            "does not exist on disk"
        )

    def test_returns_none_when_all_files_missing(self, tmp_path: Path):
        cue_content = textwrap.dedent("""\
            FILE "missing_track01.bin" BINARY
              TRACK 01 MODE2/2352
            FILE "also_missing_track02.bin" BINARY
              TRACK 02 AUDIO
        """)
        cue = tmp_path / "game.cue"
        cue.write_text(cue_content)
        assert self._call(cue) is None

    def test_handles_unreadable_cue_gracefully(self, tmp_path: Path):
        """Non-existent .cue path must return None, not raise."""
        ghost = tmp_path / "nonexistent.cue"
        assert self._call(ghost) is None
