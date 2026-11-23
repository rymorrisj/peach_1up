"""Route-level (TestClient/HTTP) tests for the leaf routes in
backend/api/routes/game_items.py.

Scoped to what a capped sub-account may see or verify at HTTP;
test_game_items.py covers the _prepare_item service helper. Covers:

    - GET /game-item/{leaf_id} 404s (no leak) when the parent bundle is
      denied by either the manual MediaRestriction blocklist or the
      max_content_rating ceiling, mirroring the bundle-level deny pattern
    - GET /game-item/{leaf_id} succeeds for a leaf whose parent bundle the
      caller may see
    - owner bypasses both filters
    - POST /game-item/{leaf_id}/verify enforces the same parent-bundle
      visibility filter as GET, via _visible_leaf, before calling
      backend.service.games.items.reverify_library_leaf

In-memory SQLModel SQLite + StaticPool + get_active_user/get_db dependency
overrides, as in the other *_routes test files.
"""

import pytest


@pytest.fixture
def mem_db_session():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import SQLModel, Session, create_engine
    import backend.models  # noqa: F401, registers all table models with SQLModel.metadata

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


def _make_game_bundle(db, **overrides):
    from backend.models.game import GameItemBundle

    kwargs = dict(title="Doom", file_path="/library/games/dos/doom", platform="dos", slug="doom")
    kwargs.update(overrides)
    bundle = GameItemBundle(**kwargs)
    db.add(bundle)
    db.commit()
    db.refresh(bundle)
    return bundle


def _make_leaf(db, bundle, **overrides):
    from backend.models.game import GameItem

    kwargs = dict(game_item_bundle_id=bundle.id, file_path="/library/games/dos/doom/doom.exe")
    kwargs.update(overrides)
    leaf = GameItem(**kwargs)
    db.add(leaf)
    db.commit()
    db.refresh(leaf)
    return leaf


def _restrict(db, user, bundle):
    from backend.models.media_restriction import MediaRestriction

    restriction = MediaRestriction(user_item_id=user.id, game_item_bundle_id=bundle.id)
    db.add(restriction)
    db.commit()


@pytest.fixture
def http_client(mem_db_session):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import game_items
    from backend.core.database import get_db

    app = FastAPI()
    app.include_router(game_items.router)
    app.dependency_overrides[get_db] = lambda: mem_db_session

    with TestClient(app) as c:
        yield c, mem_db_session, app


def _set_active_user(app, user):
    from backend.core.dependencies import get_active_user

    app.dependency_overrides[get_active_user] = lambda: user


# ---------------------------------------------------------------------------
# GET /game-item/{leaf_id}, leaf-level deny via the parent bundle's filter
# ---------------------------------------------------------------------------


class TestLeafVisibilityFilter:
    def test_manual_restriction_on_parent_bundle_404s_the_leaf(self, http_client):
        c, db, app = http_client
        user = _make_user(db)
        bundle = _make_game_bundle(db)
        leaf = _make_leaf(db, bundle)
        _restrict(db, user, bundle)
        _set_active_user(app, user)

        resp = c.get(f"/api/v1/game-item/{leaf.id}")

        assert resp.status_code == 404, resp.text

    def test_max_content_rating_ceiling_404s_the_leaf(self, http_client):
        c, db, app = http_client
        user = _make_user(db, max_content_rating="E")
        bundle = _make_game_bundle(db, content_rating="M")
        leaf = _make_leaf(db, bundle)
        _set_active_user(app, user)

        resp = c.get(f"/api/v1/game-item/{leaf.id}")

        assert resp.status_code == 404, resp.text

    def test_visible_leaf_is_returned(self, http_client):
        c, db, app = http_client
        user = _make_user(db)
        bundle = _make_game_bundle(db)
        leaf = _make_leaf(db, bundle)
        _set_active_user(app, user)

        resp = c.get(f"/api/v1/game-item/{leaf.id}")

        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == leaf.id

    def test_owner_bypasses_both_filters(self, http_client):
        c, db, app = http_client
        owner = _make_user(db, is_owner=True, max_content_rating="E")
        bundle = _make_game_bundle(db, content_rating="M")
        leaf = _make_leaf(db, bundle)
        _set_active_user(app, owner)

        resp = c.get(f"/api/v1/game-item/{leaf.id}")

        assert resp.status_code == 200, resp.text

    def test_404_for_nonexistent_leaf(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db))

        resp = c.get("/api/v1/game-item/999999")

        assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# POST /game-item/{leaf_id}/verify, same parent-bundle visibility filter as GET
# ---------------------------------------------------------------------------


