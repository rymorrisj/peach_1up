import pytest

from backend.constants_generated import Era


class TestDetectMediaType:
    def test_iso(self, tmp_path):
        from backend.service.utils.media_detect import detect_media_type
        f = tmp_path / "game.iso"
        f.write_bytes(b"\x00" * 16)
        assert detect_media_type(f) == "iso"

    def test_cue(self, tmp_path):
        from backend.service.utils.media_detect import detect_media_type
        f = tmp_path / "game.cue"
        f.write_bytes(b"FILE \"game.bin\" BINARY\n")
        assert detect_media_type(f) == "cue"

    def test_exe(self, tmp_path):
        from backend.service.utils.media_detect import detect_media_type
        f = tmp_path / "game.exe"
        f.write_bytes(b"MZ")
        assert detect_media_type(f) == "exe"

    def test_directory(self, tmp_path):
        from backend.service.utils.media_detect import detect_media_type
        d = tmp_path / "game_dir"
        d.mkdir()
        assert detect_media_type(d) == "directory"

    def test_unknown_extension(self, tmp_path):
        from backend.service.utils.media_detect import detect_media_type
        f = tmp_path / "archive.zip"
        f.write_bytes(b"PK\x03\x04")
        assert detect_media_type(f) == "unknown"

    def test_img_under_2mb_is_floppy(self, tmp_path):
        from backend.service.utils.media_detect import detect_media_type
        f = tmp_path / "disk.img"
        f.write_bytes(b"\x00" * (2 * 1024 * 1024 - 1))
        assert detect_media_type(f) == "floppy"

    def test_img_exactly_2mb_is_hdd(self, tmp_path):
        from backend.service.utils.media_detect import detect_media_type
        f = tmp_path / "disk.img"
        f.write_bytes(b"\x00" * (2 * 1024 * 1024))
        assert detect_media_type(f) == "hdd"

    def test_img_over_2mb_is_hdd(self, tmp_path):
        from backend.service.utils.media_detect import detect_media_type
        f = tmp_path / "disk.img"
        f.write_bytes(b"\x00" * (2 * 1024 * 1024 + 1))
        assert detect_media_type(f) == "hdd"


class TestGetCompatibleMediaDOS:
    def _make_file(self, directory, name, size=16):
        p = directory / name
        p.write_bytes(b"\x00" * size)
        return p

    def test_excludes_img_files(self, tmp_path):
        from backend.service.utils.media_detect import get_compatible_media
        self._make_file(tmp_path, "floppy.img", size=1024)
        self._make_file(tmp_path, "game.exe")
        result = get_compatible_media(Era.DOS, str(tmp_path))
        names = [p.name for p in result]
        assert "floppy.img" not in names
        assert "game.exe" in names

    def test_excludes_setup_exe(self, tmp_path):
        from backend.service.utils.media_detect import get_compatible_media
        self._make_file(tmp_path, "setup.exe")
        self._make_file(tmp_path, "game.exe")
        result = get_compatible_media(Era.DOS, str(tmp_path))
        names = [p.name for p in result]
        assert "setup.exe" not in names
        assert "game.exe" in names

    def test_excludes_install_exe(self, tmp_path):
        from backend.service.utils.media_detect import get_compatible_media
        self._make_file(tmp_path, "install.exe")
        self._make_file(tmp_path, "game.exe")
        result = get_compatible_media(Era.DOS, str(tmp_path))
        names = [p.name for p in result]
        assert "install.exe" not in names

    def test_excludes_setup_bat(self, tmp_path):
        from backend.service.utils.media_detect import get_compatible_media
        self._make_file(tmp_path, "setup.bat")
        self._make_file(tmp_path, "run.bat")
        result = get_compatible_media(Era.DOS, str(tmp_path))
        names = [p.name for p in result]
        assert "setup.bat" not in names
        assert "run.bat" in names

    def test_excludes_install_bat(self, tmp_path):
        from backend.service.utils.media_detect import get_compatible_media
        self._make_file(tmp_path, "install.bat")
        result = get_compatible_media(Era.DOS, str(tmp_path))
        names = [p.name for p in result]
        assert "install.bat" not in names

    def test_excludes_blocked_names_case_insensitively(self, tmp_path):
        from backend.service.utils.media_detect import get_compatible_media
        self._make_file(tmp_path, "SETUP.EXE")
        self._make_file(tmp_path, "Install.Bat")
        self._make_file(tmp_path, "SETUP.BAT")
        self._make_file(tmp_path, "INSTALL.EXE")
        self._make_file(tmp_path, "game.exe")
        result = get_compatible_media(Era.DOS, str(tmp_path))
        names = [p.name for p in result]
        assert "SETUP.EXE" not in names
        assert "Install.Bat" not in names
        assert "SETUP.BAT" not in names
        assert "INSTALL.EXE" not in names
        assert "game.exe" in names
