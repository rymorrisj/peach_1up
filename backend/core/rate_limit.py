import threading
import time

_lock = threading.Lock()
_attempts: dict[str, list[float]] = {}


def check_and_record(key: str, limit: int, window_seconds: float) -> tuple[bool, float]:
    """Sliding-window rate limit keyed by an arbitrary string (e.g. "route:ip").

    Returns (allowed, retry_after_seconds). Only records the attempt when it
    is allowed — a client hammering the endpoint past the limit doesn't keep
    pushing the window forward, so the limit resets `window_seconds` after the
    oldest *counted* attempt rather than extending indefinitely under load.

    In-memory only (lost on restart), matching the existing install_registry
    / process_registry pattern — acceptable here since the goal is bounding
    brute-force rate, not a durable audit trail.
    """
    now = time.monotonic()
    with _lock:
        cutoff = now - window_seconds
        timestamps = [t for t in _attempts.get(key, ()) if t > cutoff]
        if len(timestamps) >= limit:
            _attempts[key] = timestamps
            retry_after = timestamps[0] + window_seconds - now
            return False, max(retry_after, 0.0)
        timestamps.append(now)
        _attempts[key] = timestamps
        return True, 0.0
