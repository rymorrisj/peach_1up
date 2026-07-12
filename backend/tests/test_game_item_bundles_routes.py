"""Route-level (TestClient/HTTP) tests for backend/api/routes/game_item_bundles.py.

Per dev_docs/v2/09_test_coverage.md item 3 — the largest untested route file
(699 lines) and a parental-control-adjacent surface. Prior to this file, only
/confirm-delete and DELETE were exercised (test_upload.py). This file covers
the route's other untested surfaces:

    - GET/PUT .../restrictions (is_admin gate)
    - POST /software/import-from-path (can_manage_game gate)
    - POST /software/scan/import (can_manage_game gate)
    - PATCH .../items/reorder (can_manage_game gate)
    - POST .../flag-launch (can_launch_media gate)

Does NOT duplicate the get_filtered_game_item_bundles/get_filtered_game_item_bundle
rating-filter coverage already in test_dependencies_content_rating.py
(TestGetFilteredCollectionsUnknownRatingDenies, TestGetFilteredCollection,
TestSoftwareListRouteFiltering, TestGameItemBundleDetailRouteNoLeak).

Uses the same in-memory SQLModel SQLite DB + StaticPool +
get_active_user/get_db dependency-override pattern as
test_dependencies_content_rating.py and test_users_create_delete_reset.py.
"""

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mem_db_session():
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


def _make_user(db, **overrides):
    from backend.models.user import UserItem

    kwargs = dict(name="UserItem", is_owner=False, is_admin=False)
    kwargs.update(overrides)
    user = UserItem(**kwargs)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_collection(db, **overrides):
    from backend.models.game import GameItemBundle

    kwargs = dict(title="Doom", file_path="/library/games/dos/doom", era="dos", slug="doom")
    kwargs.update(overrides)
    collection = GameItemBundle(**kwargs)
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return collection


def _make_item(db, collection_id, **overrides):
    from backend.models.game import GameItem

    kwargs = dict(game_item_bundle_id=collection_id, disc_number=1, file_path="/library/games/dos/doom/doom.exe")
    kwargs.update(overrides)
    item = GameItem(**kwargs)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture
def http_client(mem_db_session):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import game_item_bundles
    from backend.core.database import get_db

    app = FastAPI()
    app.include_router(game_item_bundles.router)
    app.dependency_overrides[get_db] = lambda: mem_db_session

    with TestClient(app) as c:
        yield c, mem_db_session, app


def _set_active_user(app, user):
    from backend.core.dependencies import get_active_user

    app.dependency_overrides[get_active_user] = lambda: user


class _FakeSettings:
    """Same shape as test_upload.py's _FakeSettings: env dict backs
    get_env_var (used directly by import_from_path for media_root), extra
    dict backs get (used by allowed_browse_roots' svc.get(key, "") lookups)."""

    def __init__(self, env: dict, extra: dict | None = None):
        self._env = env
        self._extra = extra if extra is not None else env

    def get_env_var(self, key):
        return self._env.get(key, "")

    def get(self, key, default=None):
        return self._extra.get(key, default)


# ---------------------------------------------------------------------------
# GET/PUT .../restrictions — is_admin gate
# ---------------------------------------------------------------------------


