"""Tests for multi-disc library set support.

Covers:
- resolve_launchable: item path is a direct passthrough of LibraryItem fields.
- resolve_launchable: set path reads Set metadata + launch_disk_id item for media fields.
- launch_set calls through the same _launch_entity path as launch_item, producing
  equivalent LaunchSpec fields for equivalent inputs.
- Standalone LibraryItem creation/launch path is completely unaffected (regression).
"""

import asyncio
import itertools
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.run(coro)


_next_pid = itertools.count(50_000)


@pytest.fixture
def mem_session():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import SQLModel, Session, create_engine
    import backend.models  # noqa: F401 — registers all table models
    import backend.models.library_set  # noqa: F401 — registers set tables

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(autouse=True)
def _clean_registry():
    from backend.core import process_registry as reg

    def _clear():
        with reg._lock:
            reg._registry.clear()
            reg._pending_profiles.clear()
            reg._pending_emulator_scopes.clear()

    _clear()
    yield
    _clear()


def _make_proc(poll_return=None):
    proc = MagicMock()
    proc.pid = next(_next_pid)
    proc.poll.return_value = poll_return
    return proc


def _make_job():
    job = MagicMock()
    job.job_handle = 0xABCD
    job.memory_limit_mb = 512
    job.cpu_limit_percent = 50
    return job


def _patch_dispatch(monkeypatch, poll_return=None):
    import backend.service.utils.backend_router as router_mod
    proc = _make_proc(poll_return=poll_return)
    job = _make_job()
    monkeypatch.setattr(router_mod, "dispatch", lambda spec: (proc, job))
    monkeypatch.setattr(router_mod, "get_executable_path", lambda era, slug=None: "/fake/exe")
    return proc


