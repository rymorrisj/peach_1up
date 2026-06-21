import asyncio

from backend.core import process_registry
from backend.core.logger import get_logger
from backend.service.launch.history import write_session_ends as _write_session_ends

logger = get_logger(__name__)


async def _process_monitor_loop() -> None:
    from backend.service.launch.monitor import poll_short_lived
    while True:
        try:
            await asyncio.sleep(5)
            exited = process_registry.cleanup_exited()
            if exited:
                await asyncio.to_thread(_write_session_ends, exited)
            await asyncio.to_thread(poll_short_lived)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Process monitor iteration failed (will retry): %s", exc)
