"""
Regression tests for startup stale-session cleanup (P6-7).

Tests _cleanup_stale_sessions() in backend.core.startup_tasks. That function
marks all LaunchHistory rows with ended_at=NULL as ended (ended_at=now,
exit_code=-1) on backend startup, so interrupted sessions never appear
as still running after a crash or hard restart.

All tests use a lightweight fake database — no SQLite or DB init required.
"""

from datetime import datetime


class _FakeLaunchHistory:
    def __init__(self, session_id: int, ended_at=None):
        self.id = session_id
        self.ended_at = ended_at
        self.exit_code = None


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, stale_rows=None):
        self._all_rows = stale_rows or []
        self.flushed = False
        self.rolled_back = False

    def query(self, _model):
        open_rows = [r for r in self._all_rows if r.ended_at is None]
        return _FakeQuery(open_rows)

    def flush(self):
        self.flushed = True

    def rollback(self):
        self.rolled_back = True


class _BrokenDB:
    def query(self, _model):
        raise RuntimeError("DB connection lost")

    def rollback(self):
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCleanupStaleSessions:
    def test_stale_session_gets_ended_at_set(self):
        from backend.core.startup_tasks import _cleanup_stale_sessions
        row = _FakeLaunchHistory(session_id=1, ended_at=None)
        db = _FakeDB(stale_rows=[row])
        _cleanup_stale_sessions(db)
        assert row.ended_at is not None

    def test_stale_session_exit_code_set_to_minus_one(self):
        from backend.core.startup_tasks import _cleanup_stale_sessions
        row = _FakeLaunchHistory(session_id=2, ended_at=None)
        db = _FakeDB(stale_rows=[row])
        _cleanup_stale_sessions(db)
        assert row.exit_code == -1

    def test_multiple_stale_sessions_all_closed(self):
        from backend.core.startup_tasks import _cleanup_stale_sessions
        rows = [_FakeLaunchHistory(session_id=i, ended_at=None) for i in range(5)]
        db = _FakeDB(stale_rows=rows)
        _cleanup_stale_sessions(db)
        for row in rows:
            assert row.ended_at is not None
            assert row.exit_code == -1

    def test_already_closed_session_is_not_modified(self):
        from backend.core.startup_tasks import _cleanup_stale_sessions
        closed_at = datetime(2026, 1, 1, 12, 0, 0)
        row = _FakeLaunchHistory(session_id=10, ended_at=closed_at)
        row.exit_code = 0
        db = _FakeDB(stale_rows=[row])
        _cleanup_stale_sessions(db)
        assert row.ended_at == closed_at
        assert row.exit_code == 0

    def test_mix_of_open_and_closed_sessions(self):
        from backend.core.startup_tasks import _cleanup_stale_sessions
        open_row = _FakeLaunchHistory(session_id=1, ended_at=None)
        closed_row = _FakeLaunchHistory(session_id=2, ended_at=datetime(2026, 3, 1))
        closed_row.exit_code = 0
        db = _FakeDB(stale_rows=[open_row, closed_row])
        _cleanup_stale_sessions(db)
        assert open_row.ended_at is not None
        assert open_row.exit_code == -1
        assert closed_row.ended_at == datetime(2026, 3, 1)
        assert closed_row.exit_code == 0

    def test_flush_called_even_with_no_stale_sessions(self):
        from backend.core.startup_tasks import _cleanup_stale_sessions
        db = _FakeDB(stale_rows=[])
        _cleanup_stale_sessions(db)
        assert db.flushed is True

    def test_flush_called_after_updating_stale_sessions(self):
        from backend.core.startup_tasks import _cleanup_stale_sessions
        row = _FakeLaunchHistory(session_id=1, ended_at=None)
        db = _FakeDB(stale_rows=[row])
        _cleanup_stale_sessions(db)
        assert db.flushed is True

    def test_db_error_does_not_propagate(self):
        """DB failures are caught and logged — startup must not abort."""
        from backend.core.startup_tasks import _cleanup_stale_sessions
        _cleanup_stale_sessions(_BrokenDB())  # must not raise

    def test_db_error_triggers_rollback(self):
        from backend.core.startup_tasks import _cleanup_stale_sessions

        class RollbackTrackingDB:
            def query(self, _model):
                raise RuntimeError("deliberate error")
            def rollback(self):
                self.rolled_back = True

        db = RollbackTrackingDB()
        _cleanup_stale_sessions(db)
        assert getattr(db, "rolled_back", False) is True

    def test_ended_at_is_a_datetime(self):
        from backend.core.startup_tasks import _cleanup_stale_sessions
        row = _FakeLaunchHistory(session_id=1, ended_at=None)
        db = _FakeDB(stale_rows=[row])
        _cleanup_stale_sessions(db)
        assert isinstance(row.ended_at, datetime)
