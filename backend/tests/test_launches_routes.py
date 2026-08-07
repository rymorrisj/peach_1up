"""Route-level (TestClient/HTTP) tests for backend/api/routes/launches.py.

Per dev_docs/v2/09_test_coverage.md item 4, test_launch_guards.py and
test_launch_error_detection.py drive backend/service/launch/coordinator.py
directly; no TestClient touches the routes themselves. This file confirms
the security gates are actually wired at the endpoint, not the coordinator
logic they call into (concurrent-launch guards, crash detection, etc. stay
in those two files and are not duplicated here). Covers:

    - can_launch_media gating on POST /game-item-bundle/{id}/launch
      (launches.py:33)
    - get_filtered_collection enforcement on launch (launches.py:36), a
      capped/restricted user must get the same no-leak 404 as browsing
    - the fail-closed target_type filter on GET /launches (launches.py:94-99),
      a prior fail-open bug, regression-locked here
    - can_launch_media gating on POST /environment-items/{id}/launch
      (launches.py:50) and the missing-environment 404 branch
    - can_launch_media gating on POST /launches/{id}/stop (launches.py:117)

Uses the same in-memory SQLModel SQLite DB + StaticPool +
get_active_user/get_db dependency-override pattern as
test_dependencies_content_rating.py / test_users_create_delete_reset.py /
test_game_item_bundles_routes.py.
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


def _make_collection(db, **overrides):
    from backend.models.game import GameItemBundle

    kwargs = dict(title="Doom", file_path="/library/games/dos/doom", era="dos", slug="doom")
    kwargs.update(overrides)
    collection = GameItemBundle(**kwargs)
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return collection


def _make_launch_history(db, **overrides):
    from backend.models.launch_history import LaunchHistory

    kwargs = dict(emulator_slug="dosbox-x")
    kwargs.update(overrides)
    record = LaunchHistory(**kwargs)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _make_environment(db, **overrides):
    from backend.models import EnvironmentItem

    kwargs = dict(name="DOS Box", era="dos", emulator_slug="dosbox-x")
    kwargs.update(overrides)
    env = EnvironmentItem(**kwargs)
    db.add(env)
    db.commit()
    db.refresh(env)
    return env


@pytest.fixture
def http_client(mem_db_session):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import launches
    from backend.core.database import get_db

    app = FastAPI()
    app.include_router(launches.router)
    app.dependency_overrides[get_db] = lambda: mem_db_session

    with TestClient(app) as c:
        yield c, mem_db_session, app


def _set_active_user(app, user):
    from backend.core.dependencies import get_active_user

    app.dependency_overrides[get_active_user] = lambda: user


def _stub_launch_collection(monkeypatch, *, history_id=1):
    """Stub out svc.launch_collection so gate tests exercise only the route's
    permission/filter wiring, not the coordinator (already covered by
    test_launch_guards.py / test_launch_error_detection.py)."""
    from backend.api.routes import launches as launches_mod
    from backend.service.launch.coordinator import LaunchResult

    calls = []

    async def _fake_launch_collection(collection_id, profile_item_id, db):
        calls.append((collection_id, profile_item_id))
        return LaunchResult(history_id=history_id)

    monkeypatch.setattr(launches_mod.svc, "launch_collection", _fake_launch_collection)
    return calls


def _stub_launch_environment(monkeypatch, *, history_id=1):
    """Stub out svc.launch_environment so gate tests exercise only the route's
    permission wiring, not the coordinator's provisioning/launch logic."""
    from backend.api.routes import launches as launches_mod
    from backend.service.launch.coordinator import LaunchResult

    calls = []

    async def _fake_launch_environment(platform, profile_item_id, db):
        calls.append((platform.id, profile_item_id))
        return LaunchResult(history_id=history_id)

    monkeypatch.setattr(launches_mod.svc, "launch_environment", _fake_launch_environment)
    return calls


def _stub_stop_launch(monkeypatch, *, stopped=True):
    """Stub out svc.stop_launch so gate tests exercise only the route's
    permission wiring, not process_registry/coordinator internals."""
    from backend.api.routes import launches as launches_mod

    calls = []

    def _fake_stop_launch(history_id, active_user, db):
        calls.append((history_id, active_user.id))
        return {"stopped": stopped}

    monkeypatch.setattr(launches_mod.svc, "stop_launch", _fake_stop_launch)
    return calls


