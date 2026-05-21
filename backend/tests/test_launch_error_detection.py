"""Tests for short-lived launch detection in launches.py.

Covers:
- Process exits within 3s → launch_review_flagged set on item
- Process survives the 3s window → flag not set
- launch_review_flagged already True → returned immediately in LaunchResponse
- Environment launch → monitor not triggered
- Non-DOSBox backend → monitor not triggered (structural check)
"""

import inspect
import time
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_proc(poll_return):
    proc = MagicMock()
    proc.poll.return_value = poll_return
    return proc


# ---------------------------------------------------------------------------
# _monitor_short_lived_launch — core detection logic
# ---------------------------------------------------------------------------

class TestMonitorShortLivedLaunch:
    def test_exits_immediately_flags_item(self, monkeypatch):
        """Poll returns exit code on first call → _flag_short_lived_item called."""
        import backend.api.routes.launches as mod
        from backend.api.routes.launches import _monitor_short_lived_launch

        proc = _make_proc(poll_return=1)
        flagged = []
        monkeypatch.setattr(mod, "_flag_short_lived_item", lambda iid: flagged.append(iid))

        _monitor_short_lived_launch(42, proc, time.monotonic(), _timeout=3.0)

        assert flagged == [42]

    def test_exits_with_zero_exit_code_also_flags(self, monkeypatch):
        """Exit code 0 (clean exit) within window is still flagged as short-lived."""
        import backend.api.routes.launches as mod
        from backend.api.routes.launches import _monitor_short_lived_launch

        proc = _make_proc(poll_return=0)
        flagged = []
        monkeypatch.setattr(mod, "_flag_short_lived_item", lambda iid: flagged.append(iid))

        _monitor_short_lived_launch(99, proc, time.monotonic(), _timeout=3.0)

        assert flagged == [99]

    def test_process_survives_window_does_not_flag(self, monkeypatch):
        """Poll always returns None and the window is already expired → no flag."""
        import backend.api.routes.launches as mod
        from backend.api.routes.launches import _monitor_short_lived_launch

        proc = _make_proc(poll_return=None)
        flagged = []
        monkeypatch.setattr(mod, "_flag_short_lived_item", lambda iid: flagged.append(iid))

        # Pass launch_time 5 seconds in the past so deadline is already expired
        past_launch = time.monotonic() - 5.0
        _monitor_short_lived_launch(42, proc, past_launch, _timeout=3.0)

        assert flagged == []

    def test_warning_logged_on_short_exit(self, monkeypatch):
        """WARNING is emitted when a short-lived exit is detected."""
        import backend.api.routes.launches as mod
        from backend.api.routes.launches import _monitor_short_lived_launch

        proc = _make_proc(poll_return=2)
        monkeypatch.setattr(mod, "_flag_short_lived_item", lambda iid: None)

        mock_logger = MagicMock()
        monkeypatch.setattr(mod, "logger", mock_logger)

        _monitor_short_lived_launch(7, proc, time.monotonic(), _timeout=3.0)

        mock_logger.warning.assert_called_once()
        call_str = str(mock_logger.warning.call_args)
        assert "7" in call_str

    def test_no_warning_when_process_survives(self, monkeypatch):
        """No WARNING emitted when process outlives the window."""
        import backend.api.routes.launches as mod
        from backend.api.routes.launches import _monitor_short_lived_launch

        proc = _make_proc(poll_return=None)
        monkeypatch.setattr(mod, "_flag_short_lived_item", lambda iid: None)

        mock_logger = MagicMock()
        monkeypatch.setattr(mod, "logger", mock_logger)

        _monitor_short_lived_launch(7, proc, time.monotonic() - 5.0, _timeout=3.0)

        mock_logger.warning.assert_not_called()


# ---------------------------------------------------------------------------
# _flag_short_lived_item — DB write helper
# ---------------------------------------------------------------------------

class TestFlagShortLivedItem:
    def test_sets_flag_and_commits(self, monkeypatch):
        """Sets launch_review_flagged = True and calls commit."""
        import backend.api.routes.launches as mod
        from backend.api.routes.launches import _flag_short_lived_item

        mock_item = MagicMock()
        mock_item.launch_review_flagged = False

        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.get.return_value = mock_item

        monkeypatch.setattr("backend.core.database.get_engine", lambda: MagicMock())
        monkeypatch.setattr("sqlalchemy.orm.Session", lambda engine: mock_db)

        _flag_short_lived_item(42)

        assert mock_item.launch_review_flagged is True
        mock_db.commit.assert_called_once()

    def test_missing_item_does_not_raise(self, monkeypatch):
        """Item not found in DB → function completes without raising."""
        from backend.api.routes.launches import _flag_short_lived_item

        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.get.return_value = None

        monkeypatch.setattr("backend.core.database.get_engine", lambda: MagicMock())
        monkeypatch.setattr("sqlalchemy.orm.Session", lambda engine: mock_db)

        _flag_short_lived_item(999)  # should not raise

    def test_db_error_logs_warning_and_does_not_raise(self, monkeypatch):
        """DB failure logs WARNING and does not propagate."""
        import backend.api.routes.launches as mod
        from backend.api.routes.launches import _flag_short_lived_item

        monkeypatch.setattr("backend.core.database.get_engine", lambda: MagicMock())
        monkeypatch.setattr(
            "sqlalchemy.orm.Session",
            lambda engine: (_ for _ in ()).throw(RuntimeError("db failure")),
        )

        mock_logger = MagicMock()
        monkeypatch.setattr(mod, "logger", mock_logger)

        _flag_short_lived_item(1)  # should not raise

        mock_logger.warning.assert_called_once()


# ---------------------------------------------------------------------------
# LaunchResponse — flag already True before launch
# ---------------------------------------------------------------------------

class TestLaunchResponseFlag:
    def test_field_defaults_to_false(self):
        """LaunchResponse.launch_review_flagged defaults to False."""
        from backend.api.routes.launches import LaunchResponse
        r = LaunchResponse(launch_history_id=1)
        assert r.launch_review_flagged is False

    def test_field_carries_true_value(self):
        """LaunchResponse carries a pre-existing True flag without delay."""
        from backend.api.routes.launches import LaunchResponse
        r = LaunchResponse(launch_history_id=1, launch_review_flagged=True)
        assert r.launch_review_flagged is True


# ---------------------------------------------------------------------------
# Environment launch — monitor must not be triggered
# ---------------------------------------------------------------------------

class TestEnvironmentLaunchNoMonitor:
    def test_launch_environment_does_not_call_monitor(self):
        """launch_environment source contains no call to _monitor_short_lived_launch."""
        import backend.api.routes.launches as mod
        src = inspect.getsource(mod.launch_environment)
        assert "_monitor_short_lived_launch" not in src


# ---------------------------------------------------------------------------
# Non-DOSBox backend — monitor must be guarded by backend check
# ---------------------------------------------------------------------------

class TestNonDosboxBackendNoMonitor:
    def test_launch_item_gates_monitor_on_dosbox_backend(self):
        """launch_item source shows monitor is conditional on DOSBox backend."""
        import backend.api.routes.launches as mod
        src = inspect.getsource(mod.launch_item)
        assert "_monitor_short_lived_launch" in src
        assert "BackendSlug.DOSBOX" in src

    def test_launch_item_uses_resolve_backend_name(self):
        """launch_item resolves backend dynamically rather than hardcoding era."""
        import backend.api.routes.launches as mod
        src = inspect.getsource(mod.launch_item)
        assert "resolve_backend_name" in src
