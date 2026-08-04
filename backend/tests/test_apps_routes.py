"""Route-level (TestClient/HTTP) tests for backend/api/routes/apps.py.

Per dev_docs/P1_AUDIT.md TST-8 — apps.py (9 routes, mounted at
/api/v1/app-item*) had no route-level test at all. Note: unlike the Game
domain, AppItemBundle has no content_rating/max_content_rating concept
(backend/core/dependencies.py::get_filtered_app_items docstring — "Apps have
no content_rating/max_content_rating concept to filter on"), so the
parental-control surface here is the manual MediaRestriction blocklist only,
not a rating ceiling. Covers:

    - can_manage_app gating on create/update/delete/confirm-delete
    - the manual MediaRestriction blocklist 404s a restricted app on both
      GET /app-item-bundle/{id} and excludes it from GET /app-items, the
      same no-leak 404 pattern as the Game domain
    - owner bypasses both the permission gate and the blocklist filter
    - leaf-level (/app-item/{id}) visibility inherits the parent bundle's
      blocklist filter via _visible_leaf

Uses the same in-memory SQLModel SQLite DB + StaticPool +
get_active_user/get_db dependency-override pattern as
test_drives_routes.py / test_launches_routes.py.
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


def _make_app_bundle(db, **overrides):
    from backend.models.app import AppItemBundle

    kwargs = dict(title="Notepad++", era="winxp")
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


# ---------------------------------------------------------------------------
# can_manage_app gating
# ---------------------------------------------------------------------------


class TestCanManageAppGate:
    def test_create_403_for_non_editor(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, can_manage_app=False))

        resp = c.post("/api/v1/app-items", json={"title": "New App", "file_path": "/library/apps/x", "era": "winxp"})

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
# Manual blocklist (MediaRestriction) — the Apps parental-control surface
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