class TestVerifyLeafVisibilityFilter:
    def test_max_content_rating_ceiling_404s_verify_even_for_a_can_manage_game_user(self, http_client):
        c, db, app = http_client
        user = _make_user(db, can_manage_game=True, max_content_rating="E")
        bundle = _make_game_bundle(db, content_rating="M")
        leaf = _make_leaf(db, bundle)
        _set_active_user(app, user)

        resp = c.post(f"/api/v1/game-item/{leaf.id}/verify")

        assert resp.status_code == 404, resp.text

    def test_manual_restriction_on_parent_bundle_404s_verify(self, http_client):
        c, db, app = http_client
        user = _make_user(db, can_manage_game=True)
        bundle = _make_game_bundle(db)
        leaf = _make_leaf(db, bundle)
        _restrict(db, user, bundle)
        _set_active_user(app, user)

        resp = c.post(f"/api/v1/game-item/{leaf.id}/verify")

        assert resp.status_code == 404, resp.text

    def test_visible_leaf_can_still_be_verified(self, http_client, tmp_path):
        c, db, app = http_client
        real_file = tmp_path / "doom.exe"
        real_file.write_bytes(b"fake executable contents")
        user = _make_user(db, can_manage_game=True)
        bundle = _make_game_bundle(db)
        leaf = _make_leaf(db, bundle, file_path=str(real_file))
        _set_active_user(app, user)

        resp = c.post(f"/api/v1/game-item/{leaf.id}/verify")

        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == leaf.id

    def test_403_for_non_editor_before_visibility_is_even_checked(self, http_client):
        c, db, app = http_client
        user = _make_user(db, can_manage_game=False)
        bundle = _make_game_bundle(db)
        leaf = _make_leaf(db, bundle)
        _set_active_user(app, user)

        resp = c.post(f"/api/v1/game-item/{leaf.id}/verify")

        assert resp.status_code == 403, resp.text


# PATCH /game-item/{leaf_id}: unset vs null, and cover_art_path confinement


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / "library"
    (root / "media").mkdir(parents=True)

    import backend.core.settings as core_settings
    from backend.service.utils import settings as settings_mod

    monkeypatch.setattr(
        settings_mod, "get", lambda key, default=None: str(root) if key == "LIBRARY_PATH" else default,
    )
    monkeypatch.setattr(core_settings, "get_settings", lambda: settings_mod)
    return root


class TestLeafPatchCover:
    def _owner_and_leaf(self, http_client, **leaf_fields):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, is_owner=True))
        leaf = _make_leaf(db, _make_game_bundle(db), **leaf_fields)
        return c, db, leaf

    def test_cover_inside_the_library_is_saved(self, http_client, library):
        cover = library / "media" / "cover.png"
        cover.write_bytes(b"png")
        c, _, leaf = self._owner_and_leaf(http_client)

        resp = c.patch(f"/api/v1/game-item/{leaf.id}", json={"cover_art_path": str(cover)})

        assert resp.status_code == 200, resp.text
        assert resp.json()["cover_art_url"] == "/media/media/cover.png"

    def test_cover_outside_the_library_is_422_and_not_saved(self, http_client, library, tmp_path):
        outside = tmp_path / "elsewhere" / "cover.png"
        outside.parent.mkdir()
        outside.write_bytes(b"png")
        c, db, leaf = self._owner_and_leaf(http_client)

        resp = c.patch(f"/api/v1/game-item/{leaf.id}", json={"cover_art_path": str(outside)})

        assert resp.status_code == 422, resp.text
        assert "library" in resp.json()["detail"]
        db.refresh(leaf)
        assert leaf.cover_art_path is None

    def test_outside_path_gives_the_same_answer_whether_or_not_it_exists(self, http_client, library, tmp_path):
        existing = tmp_path / "elsewhere.png"
        existing.write_bytes(b"png")
        missing = tmp_path / "missing.png"
        c, _, leaf = self._owner_and_leaf(http_client)

        a = c.patch(f"/api/v1/game-item/{leaf.id}", json={"cover_art_path": str(existing)})
        b = c.patch(f"/api/v1/game-item/{leaf.id}", json={"cover_art_path": str(missing)})

        assert a.status_code == b.status_code == 422
        assert a.json()["detail"] == b.json()["detail"]
        assert str(tmp_path) not in a.json()["detail"]

    def test_explicit_null_clears_cover_and_executable_but_keeps_the_file(self, http_client, library):
        cover = library / "media" / "cover.png"
        cover.write_bytes(b"png")
        c, db, leaf = self._owner_and_leaf(
            http_client, cover_art_path=str(cover), executable_path=str(library / "game.exe"),
        )

        resp = c.patch(
            f"/api/v1/game-item/{leaf.id}", json={"cover_art_path": None, "executable_path": None},
        )

        assert resp.status_code == 200, resp.text
        db.refresh(leaf)
        assert leaf.cover_art_path is None
        assert leaf.executable_path is None
        assert cover.read_bytes() == b"png"

    def test_omitted_fields_are_left_alone(self, http_client, library):
        cover = library / "media" / "cover.png"
        cover.write_bytes(b"png")
        c, db, leaf = self._owner_and_leaf(
            http_client, cover_art_path=str(cover), executable_path=str(library / "game.exe"),
        )

        resp = c.patch(f"/api/v1/game-item/{leaf.id}", json={"cover_art_path": None})

        assert resp.status_code == 200, resp.text
        db.refresh(leaf)
        assert leaf.cover_art_path is None
        assert leaf.executable_path == str(library / "game.exe")

    def test_existing_cover_outside_the_library_survives_an_unrelated_patch(self, http_client, library, tmp_path):
        stored = str(tmp_path / "old" / "cover.png")
        c, db, leaf = self._owner_and_leaf(http_client, cover_art_path=stored)

        resp = c.patch(f"/api/v1/game-item/{leaf.id}", json={})

        assert resp.status_code == 200, resp.text
        db.refresh(leaf)
        assert leaf.cover_art_path == stored
