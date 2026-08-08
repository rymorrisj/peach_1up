import dataclasses
from pathlib import Path

import pytest


class TestMediaTargetConstruction:
    def test_file_kind(self):
        from backend.service.utils.detection import MediaTarget
        pkg = Path("/library/games/ps3/example/game.pkg")
        target = MediaTarget(
            kind="file", detect_path=pkg, launch_path=pkg,
            era="ps3", requires_install=False, license_files=(),
        )
        assert target.kind == "file"
        assert target.detect_path == pkg
        assert target.launch_path == pkg
        assert target.era == "ps3"
        assert target.requires_install is False
        assert target.license_files == ()

    def test_file_kind_with_license_files(self):
        # Mirrors rpcs3.py's pkg_target construction: sibling .rap files
        # discovered alongside a "file"-kind PS3 .pkg target.
        from backend.service.utils.detection import MediaTarget
        pkg = Path("/library/games/ps3/example/game.pkg")
        rap = Path("/library/games/ps3/example/game.rap")
        target = MediaTarget(
            kind="file", detect_path=pkg, launch_path=pkg,
            era="ps3", requires_install=False, license_files=(rap,),
        )
        assert target.license_files == (rap,)

    def test_disc_folder_kind(self):
        from backend.service.utils.detection import MediaTarget
        folder = Path("/library/games/ps3/example")
        eboot = folder / "PS3_GAME" / "USRDIR" / "EBOOT.BIN"
        target = MediaTarget(
            kind="disc_folder", detect_path=eboot, launch_path=folder,
            era="ps3", requires_install=False, license_files=(),
        )
        assert target.kind == "disc_folder"
        assert target.detect_path == eboot
        assert target.launch_path == folder

    def test_installed_dir_kind(self):
        from backend.service.utils.detection import MediaTarget
        folder = Path("/library/games/ps3/example")
        eboot = folder / "USRDIR" / "EBOOT.BIN"
        target = MediaTarget(
            kind="installed_dir", detect_path=eboot, launch_path=folder,
            era="ps3", requires_install=False, license_files=(),
        )
        assert target.kind == "installed_dir"
        assert target.detect_path == eboot
        assert target.launch_path == folder

    def test_xex_folder_kind(self):
        # xex_folder is the one shape where detect_path and launch_path are
        # the same file, not a folder (Xenia is handed the resolved .xex
        # directly, unlike PS3's folder-as-launch-target shapes).
        from backend.service.utils.detection import MediaTarget
        xex = Path("/library/games/xbox360/example/default.xex")
        target = MediaTarget(
            kind="xex_folder", detect_path=xex, launch_path=xex,
            era="xbox360", requires_install=False, license_files=(),
        )
        assert target.kind == "xex_folder"
        assert target.detect_path == target.launch_path == xex
        assert target.era == "xbox360"

    def test_era_none_allowed(self):
        from backend.service.utils.detection import MediaTarget
        f = Path("/library/games/example.pkg")
        target = MediaTarget(
            kind="file", detect_path=f, launch_path=f,
            era=None, requires_install=False, license_files=(),
        )
        assert target.era is None

    def test_license_files_defaults_to_empty_tuple(self):
        from backend.service.utils.detection import MediaTarget
        f = Path("/library/games/example.pkg")
        target = MediaTarget(
            kind="file", detect_path=f, launch_path=f,
            era="ps3", requires_install=False,
        )
        assert target.license_files == ()

    def test_frozen_instance_is_immutable(self):
        from backend.service.utils.detection import MediaTarget
        f = Path("/library/games/example.pkg")
        target = MediaTarget(
            kind="file", detect_path=f, launch_path=f,
            era="ps3", requires_install=False, license_files=(),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            target.kind = "xex_folder"
