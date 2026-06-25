"""Tests for short-lived launch detection in monitor.py and coordinator.py.

Covers:
- Process exits within 3s → launch_review_flagged set on item (async, next launch)
- Process survives the 3s window → flag not set
- launch_review_flagged already True → returned immediately in LaunchResponse
- Environment launch → monitor not triggered
- Item launch scope is backend-agnostic (is_environment), not a slug list
- coordinator._poll_for_immediate_exit — synchronous inline crash check that
  makes the *current* launch response reflect failure, not just flag for later
"""

import asyncio
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
# poll_short_lived — core detection logic (replaces _monitor_short_lived_launch)
# ---------------------------------------------------------------------------

class TestMonitorShortLivedLaunch:
    def _register_and_poll(self, monkeypatch, item_id, proc, launch_time):
        """Register a pending check then call poll_short_lived once."""
        import backend.service.launch.monitor as mod
        from backend.service.launch.monitor import register_short_lived_check, poll_short_lived

        # Clear any leftover state from prior tests
        with mod._lock:
            mod._pending.clear()

        register_short_lived_check(item_id, proc, launch_time)

        flagged = []
        monkeypatch.setattr(mod, "_flag_short_lived_item", lambda iid: flagged.append(iid))

        poll_short_lived()
        return flagged

    def test_exits_immediately_flags_item(self, monkeypatch):
        """Poll returns exit code on first call → _flag_short_lived_item called."""
        proc = _make_proc(poll_return=1)
        flagged = self._register_and_poll(monkeypatch, 42, proc, time.monotonic())
        assert flagged == [42]

    def test_exits_with_zero_exit_code_also_flags(self, monkeypatch):
        """Exit code 0 (clean exit) within window is still flagged as short-lived."""
        proc = _make_proc(poll_return=0)
        flagged = self._register_and_poll(monkeypatch, 99, proc, time.monotonic())
        assert flagged == [99]

    def test_process_survives_window_does_not_flag(self, monkeypatch):
        """Poll always returns None and the window is already expired → no flag."""
        import backend.service.launch.monitor as mod
        from backend.service.launch.monitor import register_short_lived_check, poll_short_lived

        with mod._lock:
            mod._pending.clear()

        proc = _make_proc(poll_return=None)
        # Launch time 5 seconds in the past so deadline is already expired
        past_launch = time.monotonic() - 5.0
        register_short_lived_check(42, proc, past_launch)

        flagged = []
        monkeypatch.setattr(mod, "_flag_short_lived_item", lambda iid: flagged.append(iid))

        poll_short_lived()
        assert flagged == []

    def test_warning_logged_on_short_exit(self, monkeypatch):
        """WARNING is emitted when a short-lived exit is detected."""
        import backend.service.launch.monitor as mod
        from backend.service.launch.monitor import register_short_lived_check, poll_short_lived

        with mod._lock:
            mod._pending.clear()

        proc = _make_proc(poll_return=2)
        register_short_lived_check(7, proc, time.monotonic())

        monkeypatch.setattr(mod, "_flag_short_lived_item", lambda iid: None)
        mock_logger = MagicMock()
        monkeypatch.setattr(mod, "logger", mock_logger)

        poll_short_lived()

        mock_logger.warning.assert_called_once()
        call_str = str(mock_logger.warning.call_args)
        assert "7" in call_str

    def test_no_warning_when_process_survives(self, monkeypatch):
        """No WARNING emitted when process outlives the window."""
        import backend.service.launch.monitor as mod
        from backend.service.launch.monitor import register_short_lived_check, poll_short_lived

        with mod._lock:
            mod._pending.clear()

        proc = _make_proc(poll_return=None)
        register_short_lived_check(7, proc, time.monotonic() - 5.0)

        monkeypatch.setattr(mod, "_flag_short_lived_item", lambda iid: None)
        mock_logger = MagicMock()
        monkeypatch.setattr(mod, "logger", mock_logger)

        poll_short_lived()

        mock_logger.warning.assert_not_called()


# ---------------------------------------------------------------------------
# _flag_short_lived_item — DB write helper
# ---------------------------------------------------------------------------

