"""Tests for launch validation guards in service/launch/coordinator.py.

Covers the concurrent-launch guard: a launch is rejected if either (a) the
same profile_id, or (b) the same (emulator_slug, user_id) pair, already has
an active launch in flight. The guard is enforced inside coordinator.launch()
via process_registry.try_reserve()/release(), the single point all three
launch entry points (launch_collection, launch_environment, launch) converge on.

No pytest-asyncio plugin is configured in this project, so async calls are
driven through asyncio.run() from plain sync test functions.
"""

import asyncio
import itertools
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def mem_session():
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


class _FakeSettings:
    """Same fake-settings convention as test_game_items.py. get_settings() is
    a process-wide singleton gated by init_settings(), so unit tests patch it
    directly instead of relying on a real init from another test file."""

    def get(self, key, default=None):
        return default

    def get_env_var(self, key):
        return ""


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch):
    import backend.core.settings as settings_mod
    monkeypatch.setattr(settings_mod, "get_settings", lambda: _FakeSettings())


@pytest.fixture(autouse=True)
def _clean_registry():
    """process_registry is a process-wide singleton; clear it around every test
    so leftover reservations/entries from one test can't leak into the next."""
    from backend.core import process_registry as reg

    def _clear():
        with reg._lock:
            reg._registry.clear()
            reg._pending_profiles.clear()
            reg._pending_emulator_scopes.clear()

    _clear()
    yield
    _clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_next_pid = itertools.count(10_000)


def _make_proc(poll_return=None):
    proc = MagicMock()
    proc.pid = next(_next_pid)
    proc.poll.return_value = poll_return
    return proc


def _make_job():
    job = MagicMock()
    job.job_handle = 0xABCD  # truthy sentinel, coordinator requires this to not be None
    job.memory_limit_mb = 512
    job.cpu_limit_percent = 50
    return job


def _patch_backend_router(monkeypatch, dispatch_fn, executable_path="/fake/exe"):
    import backend.service.utils.backend_router as router_mod
    monkeypatch.setattr(router_mod, "dispatch", dispatch_fn)
    monkeypatch.setattr(router_mod, "get_executable_path", lambda era, slug=None: executable_path)


def _make_profile(db, *, name, emulator_slug, user_item_id, era="ps1"):
    from backend.models.profile import ProfileItem
    profile = ProfileItem(name=name, slug=name.lower(), emulator_slug=emulator_slug, era=era, user_item_id=user_item_id)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def _make_item(db, *, profile, era="ps1"):
    # Build a collection-of-one (parent + single leaf) and return the collection,
    # the sole game launch target after the set/item consolidation.
    from backend.models.game import GameItemBundle, GameItem
    collection = GameItemBundle(
        title=f"Game-{profile.id}", era=era, slug=f"game-{profile.id}", profile_item_id=profile.id
    )
    db.add(collection)
    db.flush()
    leaf = GameItem(game_item_bundle_id=collection.id, disc_number=1, file_path="/tmp/game.bin")
    db.add(leaf)
    db.flush()
    collection.launch_disk_id = leaf.id
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return collection


def _make_platform(db, *, profile, era="ps1"):
    from backend.models.environment import EnvironmentItem
    platform = EnvironmentItem(
        name=f"Plat-{profile.id}",
        era=era,
        emulator_slug=profile.emulator_slug,
        profile_item_id=profile.id,
        working_image_path=f"/tmp/wp-{profile.id}.img",
        config_path=f"/tmp/cfg-{profile.id}.cfg",
    )
    db.add(platform)
    db.commit()
    db.refresh(platform)
    return platform


class TestResolveProfileForItem:
    def test_nonexistent_profile_id_returns_404(self, mem_session):
        from backend.service.launch.coordinator import _resolve_profile_for_item

        # entity_profile_id=None, explicit profile_id=9999 (does not exist) → 404
        with pytest.raises(HTTPException) as exc_info:
            _resolve_profile_for_item(None, 9999, mem_session)

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# 1. Same profile_id, second launch_collection request while first is still active
# ---------------------------------------------------------------------------

class TestSameProfileRejected:
    def test_second_launch_item_same_profile_rejected(self, mem_session, monkeypatch):
        from backend.service.launch.coordinator import launch_collection

        profile = _make_profile(mem_session, name="P1", emulator_slug="duckstation", user_item_id=1)
        item = _make_item(mem_session, profile=profile)

        calls = []

        def fake_dispatch(spec):
            calls.append(spec)
            return (_make_proc(poll_return=None), _make_job())

        _patch_backend_router(monkeypatch, fake_dispatch)

        # First launch succeeds and remains "active" (proc never exits).
        result = _run(launch_collection(item.id, None, mem_session))
        assert result.history_id is not None
        assert len(calls) == 1

        # Second launch for the same profile must be rejected before dispatch.
        with pytest.raises(HTTPException) as exc_info:
            _run(launch_collection(item.id, None, mem_session))
        assert exc_info.value.status_code == 409
        assert len(calls) == 1  # dispatch was never reached for the rejected launch