class TestRestrictionsEndpoint:
    def test_non_admin_gets_403_on_get(self, http_client):
        c, db, app = http_client
        collection = _make_collection(db)
        non_admin = _make_user(db, can_manage_game=True, is_admin=False)
        _set_active_user(app, non_admin)

        resp = c.get(f"/api/v1/game-item-bundle/{collection.id}/restrictions")
        assert resp.status_code == 403, resp.text

    def test_admin_gets_restriction_list(self, http_client):
        from backend.models.media_restriction import MediaRestriction

        c, db, app = http_client
        collection = _make_collection(db)
        restricted_user = _make_user(db, name="Kid")
        db.add(MediaRestriction(user_item_id=restricted_user.id, game_item_bundle_id=collection.id))
        db.commit()
        admin = _make_user(db, name="Admin", is_admin=True)
        _set_active_user(app, admin)

        resp = c.get(f"/api/v1/game-item-bundle/{collection.id}/restrictions")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"restricted_user_item_ids": [restricted_user.id]}

    def test_non_admin_gets_403_on_put(self, http_client):
        c, db, app = http_client
        collection = _make_collection(db)
        non_admin = _make_user(db, can_manage_game=True, is_admin=False)
        _set_active_user(app, non_admin)

        resp = c.put(
            f"/api/v1/game-item-bundle/{collection.id}/restrictions",
            json={"user_item_ids": [non_admin.id]},
        )
        assert resp.status_code == 403, resp.text

    def test_admin_put_delete_then_reinsert_persists(self, http_client):
        """set_restrictions deletes all existing rows for the collection then
        reinserts the new list — confirm a second PUT with a different set
        actually replaces (not merges with) the first."""
        from backend.models.media_restriction import MediaRestriction

        c, db, app = http_client
        collection = _make_collection(db)
        user_a = _make_user(db, name="A")
        user_b = _make_user(db, name="B")
        admin = _make_user(db, name="Admin", is_admin=True)
        _set_active_user(app, admin)

        first = c.put(
            f"/api/v1/game-item-bundle/{collection.id}/restrictions",
            json={"user_item_ids": [user_a.id]},
        )
        assert first.status_code == 200, first.text
        assert first.json() == {"restricted_user_item_ids": [user_a.id]}

        second = c.put(
            f"/api/v1/game-item-bundle/{collection.id}/restrictions",
            json={"user_item_ids": [user_b.id]},
        )
        assert second.status_code == 200, second.text
        assert second.json() == {"restricted_user_item_ids": [user_b.id]}

        db.expire_all()
        rows = db.query(MediaRestriction).filter(
            MediaRestriction.game_item_bundle_id == collection.id
        ).all()
        persisted_ids = {r.user_item_id for r in rows}
        assert persisted_ids == {user_b.id}


# ---------------------------------------------------------------------------
# POST /software/import-from-path — can_manage_game gate
# ---------------------------------------------------------------------------