class TestFlagShortLivedItem:
    def test_sets_flag_and_commits(self, monkeypatch):
        """Sets launch_review_flagged = True and calls commit."""
        import backend.service.launch.monitor as mod
        from backend.service.launch.monitor import _flag_short_lived_item

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
        from backend.service.launch.monitor import _flag_short_lived_item

        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.get.return_value = None

        monkeypatch.setattr("backend.core.database.get_engine", lambda: MagicMock())
        monkeypatch.setattr("sqlalchemy.orm.Session", lambda engine: mock_db)

        _flag_short_lived_item(999)  # should not raise

    def test_db_error_logs_error_and_raises(self, monkeypatch):
        """DB failure logs ERROR and re-raises the exception."""
        import backend.service.launch.monitor as mod
        from backend.service.launch.monitor import _flag_short_lived_item

        monkeypatch.setattr("backend.core.database.get_engine", lambda: MagicMock())
        monkeypatch.setattr(
            "sqlalchemy.orm.Session",
            lambda engine: (_ for _ in ()).throw(RuntimeError("db failure")),
        )

        mock_logger = MagicMock()
        monkeypatch.setattr(mod, "logger", mock_logger)

        with pytest.raises(RuntimeError, match="db failure"):
            _flag_short_lived_item(1)

        mock_logger.error.assert_called_once()


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
        """launch_environment source contains no call to register_short_lived_check."""
        import backend.api.routes.launches as mod
        src = inspect.getsource(mod.launch_environment)
        assert "register_short_lived_check" not in src


# ---------------------------------------------------------------------------
# Backend-agnostic scope — monitor covers any item launch, not a slug list
# ---------------------------------------------------------------------------

class TestItemLaunchScopeNotSlugList:
    def test_coordinator_launch_gates_monitor_on_item_id_not_slug(self):
        """coordinator.launch() gates the short-lived check on is_environment
        (i.e. any library-item launch), not on a hardcoded backend slug —
        covers DuckStation/PCSX2/Mesen/Project64/Flycast/DOSBox uniformly."""
        import backend.service.launch.coordinator as coord
        src = inspect.getsource(coord.launch)
        assert "BackendSlug.DOSBOX" not in src
        assert "not is_environment" in src
        assert "register_short_lived_check" in src

    def test_coordinator_uses_resolve_backend_name(self):
        """Backend selection is dynamic via resolve_backend_name in the coordinator."""
        import backend.service.launch.coordinator as coord
        src = inspect.getsource(coord._build_spec_for_entity)
        assert "resolve_backend_name" in src


# ---------------------------------------------------------------------------
# _poll_for_immediate_exit — synchronous inline crash check
# ---------------------------------------------------------------------------

class TestPollForImmediateExit:
    def test_returns_exit_code_when_already_exited(self):
        """proc already exited before the first poll → returns that code immediately."""
        from backend.service.launch.coordinator import _poll_for_immediate_exit

        proc = _make_proc(poll_return=7)
        result = asyncio.run(_poll_for_immediate_exit(proc, timeout=0.3))
        assert result == 7

    def test_returns_exit_code_zero_when_already_exited(self):
        """Exit code 0 (clean exit) is still treated as 'exited', not 'still running'."""
        from backend.service.launch.coordinator import _poll_for_immediate_exit

        proc = _make_proc(poll_return=0)
        result = asyncio.run(_poll_for_immediate_exit(proc, timeout=0.3))
        assert result == 0

    def test_returns_none_when_process_survives_window(self):
        """proc.poll() always returns None → window elapses, returns None."""
        from backend.service.launch.coordinator import _poll_for_immediate_exit

        proc = _make_proc(poll_return=None)
        result = asyncio.run(_poll_for_immediate_exit(proc, timeout=0.2))
        assert result is None

    def test_detects_exit_partway_through_window(self):
        """proc exits after a couple of poll iterations, within the window."""
        from backend.service.launch.coordinator import _poll_for_immediate_exit

        proc = MagicMock()
        proc.poll.side_effect = [None, None, 1]
        result = asyncio.run(_poll_for_immediate_exit(proc, timeout=1.0))
        assert result == 1


class TestInlineCheckFailsCurrentResponse:
    def test_immediate_exit_raises_http_exception_not_success(self, monkeypatch):
        """The whole point of the inline check: an immediate exit must raise
        HTTPException for *this* request, not just flag the item for later."""
        import backend.service.launch.coordinator as coord
        from fastapi import HTTPException

        src = inspect.getsource(coord.launch)
        # The inline check must run before LaunchResult is constructed, and
        # must raise rather than silently falling through to a 200 response.
        assert "_poll_for_immediate_exit" in src
        assert "raise HTTPException" in src
        assert src.index("_poll_for_immediate_exit") < src.index("return LaunchResult(")

    def test_gate_excludes_clean_exit_code_zero(self):
        """A clean exit (code 0) within the inline window is not a crash --
        the gate must check exit_code != 0, not just exit_code is not None,
        or a deliberate fast-exiting launch would be flagged as a failure."""
        import backend.service.launch.coordinator as coord

        src = inspect.getsource(coord.launch)
        assert "exit_code is not None and exit_code != 0" in src