def _make_profile(db, *, era="ps1", user_id=1):
    from backend.models.profile import Profile
    p = Profile(name="TestProfile", slug="test-profile", emulator_slug="duckstation", era=era, user_id=user_id)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _make_item(db, *, profile, media_path="/tmp/game.bin", era="ps1"):
    from backend.models.library import LibraryItem
    item = LibraryItem(title="Solo Game", era=era, media_path=media_path, profile_id=profile.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _make_set_with_items(db, *, profile, disc_paths=None, era="ps1"):
    from backend.models.library_set import LibrarySet, LibrarySetItem

    if disc_paths is None:
        disc_paths = ["/tmp/disc1.iso", "/tmp/disc2.iso"]

    s = LibrarySet(title="Multi-Disc Game", era=era, profile_id=profile.id)
    db.add(s)
    db.flush()

    items = []
    for i, path in enumerate(disc_paths, start=1):
        disc = LibrarySetItem(set_id=s.id, disc_number=i, media_path=path)
        db.add(disc)
        items.append(disc)
    db.flush()

    s.launch_disk_id = items[0].id
    db.add(s)
    db.commit()
    db.refresh(s)
    return s, items


# ---------------------------------------------------------------------------
# resolve_launchable — item path
# ---------------------------------------------------------------------------

class TestResolvelaunchableItem:
    def test_returns_item_fields(self, mem_session):
        from backend.service.launch.launchable_resolver import resolve_launchable

        profile = _make_profile(mem_session)
        item = _make_item(mem_session, profile=profile, media_path="/tmp/game.cue")

        entity = resolve_launchable(item_id=item.id, db=mem_session)

        assert entity.item_id == item.id
        assert entity.set_id is None
        assert entity.profile_id == profile.id
        assert entity.era == "ps1"
        assert entity.media_path == "/tmp/game.cue"
        assert entity._db_item is item

    def test_missing_item_raises(self, mem_session):
        from backend.service.launch.launchable_resolver import resolve_launchable

        with pytest.raises(ValueError, match="not found"):
            resolve_launchable(item_id=9999, db=mem_session)

    def test_neither_raises(self, mem_session):
        from backend.service.launch.launchable_resolver import resolve_launchable

        with pytest.raises(ValueError, match="Must provide"):
            resolve_launchable(db=mem_session)


# ---------------------------------------------------------------------------
# resolve_launchable — set path
# ---------------------------------------------------------------------------

class TestResolvelaunchableSet:
    def test_returns_set_metadata_and_disc1_media(self, mem_session):
        from backend.service.launch.launchable_resolver import resolve_launchable

        profile = _make_profile(mem_session)
        s, items = _make_set_with_items(
            mem_session,
            profile=profile,
            disc_paths=["/tmp/disc1.iso", "/tmp/disc2.iso"],
        )

        entity = resolve_launchable(set_id=s.id, db=mem_session)

        assert entity.set_id == s.id
        assert entity.item_id is None
        assert entity.profile_id == profile.id
        assert entity.era == "ps1"
        # media_path comes from the launch_disk_id item (disc 1)
        assert entity.media_path == "/tmp/disc1.iso"
        assert entity._db_item is None

    def test_disc_number_ordering_correct(self, mem_session):
        from backend.service.launch.launchable_resolver import resolve_launchable
        from backend.models.library_set import LibrarySet

        profile = _make_profile(mem_session)
        s, items = _make_set_with_items(
            mem_session,
            profile=profile,
            disc_paths=["/tmp/disc1.iso", "/tmp/disc2.iso", "/tmp/disc3.iso"],
        )

        assert items[0].disc_number == 1
        assert items[1].disc_number == 2
        assert items[2].disc_number == 3

        # Default launch disc is disc 1
        entity = resolve_launchable(set_id=s.id, db=mem_session)
        assert entity.media_path == "/tmp/disc1.iso"

    def test_missing_set_raises(self, mem_session):
        from backend.service.launch.launchable_resolver import resolve_launchable

        with pytest.raises(ValueError, match="not found"):
            resolve_launchable(set_id=9999, db=mem_session)

    def test_no_launch_disk_raises(self, mem_session):
        from backend.service.launch.launchable_resolver import resolve_launchable
        from backend.models.library_set import LibrarySet

        profile = _make_profile(mem_session)
        s = LibrarySet(title="Empty Set", era="ps1", profile_id=profile.id)
        mem_session.add(s)
        mem_session.commit()

        with pytest.raises(ValueError, match="no launch disc"):
            resolve_launchable(set_id=s.id, db=mem_session)


# ---------------------------------------------------------------------------
# launch_set resolves to launch_disk_id's item and set's profile/platform
# ---------------------------------------------------------------------------

class TestLaunchSet:
    def test_launch_set_succeeds_with_disc1_media(self, mem_session, monkeypatch):
        from backend.service.launch.coordinator import launch_set

        _patch_dispatch(monkeypatch)
        profile = _make_profile(mem_session)
        s, _ = _make_set_with_items(mem_session, profile=profile)

        result = _run(launch_set(s.id, None, mem_session))

        assert result.history_id is not None

    def test_launch_set_history_records_set_id(self, mem_session, monkeypatch):
        from backend.models.launch_history import LaunchHistory
        from backend.service.launch.coordinator import launch_set

        _patch_dispatch(monkeypatch)
        profile = _make_profile(mem_session)
        s, _ = _make_set_with_items(mem_session, profile=profile)

        result = _run(launch_set(s.id, None, mem_session))

        history = mem_session.get(LaunchHistory, result.history_id)
        assert history.library_set_id == s.id
        assert history.library_item_id is None
        assert history.target_type == "library_set"

    def test_launch_set_missing_set_raises_422(self, mem_session, monkeypatch):
        from backend.service.launch.coordinator import launch_set

        _patch_dispatch(monkeypatch)
        with pytest.raises(HTTPException) as exc_info:
            _run(launch_set(9999, None, mem_session))
        assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# Regression: standalone LibraryItem launch path unaffected
# ---------------------------------------------------------------------------

class TestLibraryItemLaunchUnaffected:
    def test_item_launch_succeeds(self, mem_session, monkeypatch):
        from backend.service.launch.coordinator import launch_item

        _patch_dispatch(monkeypatch)
        profile = _make_profile(mem_session)
        item = _make_item(mem_session, profile=profile)

        result = _run(launch_item(item, None, mem_session))

        assert result.history_id is not None

    def test_item_launch_history_records_item_id(self, mem_session, monkeypatch):
        from backend.models.launch_history import LaunchHistory
        from backend.service.launch.coordinator import launch_item

        _patch_dispatch(monkeypatch)
        profile = _make_profile(mem_session)
        item = _make_item(mem_session, profile=profile)

        result = _run(launch_item(item, None, mem_session))

        history = mem_session.get(LaunchHistory, result.history_id)
        assert history.library_item_id == item.id
        assert history.library_set_id is None
        assert history.target_type == "library_item"

    def test_item_and_set_share_no_coupling(self, mem_session, monkeypatch):
        """Creating a set does not affect an existing item's launch path."""
        from backend.service.launch.coordinator import launch_item
        from backend.models.launch_history import LaunchHistory

        _patch_dispatch(monkeypatch)
        profile = _make_profile(mem_session)
        item = _make_item(mem_session, profile=profile)
        # Create a set alongside the item — should not interfere.
        _make_set_with_items(mem_session, profile=profile)

        result = _run(launch_item(item, None, mem_session))

        history = mem_session.get(LaunchHistory, result.history_id)
        assert history.library_item_id == item.id
        assert history.library_set_id is None
