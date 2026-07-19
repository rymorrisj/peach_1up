"""Route-level tests for Environment CRUD (backend/api/routes/environments.py),
the live presence check computed by compute_environment_presence
(backend/service/environments/environments.py), and the consolidated health
aggregate endpoints now living in backend/api/routes/health.py.

Renamed from test_platforms_routes.py: the module it tested was itself
renamed platforms.py -> environments.py (and its aggregate-health endpoints
later moved into health.py), so this file follows suit rather than keeping a
name that no longer matches the route module it exercises.
"""

import pytest


def _owner_user():
    from backend.models.user import UserItem
    return UserItem(id=1, name="Owner", is_owner=True)


def _no_permission_user():
    from backend.models.user import UserItem
    return UserItem(id=2, name="Guest", is_owner=False, can_manage_environment=False)


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
    from backend.api.routes import environments, health
    from backend.core.database import get_db
    from backend.core.dependencies import get_active_user

    app = FastAPI()
    app.include_router(environments.router)
    app.include_router(health.router)
    app.dependency_overrides[get_active_user] = _owner_user
    app.dependency_overrides[get_db] = lambda: mem_db_session

    with TestClient(app) as c:
        yield c, mem_db_session


def _make_environment(db, **overrides):
    from backend.models.environment import EnvironmentItem

    kwargs = dict(
        name="Win98 Box",
        era="win98",
        emulator_slug="86box",
        slug="win98-box",
        working_image_path=None,
        base_image_path=None,
    )
    kwargs.update(overrides)
    environment = EnvironmentItem(**kwargs)
    db.add(environment)
    db.commit()
    db.refresh(environment)
    return environment


# ---------------------------------------------------------------------------
# CRUD through the real current routes
# ---------------------------------------------------------------------------


class TestListAndGetEnvironment:
    def test_list_returns_live_presence_not_a_stale_flag(self, client):
        c, db = client
        # No working/base image paths present, so is_present must be computed
        # False live, there is no persisted column to fall back on anymore.
        _make_environment(db)

        resp = c.get("/api/v1/environment-items")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["is_present"] is False

    def test_get_by_id_returns_live_presence(self, client, tmp_path):
        c, db = client
        base_image = tmp_path / "base.img"
        base_image.write_bytes(b"x" * 512)
        environment = _make_environment(
            db,
            base_image_path=str(base_image),
            working_image_path=str(tmp_path / "missing-working.img"),
        )

        resp = c.get(f"/api/v1/environment-items/{environment.id}")

        assert resp.status_code == 200
        assert resp.json()["is_present"] is False

    def test_get_unknown_id_is_404(self, client):
        c, _ = client
        resp = c.get("/api/v1/environment-items/999")
        assert resp.status_code == 404


class TestCreateEnvironment:
    def test_rejects_non_pc_era(self, client):
        c, _ = client
        resp = c.post(
            "/api/v1/environment-items",
            json={"name": "PS1 Box", "era": "ps1", "emulator_slug": "duckstation"},
        )
        assert resp.status_code == 422
        assert "PC eras" in resp.json()["detail"]

    def test_rejects_nonexistent_base_image_path(self, client, tmp_path):
        c, _ = client
        resp = c.post(
            "/api/v1/environment-items",
            json={
                "name": "Win98 Box",
                "era": "win98",
                "emulator_slug": "86box",
                "base_image_path": str(tmp_path / "missing.img"),
            },
        )
        assert resp.status_code == 400
        assert "does not exist" in resp.json()["detail"]

    def test_successful_create_auto_slugs(self, client, tmp_path):
        c, db = client
        base_image = tmp_path / "base.img"
        working_image = tmp_path / "working.img"
        base_image.write_bytes(b"b" * 1024)
        working_image.write_bytes(b"w" * 1024)

        # Both image paths are provided so create_platform's auto-provisioning
        # branch (triggered only when working_image_path is absent) never
        # fires — keeps this test hermetic instead of touching vm/86box code.
        resp = c.post(
            "/api/v1/environment-items",
            json={
                "name": "Fresh Win98 Box",
                "era": "win98",
                "emulator_slug": "86box",
                "base_image_path": str(base_image),
                "working_image_path": str(working_image),
            },
        )

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["slug"]

        from backend.models.environment import EnvironmentItem
        assert db.get(EnvironmentItem, body["id"]) is not None

    def test_requires_can_manage_environment_permission(self, client):
        c, _ = client
        from backend.core.dependencies import get_active_user
        c.app.dependency_overrides[get_active_user] = _no_permission_user

        resp = c.post(
            "/api/v1/environment-items",
            json={"name": "Win98 Box", "era": "win98", "emulator_slug": "86box"},
        )
        assert resp.status_code == 403


