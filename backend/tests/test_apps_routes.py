"""Route-level (TestClient/HTTP) tests for backend/api/routes/apps.py
(9 routes, mounted at /api/v1/app-item*).

AppItemBundle has no content_rating/max_content_rating, so the manual
MediaRestriction blocklist is the whole parental-control surface here.

    - can_manage_app gating on create/update/delete/confirm-delete
    - the blocklist 404s a restricted app on GET /app-item-bundle/{id} and
      excludes it from GET /app-items
    - owner bypasses both the permission gate and the blocklist filter
    - leaf-level (/app-item/{id}) visibility inherits the parent bundle's
      blocklist filter via _visible_leaf

In-memory SQLModel SQLite + StaticPool + get_active_user/get_db dependency
overrides, as in test_drives_routes.py.
"""

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


def _make_app_bundle(db, **overrides):
    from backend.models.app import AppItemBundle

    kwargs = dict(title="Notepad++", platform="winxp")
    kwargs.update(overrides)
    bundle = AppItemBundle(**kwargs)
    db.add(bundle)
    db.commit()
    db.refresh(bundle)
    return bundle


def _make_app_item(db, bundle, **overrides):
    from backend.models.app import AppItem

    kwargs = dict(app_item_bundle_id=bundle.id, file_path="/library/apps/winxp/notepad/notepad.exe")
    kwargs.update(overrides)
    item = AppItem(**kwargs)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _restrict(db, user, bundle):
    from backend.models.media_restriction import MediaRestriction

    restriction = MediaRestriction(user_item_id=user.id, app_item_bundle_id=bundle.id)
    db.add(restriction)
    db.commit()


@pytest.fixture
def http_client(mem_db_session):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import apps
    from backend.core.database import get_db

    app = FastAPI()
    app.include_router(apps.router)
    app.dependency_overrides[get_db] = lambda: mem_db_session

    with TestClient(app) as c:
        yield c, mem_db_session, app


def _set_active_user(app, user):
    from backend.core.dependencies import get_active_user

    app.dependency_overrides[get_active_user] = lambda: user


# PATCH /app-item/{id}: unset vs null, fail-closed containment


@pytest.fixture
def app_library(tmp_path, monkeypatch):
    """SOFTWARE_PATH and LIBRARY_PATH under tmp_path, so tmp_path files are
    inside the permitted roots."""
    import backend.core.settings as core_settings

    root = tmp_path / "library"
    (root / "software").mkdir(parents=True)

    class _Settings:
        def get(self, key, default=None):
            return {"SOFTWARE_PATH": str(root / "software"), "LIBRARY_PATH": str(root)}.get(key, default)

    monkeypatch.setattr(core_settings, "get_settings", lambda: _Settings())
    from backend.service.utils import settings as settings_mod

    monkeypatch.setattr(settings_mod, "get", _Settings().get)
    return root


class TestAppLeafPatch:
    def _owner_and_leaf(self, http_client, **leaf_fields):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, is_owner=True, can_manage_app=True))
        return c, db, _make_app_item(db, _make_app_bundle(db), **leaf_fields)

    def test_explicit_null_clears_cover_and_executable_and_omitted_fields_stay(self, http_client, app_library):
        cover = app_library / "cover.png"
        cover.write_bytes(b"png")
        c, db, leaf = self._owner_and_leaf(
            http_client,
            cover_art_path=str(cover),
            executable_path=str(app_library / "app.exe"),
        )

        resp = c.patch(f"/api/v1/app-item/{leaf.id}", json={"cover_art_path": None})
        assert resp.status_code == 200, resp.text
        db.refresh(leaf)
        assert leaf.cover_art_path is None
        assert leaf.executable_path == str(app_library / "app.exe")

        resp = c.patch(f"/api/v1/app-item/{leaf.id}", json={"executable_path": None})
        assert resp.status_code == 200, resp.text
        db.refresh(leaf)
        assert leaf.executable_path is None
        assert cover.read_bytes() == b"png"

    def test_unset_software_path_fails_closed_with_503(self, http_client, tmp_path, monkeypatch):
        import backend.core.settings as core_settings

        class _Unset:
            def get(self, key, default=None):
                return default

        monkeypatch.setattr(core_settings, "get_settings", lambda: _Unset())
        exe = tmp_path / "app.exe"
        exe.write_bytes(b"MZ")
        c, db, leaf = self._owner_and_leaf(http_client)

        resp = c.patch(f"/api/v1/app-item/{leaf.id}", json={"executable_path": str(exe)})

        assert resp.status_code == 503, resp.text
        assert resp.json()["detail"] == "SOFTWARE_PATH is not configured."
        db.refresh(leaf)
        assert leaf.executable_path is None

    def test_path_errors_are_generic_and_never_echo_the_path(self, http_client, app_library):
        c, db, leaf = self._owner_and_leaf(http_client)
        missing = app_library / "software" / "missing.exe"

        resp = c.patch(f"/api/v1/app-item/{leaf.id}", json={"executable_path": str(missing)})

        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"] == "executable_path does not exist."
        assert str(app_library) not in resp.text


