import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestComputeDriveSizeMb:
    def test_iso_floor_on_tiny_file(self, tmp_path):
        from backend.service.utils.drive_utils import compute_drive_size_mb
        f = tmp_path / "game.iso"
        f.write_bytes(b"\x00")
        assert compute_drive_size_mb(f, "iso") == 50

    def test_iso_cap_on_large_file(self, tmp_path):
        from backend.service.utils.drive_utils import compute_drive_size_mb
        f = tmp_path / "game.iso"
        f.write_bytes(b"\x00")
        mock_stat = MagicMock()
        mock_stat.st_size = 1400 * 1024 * 1024  # 1400 MB → 1400 * 1.5 = 2100, capped at 2048
        with patch.object(Path, "stat", return_value=mock_stat):
            result = compute_drive_size_mb(f, "iso")
        assert result == 2048

    def test_floppy_floor_on_tiny_file(self, tmp_path):
        from backend.service.utils.drive_utils import compute_drive_size_mb
        f = tmp_path / "disk.img"
        f.write_bytes(b"\x00")
        assert compute_drive_size_mb(f, "floppy") == 20

    def test_floppy_cap_on_large_file(self, tmp_path):
        from backend.service.utils.drive_utils import compute_drive_size_mb
        f = tmp_path / "disk.img"
        f.write_bytes(b"\x00")
        mock_stat = MagicMock()
        mock_stat.st_size = 25 * 1024 * 1024  # 25 MB → 25 * 2 = 50, capped at 40
        with patch.object(Path, "stat", return_value=mock_stat):
            result = compute_drive_size_mb(f, "floppy")
        assert result == 40

    def test_fallback_2kb_file_meets_fat16_minimum(self, tmp_path):
        from backend.service.utils.drive_utils import compute_drive_size_mb
        f = tmp_path / "game.exe"
        f.write_bytes(b"\x00" * 2048)  # 2 KB
        result = compute_drive_size_mb(f, "unknown")
        assert result >= 4

    def test_fallback_2kb_file_does_not_return_3(self, tmp_path):
        from backend.service.utils.drive_utils import compute_drive_size_mb
        f = tmp_path / "game.exe"
        f.write_bytes(b"\x00" * 2048)  # 2 KB — old formula returned 3, breaking FAT16
        result = compute_drive_size_mb(f, "unknown")
        assert result != 3


class TestDeleteDriveForCollection:
    @pytest.fixture
    def mem_session(self):
        from sqlmodel import SQLModel, Session, create_engine
        import backend.models  # noqa: F401 — registers all table models with SQLModel.metadata
        engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            yield session

    def test_drive_id_is_none_after_delete(self, mem_session):
        from backend.models.game import GameItemBundle
        from backend.models.drive import Drive
        from backend.service.utils.drive_utils import delete_drive_for_collection

        collection = GameItemBundle(title="Test Game", era="dos", slug="test-game")
        mem_session.add(collection)
        mem_session.flush()

        drive = Drive(game_item_bundle_id=collection.id, name="Test Game", size_mb=10)
        mem_session.add(drive)
        mem_session.flush()

        collection.drive_id = drive.id
        mem_session.add(collection)
        mem_session.commit()

        delete_drive_for_collection(collection, mem_session)

        assert collection.drive_id is None

    def test_delete_noop_when_no_drive(self, mem_session):
        from backend.models.game import GameItemBundle
        from backend.service.utils.drive_utils import delete_drive_for_collection

        collection = GameItemBundle(title="Test Game", era="dos", slug="test-game")
        mem_session.add(collection)
        mem_session.commit()

        delete_drive_for_collection(collection, mem_session)

        assert collection.drive_id is None


