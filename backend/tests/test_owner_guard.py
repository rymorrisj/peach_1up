"""Tests for GET /api/v1/settings/owner-status: detects a missing/locked
owner row so the frontend can render the recovery fallback page.

Checked once at app load (FirstRunGuard in main.tsx), not on every request —
there is no middleware backing this anymore.
"""

import pytest


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


@pytest.fixture
def app_client(mem_session):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import settings
    from backend.core.database import get_db

    app = FastAPI()
    app.include_router(settings.router)
    app.dependency_overrides[get_db] = lambda: mem_session

    with TestClient(app) as client:
        yield client


class TestOwnerStatus:
    def test_missing_owner_reports_broken(self, app_client):
        resp = app_client.get("/api/v1/settings/owner-status")

        assert resp.status_code == 200
        assert resp.json() == {"owner_broken": True}

    def test_locked_owner_reports_broken(self, app_client, mem_session):
        from backend.models.user import UserItem

        mem_session.add(UserItem(name="Owner", is_owner=True, is_locked=True))
        mem_session.commit()

        resp = app_client.get("/api/v1/settings/owner-status")

        assert resp.status_code == 200
        assert resp.json() == {"owner_broken": True}

    def test_present_unlocked_owner_reports_healthy(self, app_client, mem_session):
        from backend.models.user import UserItem

        mem_session.add(UserItem(name="Owner", is_owner=True, is_locked=False))
        mem_session.commit()

        resp = app_client.get("/api/v1/settings/owner-status")

        assert resp.status_code == 200
        assert resp.json() == {"owner_broken": False}
