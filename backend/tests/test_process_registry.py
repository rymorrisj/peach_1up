"""Tests for H7: process_registry exception handling — logging and propagation.

Covers:
- Successful registration stores the entry
- Registration failure propagates the exception and logs ERROR
- Deregistration failure (proc.terminate raises) logs WARNING and does not propagate
- Cleanup poll failure on one entry does not abort cleanup of remaining entries
- Cleanup logs WARNING for each failed entry
- Job handle close failure logs WARNING and does not abort other cleanup
"""

import pytest
from unittest.mock import MagicMock

import backend.core.process_registry as registry_mod
from backend.core.process_registry import ProcessEntry


def _make_proc(poll_return=0):
    proc = MagicMock()
    proc.poll.return_value = poll_return
    return proc


def _make_entry(proc=None, job_handle=None):
    if proc is None:
        proc = _make_proc()
    return ProcessEntry(
        process_handle=proc,
        job_handle=job_handle,
        library_item_id=None,
        profile_id=None,
    )


@pytest.fixture(autouse=True)
def clear_registry():
    registry_mod._registry.clear()
    yield
    registry_mod._registry.clear()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_successful_registration_stores_entry(self):
        entry = _make_entry()
        registry_mod.register(1, entry)
        assert registry_mod.get(1) is entry

    def test_registration_failure_propagates(self, monkeypatch):
        class _BadDict(dict):
            def __setitem__(self, k, v):
                raise RuntimeError("storage failure")
        monkeypatch.setattr(registry_mod, "_registry", _BadDict())
        with pytest.raises(RuntimeError, match="storage failure"):
            registry_mod.register(9, _make_entry())

    def test_registration_failure_logs_error(self, monkeypatch):
        class _BadDict(dict):
            def __setitem__(self, k, v):
                raise RuntimeError("disk full")
        monkeypatch.setattr(registry_mod, "_registry", _BadDict())
        mock_logger = MagicMock()
        monkeypatch.setattr(registry_mod, "logger", mock_logger)
        with pytest.raises(RuntimeError):
            registry_mod.register(9, _make_entry())
        mock_logger.error.assert_called_once()


# ---------------------------------------------------------------------------
# Deregistration (terminate)
# ---------------------------------------------------------------------------

class TestDeregistration:
    def test_terminate_failure_does_not_propagate(self):
        proc = _make_proc(poll_return=None)  # None → process still running
        proc.terminate.side_effect = OSError("access denied")
        registry_mod._registry[42] = _make_entry(proc=proc)
        result = registry_mod.terminate(42)
        assert result is True

    def test_terminate_failure_logs_warning(self, monkeypatch):
        proc = _make_proc(poll_return=None)
        proc.terminate.side_effect = OSError("access denied")
        registry_mod._registry[42] = _make_entry(proc=proc)
        mock_logger = MagicMock()
        monkeypatch.setattr(registry_mod, "logger", mock_logger)
        registry_mod.terminate(42)
        mock_logger.warning.assert_called()
        assert "42" in str(mock_logger.warning.call_args)

    def test_terminate_failure_still_removes_entry(self):
        proc = _make_proc(poll_return=None)
        proc.terminate.side_effect = OSError("access denied")
        registry_mod._registry[42] = _make_entry(proc=proc)
        registry_mod.terminate(42)
        assert registry_mod.get(42) is None


# ---------------------------------------------------------------------------
# Cleanup (cleanup_exited)
# ---------------------------------------------------------------------------

class TestCleanupExited:
    def test_cleanup_poll_failure_on_one_entry_does_not_abort_others(self):
        proc_a = MagicMock()
        proc_a.poll.side_effect = OSError("broken pipe")
        proc_b = _make_proc(poll_return=0)

        registry_mod._registry[101] = _make_entry(proc=proc_a)
        registry_mod._registry[102] = _make_entry(proc=proc_b)

        removed = registry_mod.cleanup_exited()
        assert any(pid == 102 for pid, _ in removed)

    def test_cleanup_logs_warning_for_poll_failure(self, monkeypatch):
        proc = MagicMock()
        proc.poll.side_effect = OSError("poll failed")
        registry_mod._registry[55] = _make_entry(proc=proc)
        mock_logger = MagicMock()
        monkeypatch.setattr(registry_mod, "logger", mock_logger)
        registry_mod.cleanup_exited()
        mock_logger.warning.assert_called()
        assert "55" in str(mock_logger.warning.call_args)

    def test_job_handle_close_failure_logs_warning(self, monkeypatch):
        proc = _make_proc(poll_return=0)
        job = MagicMock()
        job.close.side_effect = OSError("close failed")
        registry_mod._registry[77] = _make_entry(proc=proc, job_handle=job)
        mock_logger = MagicMock()
        monkeypatch.setattr(registry_mod, "logger", mock_logger)
        registry_mod.cleanup_exited()
        mock_logger.warning.assert_called()
        assert "77" in str(mock_logger.warning.call_args)

    def test_job_handle_close_failure_does_not_abort_other_cleanup(self):
        proc_a = _make_proc(poll_return=0)
        job_a = MagicMock()
        job_a.close.side_effect = OSError("close failed")

        proc_b = _make_proc(poll_return=0)

        registry_mod._registry[201] = _make_entry(proc=proc_a, job_handle=job_a)
        registry_mod._registry[202] = _make_entry(proc=proc_b)

        removed = registry_mod.cleanup_exited()
        pids_removed = {pid for pid, _ in removed}
        assert 201 in pids_removed
        assert 202 in pids_removed
