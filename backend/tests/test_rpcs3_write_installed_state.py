"""Tests for _write_installed_state (backend/service/backends/rpcs3.py),
previously zero coverage. This is the write-back that persists PS3 .pkg
install completion onto GameItemBundle.installed, called from two sites with
deliberately different failure semantics (reraise=False at launch(), the
best-effort bookkeeping path; reraise=True from the background install-poll
thread, a genuine background job failure with nothing else to protect). The
reraise split is the fail-loud-relevant branch: a caller that needs to know
the write failed must actually see the exception, not have it silently
swallowed the same way the best-effort launch-time call site does.

Uses an in-memory SQLite engine, monkeypatching
backend.core.database.get_engine (the module attribute _write_installed_state
resolves via its own deferred import at call time, so patching the module
attribute before each call is sufficient, no need to touch the real DB path).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlmodel import SQLModel

from backend.service.backends.rpcs3 import _write_installed_state


def _make_spec(**overrides):
    from backend.service.launch.launch_spec import LaunchSpec

    kwargs = dict(slug="rpcs3", era="ps3", source_type="game", collection_id=1)
    kwargs.update(overrides)
    return LaunchSpec(**kwargs)


@pytest.fixture
def mem_engine(monkeypatch):
    import backend.models  # noqa: F401, registers all table models with SQLModel.metadata
    import backend.core.database as database_mod

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database_mod, "get_engine", lambda: engine)
    return engine


def _make_bundle(engine, **overrides):
    from backend.models.game import GameItemBundle

    kwargs = dict(title="Bayonetta", era="ps3", slug="bayonetta", installed=False)
    kwargs.update(overrides)
    with Session(engine) as db:
        bundle = GameItemBundle(**kwargs)
        db.add(bundle)
        db.commit()
        db.refresh(bundle)
        return bundle.id


# ---------------------------------------------------------------------------
# Era/source_type/collection_id gate: a no-op skip, not an error, for any
# launch that isn't a PS3 game bundle install.
# ---------------------------------------------------------------------------


class TestEraGateSkipsWriteEntirely:
    def test_non_ps3_era_never_touches_the_db(self, mem_engine):
        spec = _make_spec(era="dos", source_type="game", collection_id=1)
        # Must not raise; the era gate returns before a session is ever opened,
        # so there's no DB state to assert on here.
        _write_installed_state(spec, True)

    def test_non_game_source_type_is_skipped(self, mem_engine):
        bundle_id = _make_bundle(mem_engine, installed=False)
        spec = _make_spec(source_type="app", collection_id=bundle_id)

        _write_installed_state(spec, True)

        with Session(mem_engine) as db:
            from backend.models.game import GameItemBundle

            bundle = db.get(GameItemBundle, bundle_id)
            assert bundle.installed is False

    def test_none_collection_id_is_skipped(self, mem_engine):
        spec = _make_spec(collection_id=None)
        # Must not raise even though there is nothing to look up.
        _write_installed_state(spec, True)


# ---------------------------------------------------------------------------
# Real write path
# ---------------------------------------------------------------------------


class TestWritesInstalledFlag:
    def test_sets_installed_true_when_previously_false(self, mem_engine):
        bundle_id = _make_bundle(mem_engine, installed=False)
        spec = _make_spec(collection_id=bundle_id)

        _write_installed_state(spec, True)

        with Session(mem_engine) as db:
            from backend.models.game import GameItemBundle

            assert db.get(GameItemBundle, bundle_id).installed is True

    def test_sets_installed_false_when_previously_true(self, mem_engine):
        bundle_id = _make_bundle(mem_engine, installed=True)
        spec = _make_spec(collection_id=bundle_id)

        _write_installed_state(spec, False)

        with Session(mem_engine) as db:
            from backend.models.game import GameItemBundle

            assert db.get(GameItemBundle, bundle_id).installed is False

    def test_noop_when_value_already_matches(self, mem_engine, monkeypatch):
        """collection.installed != installed guards the write, confirm no
        commit happens (and thus no updated_at bump) when the value is
        already correct."""
        bundle_id = _make_bundle(mem_engine, installed=True)
        spec = _make_spec(collection_id=bundle_id)

        commits = []
        original_commit = Session.commit

        def _tracked_commit(self):
            commits.append(1)
            return original_commit(self)

        monkeypatch.setattr(Session, "commit", _tracked_commit)

        _write_installed_state(spec, True)

        assert commits == []

    def test_nonexistent_collection_id_is_a_silent_noop(self, mem_engine):
        """collection is None after db.get: not an error, just nothing to write."""
        spec = _make_spec(collection_id=999999)
        _write_installed_state(spec, True)


# ---------------------------------------------------------------------------
# Fail-loud-relevant branch: reraise controls whether a write failure is
# swallowed (launch()'s best-effort call site) or actually propagates
# (the background install-poll call site, a real job failure).
# ---------------------------------------------------------------------------


class TestFailureHandlingReraiseSplit:
    def test_default_reraise_false_swallows_the_exception(self, mem_engine, monkeypatch):
        """Best-effort bookkeeping call site (launch()): a DB failure here
        must never propagate and fail an otherwise-successful launch."""
        bundle_id = _make_bundle(mem_engine, installed=False)
        spec = _make_spec(collection_id=bundle_id)

        def _boom(self):
            raise RuntimeError("simulated commit failure")

        monkeypatch.setattr(Session, "commit", _boom)

        # Must not raise.
        _write_installed_state(spec, True)

    def test_reraise_true_propagates_the_exception(self, mem_engine, monkeypatch):
        """Background install-poll call site (_wait_for_stable_and_terminate):
        this write failing is a genuine background job failure with no launch
        to protect, so it must fail loud, not disappear silently."""
        bundle_id = _make_bundle(mem_engine, installed=False)
        spec = _make_spec(collection_id=bundle_id)

        def _boom(self):
            raise RuntimeError("simulated commit failure")

        monkeypatch.setattr(Session, "commit", _boom)

        with pytest.raises(RuntimeError, match="simulated commit failure"):
            _write_installed_state(spec, True, reraise=True)

    def test_reraise_true_still_logs_before_raising(self, mem_engine, monkeypatch):
        bundle_id = _make_bundle(mem_engine, installed=False)
        spec = _make_spec(collection_id=bundle_id)

        def _boom(self):
            raise RuntimeError("simulated commit failure")

        monkeypatch.setattr(Session, "commit", _boom)

        logged = []
        import backend.service.backends.rpcs3 as rpcs3_mod

        monkeypatch.setattr(rpcs3_mod.logger, "error", lambda *a, **kw: logged.append((a, kw)))

        with pytest.raises(RuntimeError):
            _write_installed_state(spec, True, reraise=True)

        assert len(logged) == 1