# ---------------------------------------------------------------------------
# can_launch_media gating, POST /game-item-bundle/{id}/launch
# ---------------------------------------------------------------------------


class TestCanLaunchMediaGate:
    def test_can_launch_media_false_blocks_launch_at_route(self, http_client, monkeypatch):
        c, db, app = http_client
        collection = _make_collection(db)
        calls = _stub_launch_collection(monkeypatch)
        blocked_user = _make_user(db, can_launch_media=False)
        _set_active_user(app, blocked_user)

        resp = c.post(f"/api/v1/game-item-bundle/{collection.id}/launch")

        assert resp.status_code == 403, resp.text
        # The gate must reject before the coordinator is ever reached.
        assert calls == []

    def test_can_launch_media_true_allows_launch_past_gate(self, http_client, monkeypatch):
        c, db, app = http_client
        collection = _make_collection(db)
        calls = _stub_launch_collection(monkeypatch, history_id=77)
        permitted_user = _make_user(db, can_launch_media=True)
        _set_active_user(app, permitted_user)

        resp = c.post(f"/api/v1/game-item-bundle/{collection.id}/launch")

        assert resp.status_code == 202, resp.text
        assert resp.json()["launch_history_id"] == 77
        assert calls == [(collection.id, None)]


# ---------------------------------------------------------------------------
# get_filtered_collection enforcement on launch
# ---------------------------------------------------------------------------


class TestGetFilteredCollectionEnforcement:
    def test_over_rated_collection_blocked_with_404_not_leaked(self, http_client, monkeypatch):
        """A capped sub-account attempting to launch a collection above its
        max_content_rating must get the same no-leak 404 get_filtered_collection
        returns elsewhere (list/detail), not a 403, and not a bypass because
        can_launch_media is otherwise true."""
        c, db, app = http_client
        collection = _make_collection(db, content_rating="M")
        calls = _stub_launch_collection(monkeypatch)
        capped_user = _make_user(db, can_launch_media=True, max_content_rating="T")
        _set_active_user(app, capped_user)

        resp = c.post(f"/api/v1/game-item-bundle/{collection.id}/launch")

        assert resp.status_code == 404, resp.text
        # Filtered out before the coordinator is ever reached.
        assert calls == []

    def test_restricted_collection_blocked_with_404(self, http_client, monkeypatch):
        from backend.models.media_restriction import MediaRestriction

        c, db, app = http_client
        collection = _make_collection(db)
        calls = _stub_launch_collection(monkeypatch)
        restricted_user = _make_user(db, can_launch_media=True)
        db.add(MediaRestriction(user_item_id=restricted_user.id, game_item_bundle_id=collection.id))
        db.commit()
        _set_active_user(app, restricted_user)

        resp = c.post(f"/api/v1/game-item-bundle/{collection.id}/launch")

        assert resp.status_code == 404, resp.text
        assert calls == []

    def test_permitted_collection_within_rating_passes_filter(self, http_client, monkeypatch):
        c, db, app = http_client
        collection = _make_collection(db, content_rating="E")
        calls = _stub_launch_collection(monkeypatch)
        capped_user = _make_user(db, can_launch_media=True, max_content_rating="T")
        _set_active_user(app, capped_user)

        resp = c.post(f"/api/v1/game-item-bundle/{collection.id}/launch")

        assert resp.status_code == 202, resp.text
        assert calls == [(collection.id, None)]


# ---------------------------------------------------------------------------
# GET /launches, fail-closed target_type filter (regression lock)
# ---------------------------------------------------------------------------


