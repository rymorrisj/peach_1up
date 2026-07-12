"""Tests for GET /api/v1/health/storage caching and the drive-images category.

storage_footprint() walks several directory trees unboundedly via _dir_size;
these tests confirm the TTL cache added on top of it avoids re-walking on
repeated calls, that the rescan endpoint busts the cache, and that drive
image usage is now counted in the response.
"""

import pytest


@pytest.fixture(autouse=True)
def _reset_storage_cache():
    from backend.api.routes import health
    health._storage_cache = None
    health._storage_cache_time = 0.0
    yield
    health._storage_cache = None
    health._storage_cache_time = 0.0


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


def _owner_user():
    from backend.models.user import UserItem
    return UserItem(id=1, name="Owner", is_owner=True)


@pytest.fixture
def client(tmp_path, mem_db_session, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import health
    from backend.core.database import get_db
    from backend.core.dependencies import get_active_user
    import backend.core.settings as settings_mod

    base = tmp_path / "base"
    base.mkdir()
    monkeypatch.setattr(settings_mod, "get_base_path", lambda: base)

    app = FastAPI()
    app.include_router(health.router)
    app.dependency_overrides[get_active_user] = _owner_user
    app.dependency_overrides[get_db] = lambda: mem_db_session

    with TestClient(app) as c:
        yield c, mem_db_session, base


class TestStorageCache:
    def test_repeated_calls_within_ttl_do_not_rewalk_filesystem(self, client, monkeypatch):
        from backend.api.routes import health

        c, _db, _base = client
        calls = []
        original_dir_size = health._dir_size

        def counting_dir_size(path):
            calls.append(path)
            return original_dir_size(path)

        monkeypatch.setattr(health, "_dir_size", counting_dir_size)

        resp1 = c.get("/api/v1/health/storage")
        resp2 = c.get("/api/v1/health/storage")

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json() == resp2.json()
        # _dir_size is called once per walked category per computation —
        # a second cache hit must add zero further calls.
        first_call_count = len(calls)
        assert first_call_count > 0
        c.get("/api/v1/health/storage")
        assert len(calls) == first_call_count

    def test_cache_expires_after_ttl(self, client, monkeypatch):
        from backend.api.routes import health

        c, _db, _base = client
        calls = []
        original_dir_size = health._dir_size
        monkeypatch.setattr(health, "_dir_size", lambda p: (calls.append(p), original_dir_size(p))[1])

        c.get("/api/v1/health/storage")
        count_after_first = len(calls)

        # Simulate TTL elapsing without waiting in real time.
        health._storage_cache_time -= health._STORAGE_CACHE_TTL_SECONDS + 1

        c.get("/api/v1/health/storage")
        assert len(calls) > count_after_first


class TestRescanBustsCache:
    def test_rescan_forces_immediate_recompute(self, client, monkeypatch):
        from backend.api.routes import health

        c, _db, _base = client
        calls = []
        original_dir_size = health._dir_size
        monkeypatch.setattr(health, "_dir_size", lambda p: (calls.append(p), original_dir_size(p))[1])

        c.get("/api/v1/health/storage")
        count_after_get = len(calls)
        assert count_after_get > 0

        resp = c.post("/api/v1/health/storage/rescan")
        assert resp.status_code == 200
        # rescan must trigger a fresh compute (not just a no-op cache hit).
        assert len(calls) > count_after_get

        cached_time_after_rescan = health._storage_cache_time
        c.get("/api/v1/health/storage")
        # the subsequent GET should be served from the cache rescan just populated.
        assert health._storage_cache_time == cached_time_after_rescan


class TestDriveImagesCategory:
    def test_drive_images_category_reflects_actual_drive_usage(self, client):
        from backend.models.drive import Drive
        from backend.models.game import GameItemBundle

        c, db, base = client

        image = base / "drive.img"
        image.write_bytes(b"x" * 4096)

        collection = GameItemBundle(title="Game", era="win98", slug="game")
        db.add(collection)
        db.commit()
        db.refresh(collection)

        drive = Drive(name="C:", game_item_bundle_id=collection.id, image_path=str(image))
        db.add(drive)
        db.commit()

        resp = c.get("/api/v1/health/storage")
        assert resp.status_code == 200
        body = resp.json()

        drive_cats = [cat for cat in body["categories"] if cat["key"] == "drive_images"]
        assert len(drive_cats) == 1
        assert drive_cats[0]["size_bytes"] == 4096
        assert drive_cats[0]["size_bytes"] <= body["total_bytes"]

    def test_drive_images_category_zero_when_no_drives(self, client):
        c, _db, _base = client
        resp = c.get("/api/v1/health/storage")
        body = resp.json()
        drive_cats = [cat for cat in body["categories"] if cat["key"] == "drive_images"]
        assert len(drive_cats) == 1
        assert drive_cats[0]["size_bytes"] == 0