# ---------------------------------------------------------------------------
# 2. Same (emulator_slug, user_id), different profile_id -> rejected
# ---------------------------------------------------------------------------

class TestSameEmulatorUserDifferentProfileRejected:
    def test_second_launch_environment_same_emulator_user_rejected(self, mem_session, monkeypatch):
        from backend.service.launch.coordinator import launch_environment

        profile1 = _make_profile(mem_session, name="P1", emulator_slug="duckstation", user_item_id=1)
        profile2 = _make_profile(mem_session, name="P2", emulator_slug="duckstation", user_item_id=1)
        platform1 = _make_platform(mem_session, profile=profile1)
        platform2 = _make_platform(mem_session, profile=profile2)

        calls = []

        def fake_dispatch(spec):
            calls.append(spec)
            return (_make_proc(poll_return=None), _make_job())

        _patch_backend_router(monkeypatch, fake_dispatch)

        result = _run(launch_environment(platform1, None, mem_session))
        assert result.history_id is not None
        assert len(calls) == 1

        # Different profile_id, but same (emulator_slug, user_id) pair.
        with pytest.raises(HTTPException) as exc_info:
            _run(launch_environment(platform2, None, mem_session))
        assert exc_info.value.status_code == 409
        assert len(calls) == 1


# ---------------------------------------------------------------------------
# 3. Different profile_id AND different (emulator_slug, user_id) -> succeeds
# ---------------------------------------------------------------------------

class TestDifferentKeysSucceed:
    def test_unrelated_launch_succeeds_while_another_is_active(self, mem_session, monkeypatch):
        from backend.service.launch.coordinator import launch_environment

        profile1 = _make_profile(mem_session, name="P1", emulator_slug="duckstation", user_item_id=1)
        profile2 = _make_profile(mem_session, name="P2", emulator_slug="flycast", user_item_id=2, era="dreamcast")
        platform1 = _make_platform(mem_session, profile=profile1)
        platform2 = _make_platform(mem_session, profile=profile2, era="dreamcast")

        calls = []

        def fake_dispatch(spec):
            calls.append(spec)
            return (_make_proc(poll_return=None), _make_job())

        _patch_backend_router(monkeypatch, fake_dispatch)

        result1 = _run(launch_environment(platform1, None, mem_session))
        assert result1.history_id is not None

        # Different profile_id and different (emulator_slug, user_id) -> must succeed.
        result2 = _run(launch_environment(platform2, None, mem_session))
        assert result2.history_id is not None
        assert len(calls) == 2


# ---------------------------------------------------------------------------
# 4. Reservation is released on immediate-exit failure, no phantom lock
# ---------------------------------------------------------------------------

class TestRollbackOnImmediateExit:
    def test_reservation_released_after_immediate_crash(self, mem_session, monkeypatch):
        from backend.service.launch.coordinator import launch_collection

        profile = _make_profile(mem_session, name="P1", emulator_slug="duckstation", user_item_id=1)
        item = _make_item(mem_session, profile=profile)

        dispatch_results = [
            (_make_proc(poll_return=1), _make_job()),    # crashes immediately
            (_make_proc(poll_return=None), _make_job()),  # runs fine
        ]

        def fake_dispatch(spec):
            return dispatch_results.pop(0)

        _patch_backend_router(monkeypatch, fake_dispatch)

        # First launch: backend reports an immediate exit -> 500, not 409.
        with pytest.raises(HTTPException) as exc_info:
            _run(launch_collection(item.id, None, mem_session))
        assert exc_info.value.status_code == 500

        # The crash must have released both the reservation and the registry
        # entry (process_registry.terminate at the immediate-exit path), a
        # retry for the same profile must succeed, not hit the 409 guard.
        result = _run(launch_collection(item.id, None, mem_session))
        assert result.history_id is not None


# ---------------------------------------------------------------------------
# 4b. A clean exit (code 0) within the inline window is not a crash, the
#     launch must succeed, unlike a non-zero exit in the same window.
# ---------------------------------------------------------------------------

