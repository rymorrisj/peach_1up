import threading
import time

_lock = threading.Lock()
_attempts: dict[str, list[float]] = {}
_windows: dict[str, float] = {}

# Entries are swept lazily on each call rather than via a background task —
# growth only happens while calls are coming in, so checking the clock on
# every call (cheap) is enough to keep the dict bounded under sustained or
# distributed attack without adding an asyncio loop just for this.
_SWEEP_INTERVAL_SECONDS = 60.0
_last_sweep = 0.0


def check_and_record(key: str, limit: int, window_seconds: float) -> tuple[bool, float]:
    """Sliding-window rate limit keyed by an arbitrary string (e.g. "route:ip").

    Returns (allowed, retry_after_seconds). Only records the attempt when it
    is allowed, a client hammering the endpoint past the limit doesn't keep
    pushing the window forward, so the limit resets `window_seconds` after the
    oldest *counted* attempt rather than extending indefinitely under load.

    In-memory only (lost on restart), matching the existing install_registry
    / process_registry pattern, acceptable here since the goal is bounding
    brute-force rate, not a durable audit trail.
    """
    now = time.monotonic()
    with _lock:
        _sweep_expired_locked(now)
        cutoff = now - window_seconds
        timestamps = [t for t in _attempts.get(key, ()) if t > cutoff]
        _windows[key] = window_seconds
        if len(timestamps) >= limit:
            _attempts[key] = timestamps
            retry_after = timestamps[0] + window_seconds - now
            return False, max(retry_after, 0.0)
        timestamps.append(now)
        _attempts[key] = timestamps
        return True, 0.0


def enforce(bucket: str, ip: str, limit: int, window_seconds: float) -> None:
    """check_and_record + raise HTTPException(429) with Retry-After when the
    caller (keyed ``bucket:ip``) is over the limit. Shared by the library and
    uploads routers so the 429 shape stays identical."""
    from fastapi import HTTPException

    allowed, retry_after = check_and_record(f"{bucket}:{ip}", limit, window_seconds)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests, please slow down.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


def _sweep_expired_locked(now: float) -> None:
    """Drop keys whose window has fully elapsed since their last attempt.

    Must be called with `_lock` held. Runs at most once per
    `_SWEEP_INTERVAL_SECONDS` so it stays cheap on the hot path while still
    bounding dict growth under a distributed attack (many unique keys, each
    queried once) where per-key pruning alone never removes the key.
    """
    global _last_sweep
    if now - _last_sweep < _SWEEP_INTERVAL_SECONDS:
        return
    _last_sweep = now
    stale_keys = [
        key
        for key, timestamps in _attempts.items()
        if not timestamps or timestamps[-1] <= now - _windows.get(key, 0.0)
    ]
    for key in stale_keys:
        _attempts.pop(key, None)
        _windows.pop(key, None)
