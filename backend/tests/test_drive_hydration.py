"""Tests for backend.service.launch.drive_hydration:

- _copy_loose_files_to_drive: error paths (non-dir src, no files, MD5 mismatch)
  and the success path with mocked FAT I/O.
- hydrate_drive_for_entity: skip conditions and the FAT copy trigger.

Architecture note — P3.1 transactional gap (still present in the code):
  hydrate_drive_for_entity() issues two separate db.commit() calls: one when
  drive.size_mb changes and a second when entity._db_collection.installed = True is
  written back.  A crash or exception between these two commits leaves the
  drive image freshly formatted but installed=False, causing a full re-format
  on the next launch.  No test here can paper over that race; it is noted for
  awareness.

Run with:
    pytest backend/tests/test_drive_hydration.py
"""
import hashlib
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_drive(image_path: str, size_mb: int = 100) -> MagicMock:
    drive = MagicMock()
    drive.id = 1
    drive.image_path = image_path
    drive.size_mb = size_mb
    return drive


def _make_entity(
    *,
    era: str = "dos",
    installed: bool = False,
    requires_install: bool = False,
    folder_path: str | None = None,
    media_type: str | None = "dir",
    drive=None,
    db_collection=None,
    environment_item_id: int | None = None,
):
    from backend.models.game import derive_item_type
    from backend.service.launch.launchable_resolver import LaunchableEntity

    return LaunchableEntity(
        collection_id=1,
        profile_item_id=None,
        era=era,
        item_type=derive_item_type(era),
        environment_item_id=environment_item_id,
        slug=None,
        media_path="/tmp/game.exe",
        executable_path=None,
        installed=installed,
        requires_install=requires_install,
        folder_path=folder_path,
        media_type=media_type,
        drive=drive,
        _db_collection=db_collection,
    )


# ---------------------------------------------------------------------------
# _copy_loose_files_to_drive
# ---------------------------------------------------------------------------


class TestCopyLooseFilesToDrive:
    def test_non_directory_src_raises_runtime_error(self, tmp_path):
        from backend.service.launch.drive_hydration import _copy_loose_files_to_drive

        not_a_dir = tmp_path / "file.txt"
        not_a_dir.write_bytes(b"data")

        with pytest.raises(RuntimeError, match="not a directory"):
            _copy_loose_files_to_drive(not_a_dir, tmp_path / "image.img", size_mb=10)

    def test_empty_directory_raises_runtime_error(self, tmp_path):
        from backend.service.launch.drive_hydration import _copy_loose_files_to_drive

        src = tmp_path / "src"
        src.mkdir()

        with pytest.raises(RuntimeError, match="No files found"):
            _copy_loose_files_to_drive(src, tmp_path / "image.img", size_mb=10)

    def test_md5_mismatch_raises_runtime_error(self, tmp_path, monkeypatch):
        import backend.service.launch.drive_hydration as dh

        src = tmp_path / "src"
        src.mkdir()
        (src / "game.exe").write_bytes(b"original")

        monkeypatch.setattr(dh, "write_file_to_image", MagicMock())
        # Return bytes that differ from what was written → mismatch
        monkeypatch.setattr(dh, "read_file_from_image", MagicMock(return_value=b"corrupted"))

        with pytest.raises(RuntimeError, match="MD5 mismatch"):
            dh._copy_loose_files_to_drive(src, tmp_path / "image.img", size_mb=10)

    def test_success_calls_write_and_verifies_via_read(self, tmp_path, monkeypatch):
        import backend.service.launch.drive_hydration as dh

        src = tmp_path / "src"
        src.mkdir()
        file_data = b"game content"
        (src / "game.exe").write_bytes(file_data)

        mock_write = MagicMock()
        # read_file_from_image returns the same bytes → MD5 check passes
        mock_read = MagicMock(return_value=file_data)
        monkeypatch.setattr(dh, "write_file_to_image", mock_write)
        monkeypatch.setattr(dh, "read_file_from_image", mock_read)

        img = tmp_path / "image.img"
        dh._copy_loose_files_to_drive(src, img, size_mb=10)

        mock_write.assert_called_once_with(img, "game.exe", file_data)
        mock_read.assert_called_once_with(img, "game.exe")

    def test_nested_files_preserve_relative_paths(self, tmp_path, monkeypatch):
        import backend.service.launch.drive_hydration as dh

        src = tmp_path / "src"
        subdir = src / "subdir"
        subdir.mkdir(parents=True)
        file_data = b"nested"
        (subdir / "file.dat").write_bytes(file_data)

        written_paths = []

        def mock_write(img, dest, data):
            written_paths.append(dest)

        monkeypatch.setattr(dh, "write_file_to_image", mock_write)
        monkeypatch.setattr(dh, "read_file_from_image", MagicMock(return_value=file_data))

        dh._copy_loose_files_to_drive(src, tmp_path / "image.img", size_mb=10)

        assert written_paths == ["subdir/file.dat"]

    def test_image_file_itself_is_excluded_from_copy(self, tmp_path, monkeypatch):
        """The drive image being built must not be copied into itself."""
        import backend.service.launch.drive_hydration as dh

        src = tmp_path / "src"
        src.mkdir()
        img = src / "drive.img"
        img.write_bytes(b"image data")
        (src / "game.exe").write_bytes(b"game")

        written_paths = []

        def mock_write(image, dest, data):
            written_paths.append(dest)

        monkeypatch.setattr(dh, "write_file_to_image", mock_write)
        monkeypatch.setattr(dh, "read_file_from_image", MagicMock(return_value=b"game"))

        dh._copy_loose_files_to_drive(src, img, size_mb=10)

        assert "drive.img" not in written_paths
        assert "game.exe" in written_paths