class TestUpdateEnvironment:
    def test_unknown_id_is_404(self, client):
        c, _ = client
        resp = c.patch("/api/v1/environment-items/999", json={"name": "New Name"})
        assert resp.status_code == 404

    def test_rejects_switching_to_non_pc_era(self, client):
        c, db = client
        environment = _make_environment(db)
        resp = c.patch(f"/api/v1/environment-items/{environment.id}", json={"era": "ps1"})
        assert resp.status_code == 422

    def test_rejects_nonexistent_working_image_path(self, client, tmp_path):
        c, db = client
        environment = _make_environment(db)
        resp = c.patch(
            f"/api/v1/environment-items/{environment.id}",
            json={"working_image_path": str(tmp_path / "missing.img")},
        )
        assert resp.status_code == 400

    def test_successful_update_persists_change(self, client):
        c, db = client
        environment = _make_environment(db)
        resp = c.patch(f"/api/v1/environment-items/{environment.id}", json={"name": "Renamed Box"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed Box"


class TestDeleteEnvironment:
    def test_delete_without_token_is_422(self, client):
        c, db = client
        environment = _make_environment(db)
        resp = c.delete(f"/api/v1/environment-items/{environment.id}")
        assert resp.status_code == 422  # confirmation_token is a required query param

    def test_delete_with_invalid_token_is_400(self, client):
        c, db = client
        environment = _make_environment(db)
        resp = c.delete(
            f"/api/v1/environment-items/{environment.id}",
            params={"confirmation_token": "not-a-real-token"},
        )
        assert resp.status_code == 400

    def test_confirm_delete_then_delete_removes_row(self, client):
        c, db = client
        environment = _make_environment(db)
        env_id = environment.id

        token_resp = c.post(f"/api/v1/environment-items/{env_id}/confirm-delete")
        assert token_resp.status_code == 200, token_resp.text
        token = token_resp.json()["confirmation_token"]

        del_resp = c.delete(f"/api/v1/environment-items/{env_id}", params={"confirmation_token": token})
        assert del_resp.status_code == 204

        from backend.models.environment import EnvironmentItem
        assert db.get(EnvironmentItem, env_id) is None

    def test_requires_can_manage_environment_permission(self, client):
        c, db = client
        environment = _make_environment(db)
        from backend.core.dependencies import get_active_user
        c.app.dependency_overrides[get_active_user] = _no_permission_user

        resp = c.post(f"/api/v1/environment-items/{environment.id}/confirm-delete")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# compute_environment_presence — a live boolean check, nothing persisted.
# ---------------------------------------------------------------------------


class TestComputeEnvironmentPresence:
    def _env(self, **overrides):
        from backend.models.environment import EnvironmentItem
        kwargs = dict(name="Box", era="win98", emulator_slug="86box")
        kwargs.update(overrides)
        return EnvironmentItem(**kwargs)

    def test_not_present_when_no_image_paths(self):
        from backend.service.environments.environments import compute_environment_presence
        environment = self._env(working_image_path=None, base_image_path=None)
        assert compute_environment_presence(environment) is False

    def test_present_when_working_and_base_present_and_valid(self, tmp_path):
        from backend.service.environments.environments import compute_environment_presence
        working = tmp_path / "working.img"
        base = tmp_path / "base.img"
        working.write_bytes(b"w" * 1024)
        base.write_bytes(b"b" * 1024)
        environment = self._env(working_image_path=str(working), base_image_path=str(base))
        assert compute_environment_presence(environment) is True

    def test_not_present_when_working_missing_but_base_present(self, tmp_path):
        from backend.service.environments.environments import compute_environment_presence
        base = tmp_path / "base.img"
        base.write_bytes(b"b" * 1024)
        environment = self._env(
            working_image_path=str(tmp_path / "missing-working.img"),
            base_image_path=str(base),
        )
        assert compute_environment_presence(environment) is False

    def test_not_present_when_working_present_but_base_missing(self, tmp_path):
        from backend.service.environments.environments import compute_environment_presence
        working = tmp_path / "working.img"
        working.write_bytes(b"w" * 1024)
        environment = self._env(working_image_path=str(working), base_image_path=None)
        assert compute_environment_presence(environment) is False

    def test_not_present_when_working_image_fails_integrity_probe(self, tmp_path):
        from backend.service.environments.environments import compute_environment_presence
        working = tmp_path / "working.img"
        base = tmp_path / "base.img"
        working.write_bytes(b"")  # zero-byte -> fails _probe_image_integrity
        base.write_bytes(b"b" * 1024)
        environment = self._env(working_image_path=str(working), base_image_path=str(base))
        assert compute_environment_presence(environment) is False

    def test_dos_era_not_present_without_base_image(self):
        # DOS launches mount the per-item drive instead of working_image_path,
        # so only base_image_path is evaluated for this era.
        from backend.service.environments.environments import compute_environment_presence
        environment = self._env(era="dos", emulator_slug="dosbox-x", working_image_path=None, base_image_path=None)
        assert compute_environment_presence(environment) is False

    def test_dos_era_present_when_base_image_present(self, tmp_path):
        from backend.service.environments.environments import compute_environment_presence
        base = tmp_path / "base.img"
        base.write_bytes(b"b" * 512)
        environment = self._env(era="dos", emulator_slug="dosbox-x", base_image_path=str(base))
        assert compute_environment_presence(environment) is True

    def test_dos_era_not_present_when_base_image_missing_on_disk(self, tmp_path):
        from backend.service.environments.environments import compute_environment_presence
        environment = self._env(
            era="dos",
            emulator_slug="dosbox-x",
            base_image_path=str(tmp_path / "missing-base.img"),
        )
        assert compute_environment_presence(environment) is False

    def test_system_environment_present_when_binary_installed(self, monkeypatch):
        from pathlib import Path
        from backend.service.environments import environments as env_svc
        from backend.service.utils import emulator_catalog

        monkeypatch.setattr(emulator_catalog, "get_install_path", lambda slug: Path("/fake/duckstation"))
        environment = self._env(era="ps1", emulator_slug="duckstation", is_system=True)
        assert env_svc.compute_environment_presence(environment) is True

    def test_system_environment_not_present_when_binary_not_installed(self, monkeypatch):
        from backend.service.environments import environments as env_svc
        from backend.service.utils import emulator_catalog

        monkeypatch.setattr(emulator_catalog, "get_install_path", lambda slug: None)
        environment = self._env(era="ps1", emulator_slug="duckstation", is_system=True)
        assert env_svc.compute_environment_presence(environment) is False


# ---------------------------------------------------------------------------
# Consolidated health aggregate endpoints (backend/api/routes/health.py)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _empty_catalog(monkeypatch):
    """The environments/health bucket is what these tests care about; the
    emulator/BIOS/ROM-pack catalog is bundled config unrelated to it, so it's
    stubbed to empty rather than depending on the real catalog files."""
    from backend.service.utils import emulator_catalog
    monkeypatch.setattr(emulator_catalog, "load_catalog", lambda: [])
    monkeypatch.setattr(emulator_catalog, "load_bios_requirements", lambda: [])


class TestHealthSummaryEndpoint:
    def test_not_present_environment_excluded_from_present_count(self, client):
        c, db = client
        _make_environment(db)  # no image paths -> not present

        resp = c.get("/api/v1/health/summary")

        assert resp.status_code == 200
        body = resp.json()
        assert body["environments"] == {"total": 1, "present": 0}

    def test_response_includes_all_summary_sections(self, client):
        c, _ = client
        resp = c.get("/api/v1/health/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {
            "environments", "library", "drives", "extensions", "emulators", "bios", "rom_packs",
        }

    def test_requires_can_manage_environment_permission(self, client):
        c, _ = client
        from backend.core.dependencies import get_active_user
        c.app.dependency_overrides[get_active_user] = _no_permission_user
        resp = c.get("/api/v1/health/summary")
        assert resp.status_code == 403


class TestHealthRecomputeAllEndpoint:
    def test_recomputes_presence_for_all_environments_without_persisting(self, client, tmp_path):
        c, db = client
        base = tmp_path / "base.img"
        working = tmp_path / "working.img"
        base.write_bytes(b"b" * 1024)
        working.write_bytes(b"w" * 1024)
        present_env = _make_environment(
            db, slug="a", base_image_path=str(base), working_image_path=str(working),
        )
        absent_env = _make_environment(db, slug="b")

        resp = c.post("/api/v1/health/recompute-all")

        assert resp.status_code == 200
        body = resp.json()
        assert body["checked"] == 2
        results_by_id = {r["id"]: r["is_present"] for r in body["results"]}
        assert results_by_id == {present_env.id: True, absent_env.id: False}


class TestStorageStatsEndpoint:
    def test_sums_os_image_bytes_from_environments(self, client, tmp_path):
        c, db = client
        working = tmp_path / "working.img"
        working.write_bytes(b"w" * 2048)
        _make_environment(db, working_image_path=str(working), base_image_path=None)

        resp = c.get("/api/v1/health/storage-stats")

        assert resp.status_code == 200
        body = resp.json()
        assert body["os_images_bytes"] == 2048
        assert body["drive_images_bytes"] == 0
        assert body["emulator_binaries_bytes"] == 0
