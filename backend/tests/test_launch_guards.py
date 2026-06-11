"""Tests for launch concurrency and validation guards in
service/launch/coordinator.py.

Note: the spec asked for a test documenting an `update_drive_for_item` stub
that "raises NotImplementedError". No such function exists anywhere in the
codebase (grepped service/launch/ and service/utils/drive_utils.py) — the
closest functions are create_drive_for_item and delete_drive_for_item, both
of which are fully implemented. That case is therefore skipped below with an
explanation rather than fabricated.
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


class TestUpdateDriveForItemStub:
    def test_update_drive_for_item_does_not_exist(self):
        """Documents that no update_drive_for_item stub exists in drive_utils.

        The spec describes a known gap where update_drive_for_item raises
        NotImplementedError. No function with that name exists anywhere in
        the codebase, so there is nothing to call — only create_drive_for_item
        and delete_drive_for_item are implemented.
        """
        from backend.service.utils import drive_utils

        assert not hasattr(drive_utils, "update_drive_for_item")