class TestTargetTypeFailClosed:
    """Regression lock for a previously fail-open bug: an unrecognised
    target_type must reject the request (422), not silently fall through to
    an unfiltered `list_launches` query that would leak every user's launch
    history regardless of the target_id the caller asked to scope to."""

    def test_unknown_target_type_is_rejected_not_passed_through(self, http_client):
        c, db, app = http_client
        _make_launch_history(db, environment_item_id=1)
        _make_launch_history(db, game_item_bundle_id=2)
        user = _make_user(db)
        _set_active_user(app, user)

        resp = c.get("/api/v1/launches", params={"target_id": 1, "target_type": "not_a_real_type"})

        assert resp.status_code == 422, resp.text
        # Confirm the failure is a hard reject, not an unfiltered fallback
        # that would have returned both records above.
        assert "target_type" in resp.json()["detail"]

    def test_known_target_type_filters_correctly(self, http_client):
        c, db, app = http_client
        env_record = _make_launch_history(db, environment_item_id=1)
        collection_record = _make_launch_history(db, game_item_bundle_id=1)
        user = _make_user(db)
        _set_active_user(app, user)

        env_resp = c.get("/api/v1/launches", params={"target_id": 1, "target_type": "environment_item"})
        assert env_resp.status_code == 200, env_resp.text
        env_ids = {row["id"] for row in env_resp.json()}
        assert env_ids == {env_record.id}

        collection_resp = c.get(
            "/api/v1/launches", params={"target_id": 1, "target_type": "game_item_bundle"}
        )
        assert collection_resp.status_code == 200, collection_resp.text
        collection_ids = {row["id"] for row in collection_resp.json()}
        assert collection_ids == {collection_record.id}


# ---------------------------------------------------------------------------
# can_launch_media gating, POST /environment-items/{id}/launch
# ---------------------------------------------------------------------------


class TestCanLaunchMediaGateEnvironment:
    def test_can_launch_media_false_blocks_launch_at_route(self, http_client, monkeypatch):
        c, db, app = http_client
        env = _make_environment(db)
        calls = _stub_launch_environment(monkeypatch)
        blocked_user = _make_user(db, can_launch_media=False)
        _set_active_user(app, blocked_user)

        resp = c.post(f"/api/v1/environment-items/{env.id}/launch")

        assert resp.status_code == 403, resp.text
        # The gate must reject before the coordinator is ever reached.
        assert calls == []

    def test_can_launch_media_true_allows_launch_past_gate(self, http_client, monkeypatch):
        c, db, app = http_client
        env = _make_environment(db)
        calls = _stub_launch_environment(monkeypatch, history_id=88)
        permitted_user = _make_user(db, can_launch_media=True)
        _set_active_user(app, permitted_user)

        resp = c.post(f"/api/v1/environment-items/{env.id}/launch")

        assert resp.status_code == 202, resp.text
        assert resp.json()["launch_history_id"] == 88
        assert calls == [(env.id, None)]

    def test_missing_environment_returns_404(self, http_client, monkeypatch):
        c, db, app = http_client
        calls = _stub_launch_environment(monkeypatch)
        permitted_user = _make_user(db, can_launch_media=True)
        _set_active_user(app, permitted_user)

        resp = c.post("/api/v1/environment-items/999999/launch")

        assert resp.status_code == 404, resp.text
        assert calls == []


# ---------------------------------------------------------------------------
# can_launch_media gating, POST /launches/{id}/stop
# ---------------------------------------------------------------------------


class TestCanLaunchMediaGateStopLaunch:
    def test_can_launch_media_false_blocks_stop_at_route(self, http_client, monkeypatch):
        c, db, app = http_client
        record = _make_launch_history(db)
        calls = _stub_stop_launch(monkeypatch)
        blocked_user = _make_user(db, can_launch_media=False)
        _set_active_user(app, blocked_user)

        resp = c.post(f"/api/v1/launches/{record.id}/stop")

        assert resp.status_code == 403, resp.text
        # The gate must reject before svc.stop_launch is ever reached.
        assert calls == []

    def test_can_launch_media_true_allows_stop_past_gate(self, http_client, monkeypatch):
        c, db, app = http_client
        record = _make_launch_history(db)
        calls = _stub_stop_launch(monkeypatch, stopped=True)
        permitted_user = _make_user(db, can_launch_media=True)
        _set_active_user(app, permitted_user)

        resp = c.post(f"/api/v1/launches/{record.id}/stop")

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"stopped": True}
        assert calls == [(record.id, permitted_user.id)]
