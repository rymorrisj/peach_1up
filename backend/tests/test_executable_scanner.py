import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


class _PyCdlibException(Exception):
    pass


def _make_pycdlib_modules(walk_results, has_joliet=False, open_raises=None):
    mock_iso = MagicMock()
    mock_iso.has_joliet.return_value = has_joliet
    mock_iso.walk.return_value = iter(walk_results)
    if open_raises is not None:
        mock_iso.open.side_effect = open_raises

    mock_submod = MagicMock()
    mock_submod.PyCdlibException = _PyCdlibException

    mock_mod = MagicMock()
    mock_mod.PyCdlib.return_value = mock_iso
    mock_mod.pycdlibexception = mock_submod

    return {"pycdlib": mock_mod, "pycdlib.pycdlibexception": mock_submod}


class TestScanExecutableCandidates:
    def test_doom_exe_on_doom_iso_is_top_candidate(self):
        from backend.service.utils.executable_scanner import scan_executable_candidates

        mods = _make_pycdlib_modules([("/", [], ["DOOM.EXE;1"])])
        with __import__("unittest.mock", fromlist=["patch"]).patch.dict(sys.modules, mods):
            candidates = scan_executable_candidates(Path("DOOM.ISO"))

        assert candidates[0] == "D:\\DOOM.EXE"

    def test_game_exe_ranked_above_setup_exe(self):
        from backend.service.utils.executable_scanner import scan_executable_candidates

        mods = _make_pycdlib_modules([("/", [], ["SETUP.EXE;1", "GAME.EXE;1"])])
        with __import__("unittest.mock", fromlist=["patch"]).patch.dict(sys.modules, mods):
            candidates = scan_executable_candidates(Path("GAME.ISO"))

        assert candidates[0] == "D:\\GAME.EXE"
        assert candidates[1] == "D:\\SETUP.EXE"

    def test_bat_matching_stem_ranked_above_deprioritized_exe(self):
        from backend.service.utils.executable_scanner import scan_executable_candidates

        mods = _make_pycdlib_modules([("/", [], ["SETUP.EXE;1", "GAME.BAT;1"])])
        with __import__("unittest.mock", fromlist=["patch"]).patch.dict(sys.modules, mods):
            candidates = scan_executable_candidates(Path("GAME.ISO"))

        assert candidates[0] == "D:\\GAME.BAT"
        assert candidates[1] == "D:\\SETUP.EXE"

    def test_com_files_rank_below_exe_and_bat(self):
        from backend.service.utils.executable_scanner import scan_executable_candidates

        mods = _make_pycdlib_modules(
            [("/", [], ["GAME.COM;1", "UTILS.EXE;1", "RUN.BAT;1"])]
        )
        with __import__("unittest.mock", fromlist=["patch"]).patch.dict(sys.modules, mods):
            candidates = scan_executable_candidates(Path("GAME.ISO"))

        exts = [os.path.splitext(c)[1].lower() for c in candidates]
        com_index = exts.index(".com")
        assert all(exts[i] in {".exe", ".bat"} for i in range(com_index))

    def test_pycdlib_unavailable_raises_runtime_error(self):
        from backend.service.utils.executable_scanner import scan_executable_candidates

        with __import__("unittest.mock", fromlist=["patch"]).patch.dict(
            sys.modules, {"pycdlib": None, "pycdlib.pycdlibexception": None}
        ):
            with pytest.raises(RuntimeError, match="pycdlib"):
                scan_executable_candidates(Path("GAME.ISO"))

    def test_empty_disc_returns_empty_list(self):
        from backend.service.utils.executable_scanner import scan_executable_candidates

        mods = _make_pycdlib_modules([("/", [], [])])
        with __import__("unittest.mock", fromlist=["patch"]).patch.dict(sys.modules, mods):
            candidates = scan_executable_candidates(Path("EMPTY.ISO"))

        assert candidates == []

    def test_directory_scan_finds_exe_files(self, tmp_path):
        from backend.service.utils.executable_scanner import scan_executable_candidates

        (tmp_path / "GAME.EXE").write_text("")
        (tmp_path / "README.TXT").write_text("")
        (tmp_path / "NOTES.MD").write_text("")

        candidates = scan_executable_candidates(tmp_path)

        assert len(candidates) == 1
        assert os.path.basename(candidates[0]).upper() == "GAME.EXE"

    def test_iso_subdirectory_path_is_preserved(self):
        from backend.service.utils.executable_scanner import scan_executable_candidates

        mods = _make_pycdlib_modules([("/DOOMCD", [], ["DOOM.EXE;1"])])
        with __import__("unittest.mock", fromlist=["patch"]).patch.dict(sys.modules, mods):
            candidates = scan_executable_candidates(Path("DOOM.ISO"))

        assert candidates[0] == "D:\\DOOMCD\\DOOM.EXE"

    def test_joliet_filenames_have_no_version_suffix_stripped(self):
        from backend.service.utils.executable_scanner import scan_executable_candidates

        mods = _make_pycdlib_modules([("/", [], ["Doom.exe"])], has_joliet=True)
        with __import__("unittest.mock", fromlist=["patch"]).patch.dict(sys.modules, mods):
            candidates = scan_executable_candidates(Path("DOOM.ISO"))

        assert candidates[0] == "D:\\Doom.exe"

    def test_case_insensitive_extension_matching(self, tmp_path):
        from backend.service.utils.executable_scanner import scan_executable_candidates

        (tmp_path / "run.Exe").write_text("")
        (tmp_path / "script.BAT").write_text("")
        (tmp_path / "prog.Com").write_text("")

        candidates = scan_executable_candidates(tmp_path)

        assert len(candidates) == 3

    def test_directory_scan_recurses_into_subdirectories(self, tmp_path):
        from backend.service.utils.executable_scanner import scan_executable_candidates

        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "GAME.EXE").write_text("")

        candidates = scan_executable_candidates(tmp_path)

        assert len(candidates) == 1
        assert os.path.basename(candidates[0]).upper() == "GAME.EXE"

    def test_iso_open_failure_raises_runtime_error(self):
        from backend.service.utils.executable_scanner import scan_executable_candidates

        mods = _make_pycdlib_modules([], open_raises=_PyCdlibException("bad image"))
        with __import__("unittest.mock", fromlist=["patch"]).patch.dict(sys.modules, mods):
            with pytest.raises(RuntimeError, match="Could not open"):
                scan_executable_candidates(Path("CORRUPT.ISO"))

    def test_unsupported_media_type_raises_value_error(self):
        from backend.service.utils.executable_scanner import scan_executable_candidates

        with pytest.raises(ValueError, match="Unsupported media"):
            scan_executable_candidates(Path("game.img"))
