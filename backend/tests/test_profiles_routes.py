"""Route-level (TestClient/HTTP) tests for backend/api/routes/profiles.py.

Per dev_docs/P1_AUDIT.md TST-12, profiles.py (6 routes) had zero test
coverage: can_manage_game gating, the is_bundled delete guard, and the
slug-collision 409 were all unexercised. Covers:

    - can_manage_game gating (403) on create/update/delete
    - GET routes require only an active user (no permission flag), and 404
      on an unknown slug
    - POST "" 409s on a slug collision
    - DELETE /{slug} 403s a bundled profile, regardless of can_manage_game
    - update renames trigger a fresh unique_slug (name change updates slug)

Uses the same in-memory SQLModel SQLite DB + StaticPool +
get_active_user/get_db dependency-override pattern as the other *_routes
test files.
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


def _make_profile(db, **overrides):
    from backend.models.profile import ProfileItem

    kwargs = dict(name="DOS Profile", slug="dos-profile", emulator_slug="dosbox-x", era="dos")
    kwargs.update(overrides)
    profile = ProfileItem(**kwargs)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@pytest.fixture
def http_client(mem_db_session):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import profiles
    from backend.core.database import get_db

    app = FastAPI()
    app.include_router(profiles.router)
    app.dependency_overrides[get_db] = lambda: mem_db_session

    with TestClient(app) as c:
        yield c, mem_db_session, app


def _set_active_user(app, user):
    from backend.core.dependencies import get_active_user

    app.dependency_overrides[get_active_user] = lambda: user


# ---------------------------------------------------------------------------
# can_manage_game gate
# ---------------------------------------------------------------------------


class TestCanManageGameGate:
    def test_create_403_for_non_editor(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, can_manage_game=False))

        resp = c.post(
            "/api/v1/profile-items",
            json={"name": "New Profile", "slug": "new-profile", "emulator_slug": "dosbox-x", "era": "dos"},
        )

        assert resp.status_code == 403, resp.text

    def test_update_403_for_non_editor(self, http_client):
        c, db, app = http_client
        profile = _make_profile(db)
        _set_active_user(app, _make_user(db, can_manage_game=False))

        resp = c.patch(f"/api/v1/profile-items/{profile.slug}", json={"notes": "hi"})

        assert resp.status_code == 403, resp.text

    def test_delete_403_for_non_editor(self, http_client):
        c, db, app = http_client
        profile = _make_profile(db)
        _set_active_user(app, _make_user(db, can_manage_game=False))

        resp = c.delete(f"/api/v1/profile-items/{profile.slug}")

        assert resp.status_code == 403, resp.text

    def test_create_201_for_editor(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, can_manage_game=True))

        resp = c.post(
            "/api/v1/profile-items",
            json={"name": "New Profile", "slug": "new-profile", "emulator_slug": "dosbox-x", "era": "dos"},
        )

        assert resp.status_code == 201, resp.text


# ---------------------------------------------------------------------------
# GET routes, no permission flag, just an active user
# ---------------------------------------------------------------------------


class TestReadRoutes:
    def test_list_ok_with_plain_active_user(self, http_client):
        c, db, app = http_client
        _make_profile(db)
        _set_active_user(app, _make_user(db))

        resp = c.get("/api/v1/profile-items")

        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] == 1

    def test_get_404_for_unknown_slug(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db))

        resp = c.get("/api/v1/profile-items/does-not-exist")

        assert resp.status_code == 404, resp.text

    def test_get_items_404_for_unknown_slug(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db))

        resp = c.get("/api/v1/profile-items/does-not-exist/items")

        assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# Slug collision
# ---------------------------------------------------------------------------


class TestSlugCollision:
    def test_create_409_on_slug_collision(self, http_client):
        c, db, app = http_client
        _make_profile(db, slug="dos-profile")
        _set_active_user(app, _make_user(db, can_manage_game=True))

        resp = c.post(
            "/api/v1/profile-items",
            json={"name": "Another Name", "slug": "dos-profile", "emulator_slug": "dosbox-x", "era": "dos"},
        )

        assert resp.status_code == 409, resp.text


# ---------------------------------------------------------------------------
# is_bundled delete guard
# ---------------------------------------------------------------------------


class TestBundledDeleteGuard:
    def test_delete_403_for_bundled_profile_even_as_editor(self, http_client):
        c, db, app = http_client
        profile = _make_profile(db, is_bundled=True)
        _set_active_user(app, _make_user(db, can_manage_game=True))

        resp = c.delete(f"/api/v1/profile-items/{profile.slug}")

        assert resp.status_code == 403, resp.text

    def test_delete_204_for_non_bundled_profile_as_editor(self, http_client):
        c, db, app = http_client
        profile = _make_profile(db, is_bundled=False)
        _set_active_user(app, _make_user(db, can_manage_game=True))

        resp = c.delete(f"/api/v1/profile-items/{profile.slug}")

        assert resp.status_code == 204, resp.text


# ---------------------------------------------------------------------------
# Update renames trigger a fresh slug
# ---------------------------------------------------------------------------


class TestUpdateRename:
    def test_name_change_regenerates_slug(self, http_client):
        c, db, app = http_client
        profile = _make_profile(db, name="Old Name", slug="old-name")
        _set_active_user(app, _make_user(db, can_manage_game=True))

        resp = c.patch(f"/api/v1/profile-items/{profile.slug}", json={"name": "Brand New Name"})

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["name"] == "Brand New Name"
        assert body["slug"] != "old-name"
