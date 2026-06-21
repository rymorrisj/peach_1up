"""Tests for launch concurrency and validation guards in
service/launch/coordinator.py.
"""

import pytest
from fastapi import HTTPException


@pytest.fixture(autouse=True)
def _clear_process_registry():
    from backend.core import process_registry
    with process_registry._lock:
        process_registry._registry.clear()
    yield
    with process_registry._lock:
        process_registry._registry.clear()


@pytest.fixture
def mem_session():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import SQLModel, Session, create_engine
    import backend.models  # noqa: F401 — registers all table models with SQLModel.metadata

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class TestGateSingleActiveLaunch:
    def test_second_launch_for_same_profile_rejected_with_409(self):
        from backend.core import process_registry
        from backend.core.process_registry import ProcessEntry
        from backend.service.launch.coordinator import _gate_single_active_launch

        process_registry.register(
            1234,
            ProcessEntry(process_handle=object(), job_handle=object(), library_item_id=1, profile_id=7),
        )

        with pytest.raises(HTTPException) as exc_info:
            _gate_single_active_launch(7)

        assert exc_info.value.status_code == 409

    def test_different_profile_is_not_gated(self):
        from backend.core import process_registry
        from backend.core.process_registry import ProcessEntry
        from backend.service.launch.coordinator import _gate_single_active_launch

        process_registry.register(
            1234,
            ProcessEntry(process_handle=object(), job_handle=object(), library_item_id=1, profile_id=7),
        )

        # Should not raise — different profile is unaffected.
        _gate_single_active_launch(8)

    def test_no_profile_id_is_not_gated(self):
        from backend.service.launch.coordinator import _gate_single_active_launch

        # gate_profile_id=None short-circuits regardless of registry contents.
        _gate_single_active_launch(None)


class TestResolveProfileForItem:
    def test_nonexistent_profile_id_returns_404(self, mem_session):
        from backend.models.library import LibraryItem
        from backend.service.launch.coordinator import _resolve_profile_for_item

        item = LibraryItem(title="Test Game", era="dos", media_path="/tmp/test")
        mem_session.add(item)
        mem_session.commit()
        mem_session.refresh(item)

        with pytest.raises(HTTPException) as exc_info:
            _resolve_profile_for_item(item, 9999, mem_session)

        assert exc_info.value.status_code == 404


class TestUpdateDriveForItem:
    def test_resize_preserves_existing_file_contents(self, mem_session, tmp_path):
        from backend.models.drive import Drive
        from backend.models.library import LibraryItem
        from backend.service.utils.drive_utils import update_drive_for_item
        from backend.service.utils.fat import format_fat16, read_file_from_image, write_file_to_image

        item = LibraryItem(title="Test Game", era="dos", media_path="/tmp/test")
        mem_session.add(item)
        mem_session.commit()
        mem_session.refresh(item)

        img_path = tmp_path / "drive.img"
        format_fat16(img_path, 10)
        write_file_to_image(img_path, "game.exe", b"some game data")

        drive = Drive(library_item_id=item.id, name="Test Drive", size_mb=10, image_path=str(img_path))
        mem_session.add(drive)
        mem_session.commit()
        mem_session.refresh(drive)
        item.drive_id = drive.id
        mem_session.add(item)
        mem_session.commit()

        updated = update_drive_for_item(item, 20, mem_session)

        assert updated.size_mb == 20
        assert read_file_from_image(img_path, "game.exe") == b"some game data"
        assert not img_path.with_name(img_path.name + ".bak").exists()
        assert not img_path.with_name(img_path.name + ".new").exists()

    def test_no_drive_raises(self, mem_session):
        from backend.models.library import LibraryItem
        from backend.service.utils.drive_utils import update_drive_for_item

        item = LibraryItem(title="Test Game", era="dos", media_path="/tmp/test")
        mem_session.add(item)
        mem_session.commit()
        mem_session.refresh(item)

        with pytest.raises(RuntimeError):
            update_drive_for_item(item, 20, mem_session)

    def test_size_out_of_range_raises_without_touching_image(self, mem_session, tmp_path):
        from backend.models.drive import Drive
        from backend.models.library import LibraryItem
        from backend.service.utils.drive_utils import update_drive_for_item
        from backend.service.utils.fat import format_fat16, read_file_from_image, write_file_to_image

        item = LibraryItem(title="Test Game", era="dos", media_path="/tmp/test")
        mem_session.add(item)
        mem_session.commit()
        mem_session.refresh(item)

        img_path = tmp_path / "drive.img"
        format_fat16(img_path, 10)
        write_file_to_image(img_path, "game.exe", b"some game data")

        drive = Drive(library_item_id=item.id, name="Test Drive", size_mb=10, image_path=str(img_path))
        mem_session.add(drive)
        mem_session.commit()
        mem_session.refresh(drive)
        item.drive_id = drive.id
        mem_session.add(item)
        mem_session.commit()

        with pytest.raises(RuntimeError):
            update_drive_for_item(item, 99999, mem_session)

        # Original image must be untouched on a rejected resize.
        assert read_file_from_image(img_path, "game.exe") == b"some game data"