class TestImportFromPath:
    @pytest.fixture
    def client(self, tmp_path, mem_db_session, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.api.routes import game_item_bundles
        from backend.core.database import get_db

        source_dir = tmp_path / "incoming"
        source_dir.mkdir()

        import backend.core.settings as settings_mod
        monkeypatch.setattr(
            settings_mod,
            "get_settings",
            lambda: _FakeSettings({"SOFTWARE_PATH": str(source_dir)}),
        )
        # _enforce_rate_limit calls rate_limit.check_and_record directly (not
        # rate_limit.enforce), and its module-level counters persist across
        # test methods within the same process — bypass it at the source.
        monkeypatch.setattr(game_item_bundles, "_enforce_rate_limit", lambda *a, **kw: None)

        app = FastAPI()
        app.include_router(game_item_bundles.router)
        app.dependency_overrides[get_db] = lambda: mem_db_session

        with TestClient(app) as c:
            yield c, mem_db_session, app, source_dir

    def test_non_permitted_user_gets_403(self, client):
        c, db, app, source_dir = client
        source_file = source_dir / "game.iso"
        source_file.write_bytes(b"not a real iso but enough bytes")
        non_permitted = _make_user(db, can_manage_game=False, is_admin=False)
        _set_active_user(app, non_permitted)

        resp = c.post(
            "/api/v1/game-items/import-from-path",
            json={"source_path": str(source_file), "title": "Game"},
        )
        assert resp.status_code == 403, resp.text

    def test_permitted_user_succeeds(self, client):
        c, db, app, source_dir = client
        source_file = source_dir / "game.iso"
        source_file.write_bytes(b"not a real iso but enough bytes")
        permitted = _make_user(db, can_manage_game=True, is_admin=False)
        _set_active_user(app, permitted)

        resp = c.post(
            "/api/v1/game-items/import-from-path",
            json={"source_path": str(source_file), "title": "Game"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["title"] == "Game"


# ---------------------------------------------------------------------------
# POST /software/scan/import — can_manage_game gate
# ---------------------------------------------------------------------------


class TestScanImport:
    @pytest.fixture
    def client(self, tmp_path, mem_db_session, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.api.routes import game_item_bundles
        from backend.core.database import get_db

        # No SOFTWARE_PATH configured on purpose: _prepare_item's loose-file
        # branch with games_root_str empty leaves the source file in place
        # (folder_owned=False) rather than moving/renaming it, keeping this
        # fixture free of the folder-ingest machinery this test isn't about.
        import backend.core.settings as settings_mod
        monkeypatch.setattr(settings_mod, "get_settings", lambda: _FakeSettings({}))

        app = FastAPI()
        app.include_router(game_item_bundles.router)
        app.dependency_overrides[get_db] = lambda: mem_db_session

        with TestClient(app) as c:
            yield c, mem_db_session, app

    def test_non_permitted_user_gets_403(self, client, tmp_path):
        c, db, app = client
        source_file = tmp_path / "game.iso"
        source_file.write_bytes(b"content")
        non_permitted = _make_user(db, can_manage_game=False, is_admin=False)
        _set_active_user(app, non_permitted)

        resp = c.post(
            "/api/v1/game-items/scan/import",
            json={"selected": [{"path": str(source_file), "title": "Game"}]},
        )
        assert resp.status_code == 403, resp.text

    def test_permitted_user_succeeds_and_imports(self, client, tmp_path):
        from backend.models.game import GameItemBundle

        c, db, app = client
        source_file = tmp_path / "game.iso"
        source_file.write_bytes(b"content")
        permitted = _make_user(db, can_manage_game=True, is_admin=False)
        _set_active_user(app, permitted)

        resp = c.post(
            "/api/v1/game-items/scan/import",
            json={"selected": [{"path": str(source_file), "title": "Game"}]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["imported"] == 1
        assert body["errors"] == []

        created = db.query(GameItemBundle).filter(GameItemBundle.title == "Game").first()
        assert created is not None


# ---------------------------------------------------------------------------
# PATCH .../items/reorder — can_manage_game gate
# ---------------------------------------------------------------------------


class TestItemsReorder:
    def test_non_permitted_user_gets_403(self, http_client):
        c, db, app = http_client
        collection = _make_collection(db)
        item1 = _make_item(db, collection.id, disc_number=1, file_path="/disc1")
        item2 = _make_item(db, collection.id, disc_number=2, file_path="/disc2")
        non_permitted = _make_user(db, can_manage_game=False, is_admin=False)
        _set_active_user(app, non_permitted)

        resp = c.patch(
            f"/api/v1/game-item-bundle/{collection.id}/items/reorder",
            json={"disc_order": [item2.id, item1.id]},
        )
        assert resp.status_code == 403, resp.text

    def test_permitted_user_reorder_persists_in_db(self, http_client):
        from backend.models.game import GameItemBundle, GameItem

        c, db, app = http_client
        collection = _make_collection(db)
        item1 = _make_item(db, collection.id, disc_number=1, file_path="/disc1")
        item2 = _make_item(db, collection.id, disc_number=2, file_path="/disc2")
        permitted = _make_user(db, can_manage_game=True, is_admin=False)
        _set_active_user(app, permitted)

        resp = c.patch(
            f"/api/v1/game-item-bundle/{collection.id}/items/reorder",
            json={"disc_order": [item2.id, item1.id]},
        )
        assert resp.status_code == 200, resp.text

        db.expire_all()
        reloaded_item2 = db.get(GameItem, item2.id)
        reloaded_item1 = db.get(GameItem, item1.id)
        assert reloaded_item2.disc_number == 1
        assert reloaded_item1.disc_number == 2

        reloaded_collection = db.get(GameItemBundle, collection.id)
        assert reloaded_collection.launch_disk_id == item2.id


# ---------------------------------------------------------------------------
# POST .../flag-launch — can_launch_media gate
# ---------------------------------------------------------------------------


class TestFlagLaunch:
    def test_non_permitted_user_gets_403(self, http_client):
        from backend.models.game import GameItemBundle

        c, db, app = http_client
        collection = _make_collection(db, launch_review_flagged=False)
        non_permitted = _make_user(db, can_launch_media=False, is_admin=False)
        _set_active_user(app, non_permitted)

        resp = c.post(f"/api/v1/game-item-bundle/{collection.id}/flag-launch")
        assert resp.status_code == 403, resp.text

        db.expire_all()
        reloaded = db.get(GameItemBundle, collection.id)
        assert reloaded.launch_review_flagged is False

    def test_permitted_user_flag_persists(self, http_client):
        from backend.models.game import GameItemBundle

        c, db, app = http_client
        collection = _make_collection(db, launch_review_flagged=False)
        permitted = _make_user(db, can_launch_media=True, is_admin=False)
        _set_active_user(app, permitted)

        resp = c.post(f"/api/v1/game-item-bundle/{collection.id}/flag-launch")
        assert resp.status_code == 200, resp.text
        assert resp.json()["launch_review_flagged"] is True

        db.expire_all()
        reloaded = db.get(GameItemBundle, collection.id)
        assert reloaded.launch_review_flagged is True
