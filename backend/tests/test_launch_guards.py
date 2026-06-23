"""Tests for launch validation guards in service/launch/coordinator.py."""

import pytest
from fastapi import HTTPException


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
