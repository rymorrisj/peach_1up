"""Tests for backend.core.rate_limit: sliding-window counter, lockout, retry-after, sweep.

Run with:
    pytest backend/tests/test_rate_limit.py
"""
import time

import pytest


@pytest.fixture(autouse=True)
def _reset_globals():
    """Reset module-level singletons around every test so tests are isolated."""
    import backend.core.rate_limit as rl

    with rl._lock:
        rl._attempts.clear()
        rl._windows.clear()
        rl._last_sweep = 0.0
    yield
    with rl._lock:
        rl._attempts.clear()
        rl._windows.clear()
        rl._last_sweep = 0.0


class TestCheckAndRecord:
    def test_first_call_is_allowed(self):
        from backend.core.rate_limit import check_and_record

        allowed, retry_after = check_and_record("key1", limit=3, window_seconds=60.0)
        assert allowed is True
        assert retry_after == 0.0

    def test_calls_up_to_limit_are_all_allowed(self):
        from backend.core.rate_limit import check_and_record

        for _ in range(3):
            allowed, _ = check_and_record("key2", limit=3, window_seconds=60.0)
            assert allowed is True

    def test_call_beyond_limit_is_blocked(self):
        from backend.core.rate_limit import check_and_record

        for _ in range(3):
            check_and_record("key3", limit=3, window_seconds=60.0)

        allowed, retry_after = check_and_record("key3", limit=3, window_seconds=60.0)
        assert allowed is False
        assert retry_after > 0.0

    def test_blocked_attempts_do_not_extend_the_window(self, monkeypatch):
        """Rejected calls must not be recorded, so flooding cannot push the unlock
        point forward beyond the original window expiry."""
        import backend.core.rate_limit as rl

        fake_now = 0.0
        monkeypatch.setattr(time, "monotonic", lambda: fake_now)

        for _ in range(3):
            rl.check_and_record("key4", limit=3, window_seconds=10.0)

        for _ in range(100):
            allowed, _ = rl.check_and_record("key4", limit=3, window_seconds=10.0)
            assert allowed is False

        # Just past the original window, all three allowed timestamps expired.
        fake_now = 10.01
        allowed, _ = rl.check_and_record("key4", limit=3, window_seconds=10.0)
        assert allowed is True

    def test_retry_after_reflects_oldest_allowed_attempt(self, monkeypatch):
        """retry_after = oldest_timestamp + window - now."""
        import backend.core.rate_limit as rl

        fake_now = 0.0
        monkeypatch.setattr(time, "monotonic", lambda: fake_now)

        for _ in range(3):
            rl.check_and_record("key5", limit=3, window_seconds=10.0)

        # At t=2.0, oldest allowed attempt was at t=0.0: retry_after = 0+10-2 = 8.0
        fake_now = 2.0
        allowed, retry_after = rl.check_and_record("key5", limit=3, window_seconds=10.0)
        assert allowed is False
        assert abs(retry_after - 8.0) < 0.01

    def test_different_keys_are_isolated(self):
        from backend.core.rate_limit import check_and_record

        for _ in range(3):
            check_and_record("A", limit=3, window_seconds=60.0)

        allowed, _ = check_and_record("A", limit=3, window_seconds=60.0)
        assert allowed is False

        # Key B has its own independent counter.
        allowed, _ = check_and_record("B", limit=3, window_seconds=60.0)
        assert allowed is True

    def test_window_expiry_restores_access(self, monkeypatch):
        import backend.core.rate_limit as rl

        fake_now = 0.0
        monkeypatch.setattr(time, "monotonic", lambda: fake_now)

        for _ in range(3):
            rl.check_and_record("key6", limit=3, window_seconds=10.0)

        allowed, _ = rl.check_and_record("key6", limit=3, window_seconds=10.0)
        assert allowed is False

        fake_now = 10.01  # all three original timestamps are now outside the window
        allowed, _ = rl.check_and_record("key6", limit=3, window_seconds=10.0)
        assert allowed is True


class TestEnforce:
    def test_within_limit_does_not_raise(self):
        from backend.core.rate_limit import enforce

        for _ in range(2):
            enforce("bucket", "1.2.3.4", limit=3, window_seconds=60.0)

    def test_over_limit_raises_429_with_retry_after_header(self):
        from fastapi import HTTPException
        from backend.core.rate_limit import enforce

        for _ in range(3):
            enforce("ebucket", "1.2.3.4", limit=3, window_seconds=60.0)

        with pytest.raises(HTTPException) as exc_info:
            enforce("ebucket", "1.2.3.4", limit=3, window_seconds=60.0)

        exc = exc_info.value
        assert exc.status_code == 429
        assert "Retry-After" in exc.headers
        # Header is int(retry_after)+1, so always >= 1
        assert int(exc.headers["Retry-After"]) >= 1

    def test_bucket_and_ip_form_composite_key(self):
        from backend.core.rate_limit import enforce

        for _ in range(3):
            enforce("shared", "1.1.1.1", limit=3, window_seconds=60.0)

        # Exhausted for 1.1.1.1 but 2.2.2.2 has its own independent slot.
        enforce("shared", "2.2.2.2", limit=3, window_seconds=60.0)


class TestSweep:
    def test_expired_keys_are_removed_after_sweep_interval(self, monkeypatch):
        import backend.core.rate_limit as rl

        fake_now = 0.0
        monkeypatch.setattr(time, "monotonic", lambda: fake_now)

        rl.check_and_record("old_key", limit=5, window_seconds=10.0)
        assert "old_key" in rl._attempts

        # Advance past both the window (10s) and the sweep interval (60s).
        fake_now = 71.0
        rl.check_and_record("trigger", limit=5, window_seconds=5.0)

        assert "old_key" not in rl._attempts

    def test_keys_within_their_window_survive_sweep(self, monkeypatch):
        import backend.core.rate_limit as rl

        fake_now = 0.0
        monkeypatch.setattr(time, "monotonic", lambda: fake_now)

        rl.check_and_record("live_key", limit=5, window_seconds=120.0)

        # Past the sweep interval but well within the 120s window.
        fake_now = 61.0
        rl.check_and_record("trigger", limit=5, window_seconds=5.0)

        assert "live_key" in rl._attempts

    def test_sweep_does_not_run_before_interval_elapses(self, monkeypatch):
        """Keys that have outlived their window survive in the dict until
        the 60-second sweep throttle elapses, per-call pruning alone doesn't
        remove them when no call for *that* key arrives."""
        import backend.core.rate_limit as rl

        fake_now = 0.0
        monkeypatch.setattr(time, "monotonic", lambda: fake_now)

        rl.check_and_record("stale_key", limit=5, window_seconds=5.0)

        # At t=50: key has logically expired (50 > 0+5) but sweep hasn't fired
        # yet (50 - 0 < 60), so it still occupies the dict.
        fake_now = 50.0
        rl.check_and_record("trigger", limit=5, window_seconds=5.0)
        assert "stale_key" in rl._attempts

        # At t=61: sweep interval elapsed → sweep fires → stale_key removed.
        fake_now = 61.0
        rl.check_and_record("trigger", limit=5, window_seconds=5.0)
        assert "stale_key" not in rl._attempts
