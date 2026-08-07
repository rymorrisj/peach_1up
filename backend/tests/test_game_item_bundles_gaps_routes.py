"""Route-level (TestClient/HTTP) tests closing the remaining gap in
backend/api/routes/game_item_bundles.py identified by dev_docs/P1_AUDIT.md
TST-5: of its 19 routes, test_dependencies_content_rating.py covers list and
detail (both rating-ceiling and manual MediaRestriction filtering, HTTP
level), test_game_item_bundles_routes.py covers import-from-path,
scan/import, flag-launch, and items/reorder, and test_upload.py covers
confirm-delete and delete. That leaves scan status/cancel, the full scan
trigger, by-slug, bundle-level verify, convert-xiso plus its status, and the
per-leaf patch route (nested under the bundle path) untested. Covers those,
plus two extra routes (create, update) found uncovered during this pass that
TST-5 did not call out by name.

Fixed: GET /game-items/scan/status and POST /game-items/scan/{job_id}/cancel
now require can_manage_game (P1_AUDIT.md P3-S2), matching every sibling
route in the same scan family (scan, scan/import, import-from-path). The
tests below assert the gate rather than the previously-ungated behavior.

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


def _make_game_bundle(db, **overrides):
    from backend.models.game import GameItemBundle

    kwargs = dict(title="Doom", file_path="/library/games/dos/doom", era="dos", slug="doom")
    kwargs.update(overrides)
    bundle = GameItemBundle(**kwargs)
    db.add(bundle)
    db.commit()
    db.refresh(bundle)
    return bundle


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


# ---------------------------------------------------------------------------
# GET /game-item-bundle/by-slug/{slug}
# ---------------------------------------------------------------------------


class TestGetBySlug:
    def test_404_for_unknown_slug(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db))

        resp = c.get("/api/v1/game-item-bundle/by-slug/does-not-exist")

        assert resp.status_code == 404, resp.text

    def test_visible_bundle_returned_by_slug(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db)
        _set_active_user(app, _make_user(db))

        resp = c.get(f"/api/v1/game-item-bundle/by-slug/{bundle.slug}")

        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == bundle.id

    def test_over_rated_bundle_404s_by_slug_same_as_by_id(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db, content_rating="M")
        _set_active_user(app, _make_user(db, max_content_rating="E"))

        resp = c.get(f"/api/v1/game-item-bundle/by-slug/{bundle.slug}")

        assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# Scan status / cancel, now gated the same as their scan-family siblings
# ---------------------------------------------------------------------------


class TestScanStatusAndCancel:
    def test_scan_status_403_for_non_editor(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, can_manage_game=False))

        resp = c.get("/api/v1/game-items/scan/status")

        assert resp.status_code == 403, resp.text

    def test_scan_status_200_for_editor(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, can_manage_game=True))

        resp = c.get("/api/v1/game-items/scan/status")

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"running": False, "job_id": None, "error": None}

    def test_cancel_scan_403_for_non_editor(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, can_manage_game=False))

        resp = c.post("/api/v1/game-items/scan/not-a-real-job/cancel")

        assert resp.status_code == 403, resp.text

    def test_cancel_scan_404_for_unknown_job_as_editor(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, can_manage_game=True))

        resp = c.post("/api/v1/game-items/scan/not-a-real-job/cancel")

        assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# POST /game-items/scan (full scan trigger)
# ---------------------------------------------------------------------------


class TestTriggerScan:
    def test_403_for_non_editor(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, can_manage_game=False))

        resp = c.post("/api/v1/game-items/scan")

        assert resp.status_code == 403, resp.text

    def test_400_when_no_software_path_configured(self, http_client):
        """settings.init() never runs in this route-level suite, so
        _resolve_scan_directory's get_settings().get("SOFTWARE_PATH") raises
        RuntimeError, caught and treated as unconfigured, the route's own
        documented 400, not a test artifact."""
        c, db, app = http_client
        _set_active_user(app, _make_user(db, can_manage_game=True))

        resp = c.post("/api/v1/game-items/scan")

        assert resp.status_code == 400, resp.text
        assert "software library path" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Create / update, found uncovered during this pass, not itself in TST-5
# ---------------------------------------------------------------------------


class TestCreateAndUpdateGate:
    def test_create_403_for_non_editor(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, can_manage_game=False))

        resp = c.post(
            "/api/v1/game-items",
            json={"file_path": "/library/games/dos/nonexistent", "title": "New Game"},
        )

        assert resp.status_code == 403, resp.text

    def test_update_403_for_non_editor(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db)
        _set_active_user(app, _make_user(db, can_manage_game=False))

        resp = c.patch(f"/api/v1/game-item-bundle/{bundle.id}", json={"title": "Renamed"})

        assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# POST /game-item-bundle/{id}/verify (bundle-level, distinct from the
# per-leaf /game-item/{leaf_id}/verify covered in test_game_items_leaf_routes.py)
# ---------------------------------------------------------------------------


class TestBundleVerify:
    def test_403_for_non_editor(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db)
        _set_active_user(app, _make_user(db, can_manage_game=False))

        resp = c.post(f"/api/v1/game-item-bundle/{bundle.id}/verify")

        assert resp.status_code == 403, resp.text

    def test_404_for_nonexistent_bundle(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, can_manage_game=True))

        resp = c.post("/api/v1/game-item-bundle/999999/verify")

        assert resp.status_code == 404, resp.text

    def test_succeeds_for_a_bundle_with_no_discs(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db)
        _set_active_user(app, _make_user(db, can_manage_game=True))

        resp = c.post(f"/api/v1/game-item-bundle/{bundle.id}/verify")

        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# convert-xiso + its status
# ---------------------------------------------------------------------------


class TestConvertXiso:
    def test_403_for_non_launcher(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db, era="xbox")
        _set_active_user(app, _make_user(db, can_launch_media=False))

        resp = c.post(f"/api/v1/game-item-bundle/{bundle.id}/convert-xiso")

        assert resp.status_code == 403, resp.text

    def test_400_for_non_xbox_era(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db, era="dos")
        _set_active_user(app, _make_user(db, can_launch_media=True))

        resp = c.post(f"/api/v1/game-item-bundle/{bundle.id}/convert-xiso")

        assert resp.status_code == 400, resp.text

    def test_over_rated_bundle_404s_before_era_check(self, http_client):
        """convert-xiso resolves the collection through
        get_filtered_game_item_bundle, not a raw db.get, a capped user gets
        the same no-leak 404 as browsing, not a 400 era mismatch."""
        c, db, app = http_client
        bundle = _make_game_bundle(db, era="dos", content_rating="M")
        _set_active_user(app, _make_user(db, can_launch_media=True, max_content_rating="E"))

        resp = c.post(f"/api/v1/game-item-bundle/{bundle.id}/convert-xiso")

        assert resp.status_code == 404, resp.text

    def test_status_403_for_non_launcher(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db)
        _set_active_user(app, _make_user(db, can_launch_media=False))

        resp = c.get(f"/api/v1/game-item-bundle/{bundle.id}/convert-xiso/status")

        assert resp.status_code == 403, resp.text

    def test_status_200_idle_when_never_started(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db)
        _set_active_user(app, _make_user(db, can_launch_media=True))

        resp = c.get(f"/api/v1/game-item-bundle/{bundle.id}/convert-xiso/status")

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "idle"


# ---------------------------------------------------------------------------
# PATCH /game-item-bundle/{collection_id}/items/{leaf_id} (per-leaf patch)
# ---------------------------------------------------------------------------


class TestPerLeafPatch:
    def test_403_for_non_editor(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db)
        _set_active_user(app, _make_user(db, can_manage_game=False))

        resp = c.patch(f"/api/v1/game-item-bundle/{bundle.id}/items/1", json={})

        assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# trigger_scan job-creation timing (refactor Step 5, closes 2E): the route
# must hand back job_id without first running _check_known_items_findable,
# the pre-flight DB-row walk that used to run synchronously in the route and
# block the response. It now runs inside _run_scan (the background task)
# instead. Exercised as a direct function call rather than over TestClient,
# TestClient/httpx's ASGI transport runs BackgroundTasks to completion as
# part of the same request/response cycle, which would hide the very
# ordering this test needs to observe.
# ---------------------------------------------------------------------------


class TestTriggerScanJobTiming:
    @pytest.fixture(autouse=True)
    def _reset_jobs(self):
        from backend.core import jobs

        jobs._jobs.clear()
        jobs._cancel_events.clear()
        yield
        jobs._jobs.clear()
        jobs._cancel_events.clear()

    def test_route_returns_job_id_without_running_the_known_items_check(self, tmp_path, monkeypatch):
        from fastapi import BackgroundTasks
        from backend.api.routes import game_item_bundles
        from backend.core import jobs
        from backend.models.user import UserItem

        software_path = tmp_path / "software"
        (software_path / "games").mkdir(parents=True)

        class _FakeSettings:
            def get_env_var(self, key):
                return str(software_path) if key == "SOFTWARE_PATH" else ""

            def get(self, key, default=None):
                return str(software_path) if key == "SOFTWARE_PATH" else default

        import backend.core.settings as settings_mod
        monkeypatch.setattr(settings_mod, "get_settings", lambda: _FakeSettings())
        monkeypatch.setattr(game_item_bundles, "_enforce_rate_limit", lambda *a, **kw: None)

        calls: list = []
        monkeypatch.setattr(game_item_bundles, "_check_known_items_findable", lambda db: calls.append(db))

        background_tasks = BackgroundTasks()
        result = game_item_bundles.trigger_scan(
            request=None,
            background_tasks=background_tasks,
            _=UserItem(id=1, name="Tester", is_owner=False, can_manage_game=True),
        )

        assert result["started"] is True
        assert result["job_id"]
        # The slow check never ran as part of producing this response...
        assert calls == []
        # ...it's scheduled inside _run_scan instead, to run only once the
        # background task itself actually executes.
        assert any(t.func is game_item_bundles._run_scan for t in background_tasks.tasks)

        job = jobs.get(result["job_id"])
        assert job is not None
        assert job["status"] == "processing"
        assert job["kind"] == "scan"
