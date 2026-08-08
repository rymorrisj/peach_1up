class TestIsDiscFormatFolder:
    def test_true_when_marker_present(self, tmp_path):
        from backend.service.utils.detection.ps3 import is_disc_format_folder
        (tmp_path / "PS3_DISC.SFB").write_bytes(b"")
        assert is_disc_format_folder(tmp_path) is True

    def test_false_when_marker_absent(self, tmp_path):
        from backend.service.utils.detection.ps3 import is_disc_format_folder
        assert is_disc_format_folder(tmp_path) is False

    def test_false_when_marker_is_a_directory_not_a_file(self, tmp_path):
        from backend.service.utils.detection.ps3 import is_disc_format_folder
        (tmp_path / "PS3_DISC.SFB").mkdir()
        assert is_disc_format_folder(tmp_path) is False

    def test_false_for_nonexistent_folder(self, tmp_path):
        from backend.service.utils.detection.ps3 import is_disc_format_folder
        assert is_disc_format_folder(tmp_path / "missing") is False


class TestFindEboot:
    def test_installed_dir_layout(self, tmp_path):
        # dev_hdd0/game/<TITLE_ID>/USRDIR/EBOOT.BIN - installed pkg shape
        from backend.service.utils.detection.ps3 import find_eboot
        usrdir = tmp_path / "USRDIR"
        usrdir.mkdir()
        eboot = usrdir / "EBOOT.BIN"
        eboot.write_bytes(b"")
        assert find_eboot(tmp_path) == eboot

    def test_disc_folder_layout(self, tmp_path):
        # PS3_GAME/USRDIR/EBOOT.BIN - extracted disc dump shape
        from backend.service.utils.detection.ps3 import find_eboot
        usrdir = tmp_path / "PS3_GAME" / "USRDIR"
        usrdir.mkdir(parents=True)
        eboot = usrdir / "EBOOT.BIN"
        eboot.write_bytes(b"")
        assert find_eboot(tmp_path) == eboot

    def test_installed_dir_layout_takes_priority_when_both_present(self, tmp_path):
        from backend.service.utils.detection.ps3 import find_eboot
        installed = tmp_path / "USRDIR"
        installed.mkdir()
        installed_eboot = installed / "EBOOT.BIN"
        installed_eboot.write_bytes(b"")
        disc = tmp_path / "PS3_GAME" / "USRDIR"
        disc.mkdir(parents=True)
        (disc / "EBOOT.BIN").write_bytes(b"")
        assert find_eboot(tmp_path) == installed_eboot

    def test_none_when_neither_layout_present(self, tmp_path):
        from backend.service.utils.detection.ps3 import find_eboot
        assert find_eboot(tmp_path) is None

    def test_none_when_eboot_is_a_directory_not_a_file(self, tmp_path):
        from backend.service.utils.detection.ps3 import find_eboot
        usrdir = tmp_path / "USRDIR"
        usrdir.mkdir()
        (usrdir / "EBOOT.BIN").mkdir()
        assert find_eboot(tmp_path) is None


class TestResolvePs3Target:
    def test_none_when_folder_is_not_a_directory(self, tmp_path):
        from backend.service.utils.detection.ps3 import resolve_ps3_target
        f = tmp_path / "notafolder.pkg"
        f.write_bytes(b"")
        assert resolve_ps3_target(f) is None

    def test_none_when_folder_does_not_exist(self, tmp_path):
        from backend.service.utils.detection.ps3 import resolve_ps3_target
        assert resolve_ps3_target(tmp_path / "missing") is None

    def test_disc_folder_with_valid_eboot_resolves(self, tmp_path):
        from backend.service.utils.detection.ps3 import resolve_ps3_target
        (tmp_path / "PS3_DISC.SFB").write_bytes(b"")
        usrdir = tmp_path / "PS3_GAME" / "USRDIR"
        usrdir.mkdir(parents=True)
        eboot = usrdir / "EBOOT.BIN"
        eboot.write_bytes(b"")

        target = resolve_ps3_target(tmp_path)

        assert target is not None
        assert target.kind == "disc_folder"
        assert target.detect_path == eboot
        assert target.launch_path == tmp_path
        assert target.era == "ps3"
        assert target.requires_install is False
        assert target.license_files == ()

    def test_disc_marker_alone_without_eboot_does_not_resolve(self, tmp_path):
        # Deliberate per ps3.py's own docstring: the disc-format branch used
        # to trust the SFB marker alone and skip the EBOOT check, letting an
        # unbootable folder reach RPCS3 before failing there instead of here.
        from backend.service.utils.detection.ps3 import resolve_ps3_target
        (tmp_path / "PS3_DISC.SFB").write_bytes(b"")
        assert resolve_ps3_target(tmp_path) is None

    def test_installed_dir_with_valid_eboot_resolves(self, tmp_path):
        from backend.service.utils.detection.ps3 import resolve_ps3_target
        usrdir = tmp_path / "USRDIR"
        usrdir.mkdir()
        eboot = usrdir / "EBOOT.BIN"
        eboot.write_bytes(b"")

        target = resolve_ps3_target(tmp_path)

        assert target is not None
        assert target.kind == "installed_dir"
        assert target.detect_path == eboot
        assert target.launch_path == tmp_path

    def test_none_for_empty_folder(self, tmp_path):
        from backend.service.utils.detection.ps3 import resolve_ps3_target
        assert resolve_ps3_target(tmp_path) is None

    def test_none_for_malformed_folder_with_unrelated_contents(self, tmp_path):
        from backend.service.utils.detection.ps3 import resolve_ps3_target
        (tmp_path / "readme.txt").write_bytes(b"not a game")
        (tmp_path / "USRDIR").mkdir()  # USRDIR present but no EBOOT.BIN inside
        assert resolve_ps3_target(tmp_path) is None