# ---------------------------------------------------------------------------
# can_manage_app gating
# ---------------------------------------------------------------------------


class TestCanManageAppGate:
    def test_create_403_for_non_editor(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, can_manage_app=False))

        resp = c.post(
            "/api/v1/app-items", json={"title": "New App", "file_path": "/library/apps/x", "platform": "winxp"}
        )

        assert resp.status_code == 403, resp.text

    def test_update_403_for_non_editor(self, http_client):
        c, db, app = http_client
        bundle = _make_app_bundle(db)
        _set_active_user(app, _make_user(db, can_manage_app=False))

        resp = c.patch(f"/api/v1/app-item-bundle/{bundle.id}", json={"title": "Renamed"})

        assert resp.status_code == 403, resp.text

    def test_confirm_delete_403_for_non_editor(self, http_client):
        c, db, app = http_client
        bundle = _make_app_bundle(db)
        _set_active_user(app, _make_user(db, can_manage_app=False))

        resp = c.post(f"/api/v1/app-item-bundle/{bundle.id}/confirm-delete")

        assert resp.status_code == 403, resp.text

    def test_delete_403_for_non_editor(self, http_client):
        c, db, app = http_client
        bundle = _make_app_bundle(db)
        _set_active_user(app, _make_user(db, can_manage_app=False))

        resp = c.delete(f"/api/v1/app-item-bundle/{bundle.id}?confirmation_token=garbage")

        assert resp.status_code == 403, resp.text

    def test_update_leaf_403_for_non_editor(self, http_client):
        c, db, app = http_client
        bundle = _make_app_bundle(db)
        item = _make_app_item(db, bundle)
        _set_active_user(app, _make_user(db, can_manage_app=False))

        resp = c.patch(f"/api/v1/app-item/{item.id}", json={})

        assert resp.status_code == 403, resp.text

    def test_delete_leaf_403_for_non_editor(self, http_client):
        c, db, app = http_client
        bundle = _make_app_bundle(db)
        item = _make_app_item(db, bundle)
        _set_active_user(app, _make_user(db, can_manage_app=False))

        resp = c.delete(f"/api/v1/app-item/{item.id}")

        assert resp.status_code == 403, resp.text

    def test_confirm_delete_200_for_editor(self, http_client):
        c, db, app = http_client
        bundle = _make_app_bundle(db)
        _set_active_user(app, _make_user(db, can_manage_app=True))

        resp = c.post(f"/api/v1/app-item-bundle/{bundle.id}/confirm-delete")

        assert resp.status_code == 200, resp.text
        assert "confirmation_token" in resp.json()


# ---------------------------------------------------------------------------
# Manual blocklist (MediaRestriction), the Apps parental-control surface
# ---------------------------------------------------------------------------


class TestBlocklistFiltering:
    def test_restricted_bundle_404s_on_detail(self, http_client):
        c, db, app = http_client
        user = _make_user(db)
        bundle = _make_app_bundle(db)
        _restrict(db, user, bundle)
        _set_active_user(app, user)

        resp = c.get(f"/api/v1/app-item-bundle/{bundle.id}")

        assert resp.status_code == 404, resp.text

    def test_restricted_bundle_excluded_from_list(self, http_client):
        c, db, app = http_client
        user = _make_user(db)
        visible = _make_app_bundle(db, title="Visible App")
        restricted = _make_app_bundle(db, title="Restricted App")
        _restrict(db, user, restricted)
        _set_active_user(app, user)

        resp = c.get("/api/v1/app-items")

        assert resp.status_code == 200, resp.text
        titles = {row["title"] for row in resp.json()["items"]}
        assert titles == {visible.title}

    def test_old_era_filter_param_is_rejected(self, http_client):
        c, db, app = http_client
        _make_app_bundle(db, title="Visible App")
        _set_active_user(app, _make_user(db))

        resp = c.get("/api/v1/app-items", params={"era": "dos"})

        assert resp.status_code == 422
        assert "platform" in resp.json()["detail"]

    def test_restricted_leaf_404s_via_parent_bundle_filter(self, http_client):
        c, db, app = http_client
        user = _make_user(db)
        bundle = _make_app_bundle(db)
        item = _make_app_item(db, bundle)
        _restrict(db, user, bundle)
        _set_active_user(app, user)

        resp = c.get(f"/api/v1/app-item/{item.id}")

        assert resp.status_code == 404, resp.text

    def test_owner_bypasses_blocklist(self, http_client):
        c, db, app = http_client
        owner = _make_user(db, is_owner=True)
        bundle = _make_app_bundle(db)
        # Restriction row targets a different (non-owner) user; irrelevant
        # here since the owner check short-circuits before any filter.
        other = _make_user(db, name="other")
        _restrict(db, other, bundle)
        _set_active_user(app, owner)

        resp = c.get(f"/api/v1/app-item-bundle/{bundle.id}")

        assert resp.status_code == 200, resp.text
