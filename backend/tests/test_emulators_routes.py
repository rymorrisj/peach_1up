"""Route-level (TestClient/HTTP) tests for backend/api/routes/emulators.py.

Per dev_docs/P1_AUDIT.md TST-9, only the rom-packs sub-router had coverage;
install/sandbox/delete/xemu-asset-paths/status/confirm-token were untested,
all is_admin-gated and touching the process-isolation surface. Covers:

    - is_admin gating (403 for non-admin) on: POST /{slug}/install,
      GET /{slug}/status, PATCH /{slug}/sandbox, DELETE /{slug},
      GET/PATCH /xemu/asset-paths, GET /sandbox-state/confirm-token,
      DELETE /sandbox-state
    - the gate runs before the route's own body logic (a garbage slug still
      403s a non-admin rather than 404ing first)
    - owner bypasses the gate without the is_admin flag
    - GET "" (catalog list), GET /attribution, and GET /{slug}/confirm-token
      carry no permission dependency at all in the current code (confirmed
      by reading the route signatures, no Depends/require_permission on any
      of the three) and are reachable with no active user set at all; this
      is documented here as existing behavior, not asserted as a gap to fix.

Uses the same in-memory SQLModel SQLite DB + StaticPool +
get_active_user/get_db dependency-override pattern as
test_drives_routes.py / test_launches_routes.py. Settings access
(_settings.get/set_flag) is monkeypatched the same way
test_emulator_catalog.py does, rather than running real settings.init(),
since these route tests never boot the app lifespan.
"""

import pytest

REAL_SLUG = "dosbox-x"  # config/emulators/dosbox-x.toml exists on disk


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


@pytest.fixture
def http_client(mem_db_session, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import emulators
    from backend.core.database import get_db

    # Route bodies that get past the permission gate touch _settings.get/
    # set_flag, which raise RuntimeError unless settings.init() ran. These
    # tests never boot the real lifespan, so stub both the same way
    # test_emulator_catalog.py does for the same reason.
    monkeypatch.setattr(emulators._settings, "get", lambda key, default=None: default)
    monkeypatch.setattr(emulators._settings, "set_flag", lambda key, value: None)

    app = FastAPI()
    app.include_router(emulators.router)
    app.dependency_overrides[get_db] = lambda: mem_db_session

    with TestClient(app) as c:
        yield c, mem_db_session, app


def _set_active_user(app, user):
    from backend.core.dependencies import get_active_user

    app.dependency_overrides[get_active_user] = lambda: user


# ---------------------------------------------------------------------------
# is_admin gate, 403 for non-admin
# ---------------------------------------------------------------------------


class TestIsAdminGate:
    def test_install_403_for_non_admin(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db))

        resp = c.post(f"/api/v1/emulator-items/{REAL_SLUG}/install")

        assert resp.status_code == 403, resp.text

    def test_status_403_for_non_admin(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db))

        resp = c.get(f"/api/v1/emulator-items/{REAL_SLUG}/status")

        assert resp.status_code == 403, resp.text

    def test_sandbox_patch_403_for_non_admin(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db))

        resp = c.patch(f"/api/v1/emulator-items/{REAL_SLUG}/sandbox", json={"skip_cpu_limit": True})

        assert resp.status_code == 403, resp.text

    def test_delete_403_for_non_admin(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db))

        resp = c.request(
            "DELETE",
            f"/api/v1/emulator-items/{REAL_SLUG}",
            json={"confirmation_token": "garbage"},
        )

        assert resp.status_code == 403, resp.text

    def test_xemu_asset_paths_get_403_for_non_admin(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db))

        resp = c.get("/api/v1/emulator-items/xemu/asset-paths")

        assert resp.status_code == 403, resp.text

    def test_xemu_asset_paths_patch_403_for_non_admin(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db))

        resp = c.patch("/api/v1/emulator-items/xemu/asset-paths", json={"bootrom": "/some/path"})

        assert resp.status_code == 403, resp.text

    def test_sandbox_state_confirm_token_403_for_non_admin(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db))

        resp = c.get("/api/v1/emulator-items/sandbox-state/confirm-token")

        assert resp.status_code == 403, resp.text

    def test_sandbox_state_delete_403_for_non_admin(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db))

        resp = c.request(
            "DELETE",
            "/api/v1/emulator-items/sandbox-state",
            json={"confirmation_token": "garbage"},
        )

        assert resp.status_code == 403, resp.text

    def test_gate_runs_before_existence_check(self, http_client):
        """A non-admin gets 403 on a nonexistent slug, not 404, the
        permission dependency resolves before the route body's get_emulator
        lookup ever runs."""
        c, db, app = http_client
        _set_active_user(app, _make_user(db))

        resp = c.get("/api/v1/emulator-items/not-a-real-slug/status")

        assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Owner bypass
# ---------------------------------------------------------------------------


class TestOwnerBypass:
    def test_owner_passes_gate_without_is_admin_flag(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, is_owner=True, is_admin=False))

        resp = c.get(f"/api/v1/emulator-items/{REAL_SLUG}/status")

        assert resp.status_code == 200, resp.text

    def test_admin_passes_gate(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, is_admin=True))

        resp = c.get(f"/api/v1/emulator-items/{REAL_SLUG}/status")

        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# No permission dependency at all, reachable with no active user configured
# ---------------------------------------------------------------------------


class TestUngatedRoutes:
    def test_catalog_list_reachable_with_no_active_user(self, http_client):
        c, db, app = http_client

        resp = c.get("/api/v1/emulator-items")

        assert resp.status_code == 200, resp.text

    def test_attribution_reachable_with_no_active_user(self, http_client):
        c, db, app = http_client

        resp = c.get("/api/v1/emulator-items/attribution")

        assert resp.status_code == 200, resp.text

    def test_confirm_token_reachable_with_no_active_user(self, http_client):
        c, db, app = http_client

        resp = c.get(f"/api/v1/emulator-items/{REAL_SLUG}/confirm-token")

        assert resp.status_code == 200, resp.text
        assert "token" in resp.json()
