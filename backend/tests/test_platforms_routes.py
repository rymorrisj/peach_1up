"""Route/service tests for platform status freshness.

get_platform (GET /platforms/{id}) and get_health_summary both recompute
platform status live via compute_live_status() instead of trusting the
persisted Platform.status column, so the API can't serve a stale value.
These tests construct platforms whose persisted status column deliberately
disagrees with what compute_live_status() would derive from current
filesystem state, to confirm the live value wins.
"""

import pytest


def _owner_user():
    from backend.models.user import User
    return User(id=1, name="Owner", is_owner=True)


@pytest.fixture
def mem_db_session():
    from sqlmodel import SQLModel, Session, create_engine
    from sqlalchemy.pool import StaticPool
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
def client(mem_db_session):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import platforms
    from backend.core.database import get_db
    from backend.core.dependencies import get_active_user

    app = FastAPI()
    app.include_router(platforms.router)
    app.dependency_overrides[get_active_user] = _owner_user
    app.dependency_overrides[get_db] = lambda: mem_db_session

    with TestClient(app) as c:
        yield c, mem_db_session


def _make_platform(db, **overrides):
    from backend.models.platform import Platform

    kwargs = dict(
        name="Win98 Box",
        era="win98",
        emulator_slug="86box",
        status="healthy",
        working_image_path=None,
        base_image_path=None,
    )
    kwargs.update(overrides)
    platform = Platform(**kwargs)
    db.add(platform)
    db.commit()
    db.refresh(platform)
    return platform


class TestGetPlatformLiveStatus:
    def test_returns_live_status_not_stale_persisted_column(self, client):
        c, db = client
        # Persisted column says "healthy", but with no working/base image
        # paths present, compute_live_status() must derive "unconfigured".
        platform = _make_platform(db, status="healthy")

        resp = c.get(f"/api/v1/platforms/{platform.id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "unconfigured"
        assert body["status"] != "healthy"

    def test_live_status_reflects_missing_working_image_as_degraded(self, client, tmp_path):
        c, db = client
        base_image = tmp_path / "base.img"
        base_image.write_bytes(b"x" * 512)
        # base image exists on disk but working image path doesn't -> "degraded",
        # regardless of what the persisted status column claims.
        platform = _make_platform(
            db,
            status="healthy",
            base_image_path=str(base_image),
            working_image_path=str(tmp_path / "missing-working.img"),
        )

        resp = c.get(f"/api/v1/platforms/{platform.id}")

        assert resp.status_code == 200
        assert resp.json()["status"] == "degraded"


class TestGetHealthSummary:
    def test_unconfigured_platform_buckets_separately_from_degraded(self, mem_db_session):
        from backend.service.platforms import environments as plat_svc

        db = mem_db_session
        # No working/base image paths -> compute_live_status() == "unconfigured".
        _make_platform(db, status="healthy")

        summary = plat_svc.get_health_summary(db)

        assert summary["platforms"]["total"] == 1
        assert summary["platforms"]["unconfigured"] == 1
        assert summary["platforms"]["degraded"] == 0

    def test_no_unknown_bucket_in_response(self, mem_db_session):
        from backend.service.platforms import environments as plat_svc

        db = mem_db_session
        _make_platform(db, status="healthy")

        summary = plat_svc.get_health_summary(db)

        assert "unknown" not in summary["platforms"]
        assert set(summary["platforms"].keys()) == {"total", "healthy", "degraded", "unconfigured"}
