import asyncio
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ProcessEntry:
    process_handle: Any
    job_handle: Any | None
    library_item_id: int | None
    profile_id: int | None
    launch_history_id: int | None = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    target_type: str = "library_item"
    target_id: int | None = None
    job_isolated: bool = False


_registry: dict[int, ProcessEntry] = {}
_lock = threading.Lock()

# Subscriber queues for SSE consumers
_subscribers: list[asyncio.Queue] = []
_sub_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    with _sub_lock:
        _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    with _sub_lock:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


def _notify(event: dict) -> None:
    if not _subscribers:
        return
    with _sub_lock:
        subs = list(_subscribers)
    if not subs:
        return
    lp = _loop
    if lp is None or not lp.is_running():
        return
    for q in subs:
        try:
            lp.call_soon_threadsafe(q.put_nowait, event)
        except Exception:
            pass


def register(pid: int, entry: ProcessEntry) -> None:
    with _lock:
        _registry[pid] = entry
    _notify({"type": "started", "pid": pid, "entry": entry})


def get(pid: int) -> ProcessEntry | None:
    with _lock:
        return _registry.get(pid)


def get_all() -> dict[int, ProcessEntry]:
    with _lock:
        return dict(_registry)


def terminate(pid: int) -> bool:
    with _lock:
        entry = _registry.get(pid)
        if entry is None:
            return False
        try:
            proc = entry.process_handle
            if proc is not None and proc.poll() is None:
                proc.terminate()
        except Exception:
            pass
        _registry.pop(pid, None)
        if entry.job_handle is not None:
            try:
                entry.job_handle.terminate_all()
            except Exception:
                pass
    _notify({"type": "cleaned", "pid": pid, "entry": entry, "exit_code": -15})
    return True


def cleanup_exited() -> list[tuple[int, ProcessEntry]]:
    removed = []
    with _lock:
        for pid, entry in list(_registry.items()):
            proc = entry.process_handle
            poll_result = proc.poll() if proc is not None else "no-handle"
            reaped = proc is not None and poll_result is not None and poll_result != "no-handle"
            logger.debug(
                "cleanup_exited: pid=%d poll=%s reaped=%s",
                pid, poll_result, reaped,
            )
            if reaped:
                _registry.pop(pid)
                exit_code = poll_result if isinstance(poll_result, int) else -1
                removed.append((pid, entry))
                if entry.job_handle is not None:
                    try:
                        entry.job_handle.close()
                    except Exception:
                        pass
                _notify({"type": "exited", "pid": pid, "entry": entry, "exit_code": exit_code})
    return removed


def count() -> int:
    with _lock:
        return len(_registry)
