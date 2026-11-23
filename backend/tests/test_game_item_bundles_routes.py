"""Route-level (TestClient/HTTP) tests for backend/api/routes/game_item_bundles.py.

Covers the permission gates on:

    - POST /software/import-from-path (can_manage_game)
    - POST /software/scan/import (can_manage_game)
    - PATCH .../items/reorder (can_manage_game)
    - POST .../flag-launch (can_launch_media)
    - PATCH /game-item-bundle/{id} content_rating confirmation and visibility

Rating-filter coverage for get_filtered_game_item_bundles /
get_filtered_game_item_bundle lives in test_dependencies_content_rating.py,
confirm-delete and DELETE in test_upload.py; neither is repeated here.

In-memory SQLModel SQLite + StaticPool + get_active_user/get_db dependency
overrides, as in test_dependencies_content_rating.py.
"""

import pytest
from sqlmodel import select


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


def _make_collection(db, **overrides):
    from backend.models.game import GameItemBundle

    kwargs = dict(title="Doom", file_path="/library/games/dos/doom", platform="dos", slug="doom")
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
# POST /software/import-from-path, can_manage_game gate
# ---------------------------------------------------------------------------


class TestImportFromPath:
    @pytest.fixture(autouse=True)
    def _reset_jobs(self):
        """core.jobs is a module-level, in-memory store shared across the
        whole test process. import-from-path always finalizes as a
        background job now (no inline path), so this class actually
        populates it, clear it before/after so tests don't leak jobs into
        each other or into other test files sharing the process."""
        from backend.core import jobs

        jobs._jobs.clear()
        jobs._cancel_events.clear()
        yield
        jobs._jobs.clear()
        jobs._cancel_events.clear()

    @pytest.fixture
    def client(self, tmp_path, mem_db_session, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.api.routes import game_item_bundles, jobs as jobs_routes
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
        # test methods within the same process, bypass it at the source.
        monkeypatch.setattr(game_item_bundles, "_enforce_rate_limit", lambda *a, **kw: None)

        # import_background runs as a BackgroundTask with its own DB session,
        # opened via backend.core.database.get_engine() directly (background
        # tasks can't take FastAPI Depends), not through the get_db override
        # below. Without this, that session binds to the real app engine
        # instead of this test's isolated in-memory one, same hazard fixed in
        # test_upload.py's client fixture.
        import backend.core.database as database_mod

        monkeypatch.setattr(database_mod, "get_engine", mem_db_session.get_bind)

        app = FastAPI()
        app.include_router(game_item_bundles.router)
        app.include_router(jobs_routes.router)
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
        """import-from-path always finalizes as a background job now (see
        service.games.path_import.import_background); TestClient/httpx2's
        ASGI transport runs BackgroundTasks to completion as part of the same
        request/response cycle, so the job is already 'done' by the time
        this polls it, same pattern as test_upload.py's _upload helper."""
        c, db, app, source_dir = client
        source_file = source_dir / "game.iso"
        source_file.write_bytes(b"not a real iso but enough bytes")
        permitted = _make_user(db, can_manage_game=True, is_admin=False)
        _set_active_user(app, permitted)

        resp = c.post(
            "/api/v1/game-items/import-from-path",
            json={"source_path": str(source_file), "title": "Game"},
        )
        assert resp.status_code == 202, resp.text
        job_id = resp.json()["job_id"]

        job_resp = c.get(f"/api/v1/jobs/{job_id}")
        assert job_resp.status_code == 200, job_resp.text
        job = job_resp.json()
        assert job["status"] == "done", job
        assert job["result"]["title"] == "Game"


# ---------------------------------------------------------------------------
# POST /software/scan/import, can_manage_game gate
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

        created = db.exec(select(GameItemBundle).where(GameItemBundle.title == "Game")).first()
        assert created is not None


# ---------------------------------------------------------------------------
# PATCH .../items/reorder, can_manage_game gate
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
# POST .../flag-launch, can_launch_media gate
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


# ---------------------------------------------------------------------------
# PATCH /game-item-bundle/{id}, content_rating confirmation and visibility
# ---------------------------------------------------------------------------


class TestBundlePatchRatingGuard:
    def _capped_editor(self, db):
        return _make_user(db, can_manage_game=True, max_content_rating="T")

    def _reloaded_rating(self, db, collection_id):
        from backend.models.game import GameItemBundle

        db.expire_all()
        return db.get(GameItemBundle, collection_id).content_rating

    @pytest.mark.parametrize("new_rating", ["E", None, "PEGI 12"])
    def test_lower_clear_or_scheme_change_without_confirm_is_409(self, http_client, new_rating):
        c, db, app = http_client
        collection = _make_collection(db, content_rating="T")
        _set_active_user(app, self._capped_editor(db))

        resp = c.patch(f"/api/v1/game-item-bundle/{collection.id}", json={"content_rating": new_rating})

        assert resp.status_code == 409, resp.text
        assert "confirm_rating_change" in resp.json()["detail"]
        assert self._reloaded_rating(db, collection.id) == "T"

    def test_lower_with_confirm_is_applied(self, http_client):
        c, db, app = http_client
        collection = _make_collection(db, content_rating="T")
        _set_active_user(app, self._capped_editor(db))

        resp = c.patch(
            f"/api/v1/game-item-bundle/{collection.id}",
            params={"confirm_rating_change": "true"},
            json={"content_rating": None},
        )

        assert resp.status_code == 200, resp.text
        assert self._reloaded_rating(db, collection.id) is None

    def test_raise_needs_no_confirm(self, http_client):
        c, db, app = http_client
        collection = _make_collection(db, content_rating="E")
        _set_active_user(app, self._capped_editor(db))

        resp = c.patch(f"/api/v1/game-item-bundle/{collection.id}", json={"content_rating": "T"})

        assert resp.status_code == 200, resp.text
        assert self._reloaded_rating(db, collection.id) == "T"

    def test_unchanged_rating_alongside_other_edit_needs_no_confirm(self, http_client):
        c, db, app = http_client
        collection = _make_collection(db, content_rating="T")
        _set_active_user(app, self._capped_editor(db))

        resp = c.patch(
            f"/api/v1/game-item-bundle/{collection.id}",
            json={"title": "Renamed", "content_rating": "T"},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["title"] == "Renamed"

    def test_free_form_rating_is_normalized(self, http_client):
        c, db, app = http_client
        collection = _make_collection(db, content_rating=None)
        _set_active_user(app, _make_user(db, is_owner=True))

        resp = c.patch(
            f"/api/v1/game-item-bundle/{collection.id}",
            json={"content_rating": "M - Mature 17+"},
        )

        assert resp.status_code == 200, resp.text
        assert self._reloaded_rating(db, collection.id) == "M"

    def test_owner_also_needs_confirm_to_clear(self, http_client):
        c, db, app = http_client
        collection = _make_collection(db, content_rating="M")
        _set_active_user(app, _make_user(db, is_owner=True))

        resp = c.patch(f"/api/v1/game-item-bundle/{collection.id}", json={"content_rating": None})

        assert resp.status_code == 409, resp.text
        assert self._reloaded_rating(db, collection.id) == "M"

    def test_over_cap_item_is_not_patchable_and_matches_missing_item(self, http_client):
        c, db, app = http_client
        hidden = _make_collection(db, content_rating="M")
        _set_active_user(app, self._capped_editor(db))

        hidden_resp = c.patch(
            f"/api/v1/game-item-bundle/{hidden.id}",
            params={"confirm_rating_change": "true"},
            json={"content_rating": None},
        )
        missing_resp = c.patch("/api/v1/game-item-bundle/999999", json={"title": "x"})

        assert hidden_resp.status_code == 404, hidden_resp.text
        assert hidden_resp.json() == missing_resp.json()
        assert self._reloaded_rating(db, hidden.id) == "M"

    def test_restricted_item_is_not_patchable(self, http_client):
        from backend.models.game import GameItemBundle
        from backend.models.media_restriction import MediaRestriction

        c, db, app = http_client
        collection = _make_collection(db, content_rating="E")
        user = _make_user(db, can_manage_game=True)
        db.add(MediaRestriction(user_item_id=user.id, game_item_bundle_id=collection.id))
        db.commit()
        _set_active_user(app, user)

        resp = c.patch(f"/api/v1/game-item-bundle/{collection.id}", json={"title": "Renamed"})

        assert resp.status_code == 404, resp.text
        db.expire_all()
        assert db.get(GameItemBundle, collection.id).title == "Doom"


# ---------------------------------------------------------------------------
# PATCH /game-item-bundle/{id}, platform correction re-suggests the profile, keeps
# a PC Environment, clears it for a console platform, and marks the platform
# as user-selected
# ---------------------------------------------------------------------------


class TestBundlePatchPlatform:
    def _editor(self, db):
        return _make_user(db, can_manage_game=True)

    def _profile(self, db, platform, emulator_slug, slug=None, bundled=True):
        from backend.models.profile import ProfileItem

        profile = ProfileItem(
            name=slug or f"{platform} profile",
            slug=slug or f"{platform}-profile",
            emulator_slug=emulator_slug,
            platform=platform,
            is_bundled=bundled,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile

    def _environment(self, db, platform, emulator_slug):
        from backend.models.environment import EnvironmentItem

        environment = EnvironmentItem(
            name=f"{platform} env",
            slug=f"{platform}-env",
            platform=platform,
            emulator_slug=emulator_slug,
        )
        db.add(environment)
        db.commit()
        db.refresh(environment)
        return environment

    def _reloaded(self, db, collection_id):
        from backend.models.game import GameItemBundle

        db.expire_all()
        return db.get(GameItemBundle, collection_id)

    def _two_disc_ps1_bundle(self, db, ps1_profile):
        collection = _make_collection(db, platform="ps1", slug="ico", title="Ico", profile_item_id=ps1_profile.id)
        _make_item(
            db, collection.id, disc_number=1, file_path="/library/games/ps1/ico/d1.chd", detection_reason="CHD header"
        )
        _make_item(
            db, collection.id, disc_number=2, file_path="/library/games/ps1/ico/d2.chd", detection_reason="CHD header"
        )
        return collection

    def test_platform_change_refills_profile_and_marks_every_leaf(self, http_client):
        from backend.constants import PLATFORM_SELECTED_BY_USER_REASON

        c, db, app = http_client
        ps1 = self._profile(db, "ps1", "duckstation")
        ps2 = self._profile(db, "ps2", "pcsx2")
        collection = self._two_disc_ps1_bundle(db, ps1)
        _set_active_user(app, self._editor(db))

        # The form echoes the stored profile id on every save.
        resp = c.patch(
            f"/api/v1/game-item-bundle/{collection.id}",
            json={"platform": "ps2", "profile_item_id": ps1.id, "environment_item_id": None},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["platform"] == "ps2"
        assert body["profile_item_id"] == ps2.id
        assert body["environment_item_id"] is None
        assert [i["detection_reason"] for i in body["items"]] == [PLATFORM_SELECTED_BY_USER_REASON] * 2
        assert body["platform_review"] == "confirmed"
        assert body["platform_confirmed"] is True
        assert self._reloaded(db, collection.id).profile_item_id == ps2.id

    def test_pc_platform_change_keeps_the_chosen_environment(self, http_client):
        c, db, app = http_client
        self._profile(db, "dos", "dosbox-x")
        win98 = self._profile(db, "win98", "86box")
        environment = self._environment(db, "win95", "86box")
        collection = _make_collection(
            db,
            platform="dos",
            slug="doom2",
            environment_item_id=environment.id,
        )
        _make_item(db, collection.id)
        _set_active_user(app, self._editor(db))

        resp = c.patch(
            f"/api/v1/game-item-bundle/{collection.id}",
            json={"platform": "win98", "environment_item_id": environment.id},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["profile_item_id"] == win98.id
        assert resp.json()["environment_item_id"] == environment.id

    def test_pc_platform_change_never_suggests_an_environment(self, http_client):
        c, db, app = http_client
        ps1 = self._profile(db, "ps1", "duckstation")
        dos = self._profile(db, "dos", "dosbox-x")
        self._environment(db, "dos", "dosbox-x")
        collection = self._two_disc_ps1_bundle(db, ps1)
        _set_active_user(app, self._editor(db))

        resp = c.patch(f"/api/v1/game-item-bundle/{collection.id}", json={"platform": "dos"})

        assert resp.status_code == 200, resp.text
        assert resp.json()["profile_item_id"] == dos.id
        assert resp.json()["environment_item_id"] is None

    def test_console_platform_change_clears_the_environment(self, http_client):
        c, db, app = http_client
        dos = self._profile(db, "dos", "dosbox-x")
        ps1 = self._profile(db, "ps1", "duckstation")
        environment = self._environment(db, "dos", "dosbox-x")
        collection = _make_collection(
            db,
            platform="dos",
            slug="doom2",
            profile_item_id=dos.id,
            environment_item_id=environment.id,
        )
        _make_item(db, collection.id)
        _set_active_user(app, self._editor(db))

        resp = c.patch(
            f"/api/v1/game-item-bundle/{collection.id}",
            json={"platform": "ps1", "profile_item_id": dos.id, "environment_item_id": environment.id},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["profile_item_id"] == ps1.id
        assert resp.json()["environment_item_id"] is None

    def test_explicit_ids_in_the_same_request_win(self, http_client):
        c, db, app = http_client
        ps1 = self._profile(db, "ps1", "duckstation")
        self._profile(db, "ps2", "pcsx2")
        custom = self._profile(db, "ps2", "pcsx2", slug="my-ps2-profile", bundled=False)
        collection = self._two_disc_ps1_bundle(db, ps1)
        _set_active_user(app, self._editor(db))

        resp = c.patch(
            f"/api/v1/game-item-bundle/{collection.id}",
            json={"platform": "ps2", "profile_item_id": custom.id},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["profile_item_id"] == custom.id

    def test_changing_to_unknown_leaves_both_empty(self, http_client):
        c, db, app = http_client
        dos = self._profile(db, "dos", "dosbox-x")
        dos_env = self._environment(db, "dos", "dosbox-x")
        collection = _make_collection(
            db,
            platform="dos",
            slug="doom2",
            profile_item_id=dos.id,
            environment_item_id=dos_env.id,
        )
        _make_item(db, collection.id)
        _set_active_user(app, self._editor(db))

        resp = c.patch(
            f"/api/v1/game-item-bundle/{collection.id}",
            json={"platform": "unknown", "profile_item_id": dos.id, "environment_item_id": dos_env.id},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["profile_item_id"] is None
        assert body["environment_item_id"] is None
        # Unknown is always unreviewed, even though the user chose it.
        assert body["platform_review"] == "unreviewed"

    def test_resending_the_unchanged_platform_keeps_bindings_and_reason(self, http_client):
        c, db, app = http_client
        ps1 = self._profile(db, "ps1", "duckstation")
        collection = self._two_disc_ps1_bundle(db, ps1)
        _set_active_user(app, self._editor(db))

        resp = c.patch(
            f"/api/v1/game-item-bundle/{collection.id}",
            json={"platform": "ps1", "profile_item_id": ps1.id, "title": "Ico (renamed)"},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["profile_item_id"] == ps1.id
        assert [i["detection_reason"] for i in body["items"]] == ["CHD header"] * 2
        assert body["platform_review"] == "unreviewed"


# ---------------------------------------------------------------------------
# PATCH /game-item-bundle/{id}, platform_confirmed: set by a platform change, set by the
# explicit Confirm action, never un-set directly
# ---------------------------------------------------------------------------


class TestBundlePatchPlatformConfirmed:
    def _editor(self, db):
        return _make_user(db, can_manage_game=True)

    def _reloaded(self, db, collection_id):
        from backend.models.game import GameItemBundle

        db.expire_all()
        return db.get(GameItemBundle, collection_id)

    def _detected_bundle(self, db, platform="ps1", **overrides):
        collection = _make_collection(db, platform=platform, slug="ico", title="Ico", **overrides)
        _make_item(db, collection.id, file_path="/library/games/ps1/ico/d1.chd", detection_reason="CHD header")
        return collection

    def test_new_bundle_starts_unconfirmed(self, http_client):
        c, db, app = http_client
        collection = self._detected_bundle(db)
        _set_active_user(app, self._editor(db))

        body = c.get(f"/api/v1/game-item-bundle/{collection.id}").json()

        assert body["platform_confirmed"] is False
        assert body["platform_review"] == "unreviewed"

    def test_platform_change_sets_platform_confirmed(self, http_client):
        c, db, app = http_client
        collection = self._detected_bundle(db)
        _set_active_user(app, self._editor(db))

        resp = c.patch(f"/api/v1/game-item-bundle/{collection.id}", json={"platform": "ps2"})

        assert resp.status_code == 200, resp.text
        assert resp.json()["platform_confirmed"] is True
        assert resp.json()["platform_review"] == "confirmed"
        assert self._reloaded(db, collection.id).platform_confirmed is True

    def test_platform_change_to_unknown_leaves_platform_unconfirmed(self, http_client):
        c, db, app = http_client
        collection = self._detected_bundle(db, platform_confirmed=True)
        _set_active_user(app, self._editor(db))

        resp = c.patch(f"/api/v1/game-item-bundle/{collection.id}", json={"platform": "unknown"})

        assert resp.status_code == 200, resp.text
        assert resp.json()["platform_confirmed"] is False
        assert resp.json()["platform_review"] == "unreviewed"

    def test_resending_the_unchanged_platform_does_not_confirm(self, http_client):
        c, db, app = http_client
        collection = self._detected_bundle(db)
        _set_active_user(app, self._editor(db))

        resp = c.patch(
            f"/api/v1/game-item-bundle/{collection.id}",
            json={"platform": "ps1", "title": "Ico (renamed)"},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["platform_confirmed"] is False
        assert self._reloaded(db, collection.id).platform_confirmed is False

    def test_unrelated_save_keeps_a_confirmed_platform_confirmed(self, http_client):
        c, db, app = http_client
        collection = self._detected_bundle(db, platform_confirmed=True)
        _set_active_user(app, self._editor(db))

        resp = c.patch(f"/api/v1/game-item-bundle/{collection.id}", json={"title": "Ico (renamed)"})

        assert resp.status_code == 200, resp.text
        assert resp.json()["platform_confirmed"] is True

    def test_explicit_true_confirms_with_can_manage_game(self, http_client):
        c, db, app = http_client
        collection = self._detected_bundle(db)
        _set_active_user(app, self._editor(db))

        resp = c.patch(f"/api/v1/game-item-bundle/{collection.id}", json={"platform_confirmed": True})

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["platform"] == "ps1"
        assert body["platform_confirmed"] is True
        assert body["platform_review"] == "confirmed"
        # Confirm is not an platform edit, the detected reason stays as it was.
        assert [i["detection_reason"] for i in body["items"]] == ["CHD header"]
        assert self._reloaded(db, collection.id).platform_confirmed is True

    def test_explicit_true_is_rejected_without_can_manage_game(self, http_client):
        c, db, app = http_client
        collection = self._detected_bundle(db)
        _set_active_user(app, _make_user(db, can_manage_game=False, can_launch_media=True))

        resp = c.patch(f"/api/v1/game-item-bundle/{collection.id}", json={"platform_confirmed": True})

        assert resp.status_code == 403, resp.text
        assert self._reloaded(db, collection.id).platform_confirmed is False

    def test_explicit_true_is_allowed_for_the_owner(self, http_client):
        c, db, app = http_client
        collection = self._detected_bundle(db)
        _set_active_user(app, _make_user(db, is_owner=True))

        resp = c.patch(f"/api/v1/game-item-bundle/{collection.id}", json={"platform_confirmed": True})

        assert resp.status_code == 200, resp.text
        assert resp.json()["platform_confirmed"] is True

    def test_explicit_false_is_422_and_changes_nothing(self, http_client):
        c, db, app = http_client
        collection = self._detected_bundle(db, platform_confirmed=True)
        _set_active_user(app, self._editor(db))

        resp = c.patch(f"/api/v1/game-item-bundle/{collection.id}", json={"platform_confirmed": False})

        assert resp.status_code == 422, resp.text
        assert self._reloaded(db, collection.id).platform_confirmed is True

    def test_explicit_null_is_422(self, http_client):
        c, db, app = http_client
        collection = self._detected_bundle(db)
        _set_active_user(app, self._editor(db))

        resp = c.patch(f"/api/v1/game-item-bundle/{collection.id}", json={"platform_confirmed": None})

        assert resp.status_code == 422, resp.text

    def test_true_on_unknown_platform_is_422(self, http_client):
        c, db, app = http_client
        collection = _make_collection(db, platform="unknown", slug="mystery", title="Mystery")
        _make_item(db, collection.id)
        _set_active_user(app, self._editor(db))

        resp = c.patch(f"/api/v1/game-item-bundle/{collection.id}", json={"platform_confirmed": True})

        assert resp.status_code == 422, resp.text
        assert self._reloaded(db, collection.id).platform_confirmed is False

    def test_true_with_a_same_request_change_to_unknown_is_422(self, http_client):
        c, db, app = http_client
        collection = self._detected_bundle(db)
        _set_active_user(app, self._editor(db))

        resp = c.patch(
            f"/api/v1/game-item-bundle/{collection.id}",
            json={"platform": "unknown", "platform_confirmed": True},
        )

        assert resp.status_code == 422, resp.text
        assert self._reloaded(db, collection.id).platform == "ps1"

    def test_true_with_a_same_request_change_to_a_known_platform_is_accepted(self, http_client):
        c, db, app = http_client
        collection = _make_collection(db, platform="unknown", slug="mystery", title="Mystery")
        _make_item(db, collection.id)
        _set_active_user(app, self._editor(db))

        resp = c.patch(
            f"/api/v1/game-item-bundle/{collection.id}",
            json={"platform": "ps2", "platform_confirmed": True},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["platform_confirmed"] is True

    def test_create_does_not_accept_platform_confirmed(self):
        from backend.models.game import GameItemBundleCreate

        assert "platform_confirmed" not in GameItemBundleCreate.model_fields
