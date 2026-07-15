import asyncio
import time

from backend.core import process_registry
from backend.core.logger import get_logger
from backend.service.launch.history import (
    prune_launch_history as _prune_launch_history,
    write_session_ends as _write_session_ends,
)

logger = get_logger(__name__)

# The monitor loop wakes every 5s for process cleanup, but the launch-history
# retention sweep only needs to run coarsely (windows are days+). Gate it to run
# at most hourly, and once shortly after startup (last_prune starts at 0).
_RETENTION_SWEEP_INTERVAL_S = 3600


async def _process_monitor_loop() -> None:
    from backend.service.launch.monitor import poll_short_lived
    last_prune = 0.0
    while True:
        try:
            await asyncio.sleep(5)
            exited = process_registry.cleanup_exited()
            if exited:
                await asyncio.to_thread(_write_session_ends, exited)
            await asyncio.to_thread(poll_short_lived)
            now = time.monotonic()
            if now - last_prune >= _RETENTION_SWEEP_INTERVAL_S:
                last_prune = now
                deleted = await asyncio.to_thread(_prune_launch_history)
                if deleted:
                    logger.info("Retention sweep deleted %d launch history row(s)", deleted)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Process monitor iteration failed (will retry): %s", exc)
