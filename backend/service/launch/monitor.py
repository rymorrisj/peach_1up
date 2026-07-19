"""Short-lived launch detection.

Fires for every non-app software launch (across all eras, not just DOS)
within the 3s crash-review window after launch. Replaces the per-launch
daemon thread. Instead of spawning a thread that sleeps for 3 seconds per
launch, `register_short_lived_check` stores the process handle, and
`poll_short_lived` is called by the existing _process_monitor_loop in
core/lifespan.py on every iteration.

Detection latency: bounded by monitor loop poll interval (5 s) plus
_SHORT_LIVED_TIMEOUT. A process that exits at t=1 s is detected at the
next poll (up to t=5 s). The 'lifetime' value logged reflects the gap
between launch and detection, not true exit time.
"""

from __future__ import annotations

import threading
import time

from backend.core.logger import get_logger

logger = get_logger(__name__)

_SHORT_LIVED_TIMEOUT = 3.0

# collection_id -> (proc, launch_time_monotonic, era)
_pending: dict[int, tuple[object, float, str | None]] = {}
_lock = threading.Lock()


def register_short_lived_check(collection_id: int, proc: object, launch_time: float, era: str | None = None) -> None:
    """Register a newly-launched software process for short-lived exit detection."""
    with _lock:
        _pending[collection_id] = (proc, launch_time, era)


def poll_short_lived() -> None:
    """Check all pending short-lived entries. Called from the monitor loop."""
    now = time.monotonic()
    to_flag: list[tuple[int, int | None, float, str | None]] = []
    to_remove: list[int] = []

    with _lock:
        for collection_id, (proc, launch_time, era) in list(_pending.items()):
            exit_code = proc.poll() if hasattr(proc, "poll") else None
            if exit_code is not None:
                to_flag.append((collection_id, exit_code, now - launch_time, era))
                to_remove.append(collection_id)
            elif now - launch_time > _SHORT_LIVED_TIMEOUT:
                to_remove.append(collection_id)
        for collection_id in to_remove:
            _pending.pop(collection_id, None)

    for collection_id, exit_code, lifetime, era in to_flag:
        logger.warning(
            "Short-lived %s launch detected: collection_id=%d exit_code=%r lifetime=%.2fs, flagging for review",
            era or "software",
            collection_id,
            exit_code,
            lifetime,
        )
        _flag_short_lived_item(collection_id)


def _flag_short_lived_item(collection_id: int) -> None:
    from backend.core.database import get_engine
    from backend.models import GameItemBundle
    from sqlalchemy.orm import Session

    try:
        with Session(get_engine()) as db:
            collection = db.get(GameItemBundle, collection_id)
            if collection is not None:
                collection.launch_review_flagged = True
                db.commit()
    except Exception as exc:
        logger.error("Failed to set launch_review_flagged for collection %d: %s", collection_id, exc, exc_info=True)
        raise