class TestCleanExitZeroNotTreatedAsCrash:
    def test_immediate_clean_exit_does_not_raise(self, mem_session, monkeypatch):
        from backend.service.launch.coordinator import launch_collection

        profile = _make_profile(mem_session, name="P1", emulator_slug="duckstation", user_item_id=1)
        item = _make_item(mem_session, profile=profile)

        def fake_dispatch(spec):
            return (_make_proc(poll_return=0), _make_job())

        _patch_backend_router(monkeypatch, fake_dispatch)

        # Exit code 0 within the inline window must not be treated as a
        # crash, the launch should succeed, not raise a 500.
        result = _run(launch_collection(item.id, None, mem_session))
        assert result.history_id is not None

    def test_immediate_nonzero_exit_still_raises(self, mem_session, monkeypatch):
        """Non-zero exit within the same window is unchanged: still a 500."""
        from backend.service.launch.coordinator import launch_collection

        profile = _make_profile(mem_session, name="P2", emulator_slug="flycast", user_item_id=2, era="dreamcast")
        item = _make_item(mem_session, profile=profile, era="dreamcast")

        def fake_dispatch(spec):
            return (_make_proc(poll_return=1), _make_job())

        _patch_backend_router(monkeypatch, fake_dispatch)

        with pytest.raises(HTTPException) as exc_info:
            _run(launch_collection(item.id, None, mem_session))
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# 5. Back-to-back reservation calls close the TOCTOU race, not just narrow it
# ---------------------------------------------------------------------------

class TestReservationRaceClosed:
    def test_second_reservation_for_same_profile_fails_without_registration(self):
        from backend.core import process_registry

        reservation1 = process_registry.try_reserve(profile_item_id=42, emulator_slug="duckstation", user_item_id=1)
        assert reservation1 is not None

        # No registration happened in between, this is the exact TOCTOU
        # window a naive "check, then separately mark" implementation would
        # leave open. A real reservation must close it.
        reservation2 = process_registry.try_reserve(profile_item_id=42, emulator_slug="other-slug", user_item_id=99)
        assert reservation2 is None

        process_registry.release(reservation1)

        # Once released, the key is free again.
        reservation3 = process_registry.try_reserve(profile_item_id=42, emulator_slug="duckstation", user_item_id=1)
        assert reservation3 is not None
        process_registry.release(reservation3)

    def test_second_reservation_for_same_emulator_user_fails(self):
        from backend.core import process_registry

        reservation1 = process_registry.try_reserve(profile_item_id=1, emulator_slug="flycast", user_item_id=7)
        assert reservation1 is not None

        # Different profile_id, same (emulator_slug, user_id), must also collide.
        reservation2 = process_registry.try_reserve(profile_item_id=2, emulator_slug="flycast", user_item_id=7)
        assert reservation2 is None

        process_registry.release(reservation1)


# ---------------------------------------------------------------------------
# 6. process_registry.register() raising must kill the spawned process,
#    surface a curated 500 (not the raw exception), and still release the
#    reservation so a retry for the same key can proceed.
# ---------------------------------------------------------------------------

class TestRegistrationFailureKillsProcessAndReleasesReservation:
    def test_register_failure_kills_process_curates_error_and_releases_reservation(self, mem_session, monkeypatch):
        from backend.core import process_registry
        from backend.service.launch.coordinator import launch_collection

        profile = _make_profile(mem_session, name="P1", emulator_slug="duckstation", user_item_id=1)
        item = _make_item(mem_session, profile=profile)

        crashing_proc = _make_proc(poll_return=None)
        crashing_job = _make_job()

        def fake_dispatch(spec):
            return (crashing_proc, crashing_job)

        _patch_backend_router(monkeypatch, fake_dispatch)

        original_register = process_registry.register

        def failing_register(pid, entry):
            raise RuntimeError("registry write failed")

        monkeypatch.setattr(process_registry, "register", failing_register)

        with pytest.raises(HTTPException) as exc_info:
            _run(launch_collection(item.id, None, mem_session))

        # (b) curated 500, not the raw RuntimeError, surfaces to the caller.
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Launch failed during process registration; process was terminated."

        # (a) the spawned process was killed.
        crashing_proc.kill.assert_called_once()

        # process_registry.register() never succeeded, so no entry exists in
        # the registry either, only a leaked pending marker could block a
        # retry from here.
        monkeypatch.setattr(process_registry, "register", original_register)

        retry_proc = _make_proc(poll_return=None)
        retry_job = _make_job()

        def fake_dispatch_retry(spec):
            return (retry_proc, retry_job)

        _patch_backend_router(monkeypatch, fake_dispatch_retry)

        # (c) reservation was released, a retry for the same profile_id and
        # the same (emulator_slug, user_id) pair must succeed, not hit 409.
        result = _run(launch_collection(item.id, None, mem_session))
        assert result.history_id is not None