# ---------------------------------------------------------------------------
# hydrate_drive_for_entity
# ---------------------------------------------------------------------------


class TestHydrateDriveForEntity:
    def test_returns_none_when_no_drive_and_era_not_in_drive_eras(self, tmp_path):
        from backend.service.launch.drive_hydration import hydrate_drive_for_entity

        entity = _make_entity(era="ps1", drive=None)
        result = hydrate_drive_for_entity(entity, db=None)
        assert result is None

    def test_returns_drive_unchanged_when_already_installed(self, tmp_path):
        from backend.service.launch.drive_hydration import hydrate_drive_for_entity

        drive = _make_drive(str(tmp_path / "game.img"))
        entity = _make_entity(
            era="dos",
            installed=True,
            folder_path=str(tmp_path),
            drive=drive,
        )
        result = hydrate_drive_for_entity(entity, db=MagicMock())
        assert result is drive

    def test_returns_drive_unchanged_when_requires_install(self, tmp_path):
        from backend.service.launch.drive_hydration import hydrate_drive_for_entity

        drive = _make_drive(str(tmp_path / "game.img"))
        entity = _make_entity(
            era="dos",
            requires_install=True,
            folder_path=str(tmp_path),
            drive=drive,
        )
        result = hydrate_drive_for_entity(entity, db=MagicMock())
        assert result is drive

    def test_returns_drive_unchanged_when_folder_path_is_none(self, tmp_path):
        from backend.service.launch.drive_hydration import hydrate_drive_for_entity

        drive = _make_drive(str(tmp_path / "game.img"))
        entity = _make_entity(era="dos", drive=drive, folder_path=None)
        result = hydrate_drive_for_entity(entity, db=MagicMock())
        assert result is drive

    def test_drive_with_no_image_path_raises_runtime_error(self, tmp_path):
        from backend.service.launch.drive_hydration import hydrate_drive_for_entity

        src = tmp_path / "src"
        src.mkdir()
        (src / "game.exe").write_bytes(b"data")

        drive = _make_drive(image_path=None)
        entity = _make_entity(
            era="dos",
            installed=False,
            requires_install=False,
            folder_path=str(src),
            drive=drive,
        )
        with pytest.raises(RuntimeError, match="no image_path"):
            from backend.service.launch.drive_hydration import hydrate_drive_for_entity
            hydrate_drive_for_entity(entity, db=MagicMock())

    def test_fat_copy_path_triggered_for_uninstalled_dos_entity(self, tmp_path, monkeypatch):
        """On first launch of a DOS loose-file item:
        - existing image is deleted (if present)
        - format_fat16 is called with the fresh size
        - _copy_loose_files_to_drive copies files
        - installed=True is written back via db
        """
        import backend.service.launch.drive_hydration as dh

        src = tmp_path / "src"
        src.mkdir()
        (src / "game.exe").write_bytes(b"data")

        img = tmp_path / "game.img"
        img.write_bytes(b"stale image")  # pre-existing; must be deleted first

        mock_format = MagicMock()
        mock_write = MagicMock()
        mock_read = MagicMock(return_value=b"data")
        mock_copy = MagicMock()

        monkeypatch.setattr(dh, "format_fat16", mock_format)
        monkeypatch.setattr(dh, "write_file_to_image", mock_write)
        monkeypatch.setattr(dh, "read_file_from_image", mock_read)
        monkeypatch.setattr(dh, "_copy_loose_files_to_drive", mock_copy)

        # Mock compute_drive_size_mb at the source so the deferred import resolves it
        import backend.service.utils.drive_utils as du_mod
        monkeypatch.setattr(du_mod, "compute_drive_size_mb", MagicMock(return_value=50))

        drive = _make_drive(str(img), size_mb=50)
        db_collection = MagicMock()
        db_collection.installed = False
        db = MagicMock()

        entity = _make_entity(
            era="dos",
            installed=False,
            requires_install=False,
            folder_path=str(src),
            media_type="dir",
            drive=drive,
            db_collection=db_collection,
        )

        result = dh.hydrate_drive_for_entity(entity, db=db)

        assert result is drive
        assert not img.exists()  # stale image was deleted before format
        mock_format.assert_called_once()
        mock_copy.assert_called_once()
        # installed=True must be written back
        assert db_collection.installed is True
        db.commit.assert_called()

    def test_auto_creates_drive_for_dos_item_with_no_drive(self, tmp_path, monkeypatch):
        """When no drive exists for a DOS item, one is auto-created before hydration."""
        import backend.service.launch.drive_hydration as dh
        import backend.service.utils.drive_utils as du_mod

        src = tmp_path / "src"
        src.mkdir()
        (src / "game.exe").write_bytes(b"data")

        img = tmp_path / "auto.img"
        auto_drive = _make_drive(str(img), size_mb=50)

        monkeypatch.setattr(du_mod, "create_drive_for_collection", MagicMock(return_value=auto_drive))
        monkeypatch.setattr(du_mod, "compute_drive_size_mb", MagicMock(return_value=50))
        monkeypatch.setattr(dh, "format_fat16", MagicMock())
        monkeypatch.setattr(dh, "_copy_loose_files_to_drive", MagicMock())

        db_collection = MagicMock()
        db_collection.installed = False
        db = MagicMock()

        entity = _make_entity(
            era="dos",
            installed=False,
            requires_install=False,
            folder_path=str(src),
            drive=None,
            db_collection=db_collection,
        )

        result = dh.hydrate_drive_for_entity(entity, db=db)
        assert result is auto_drive
