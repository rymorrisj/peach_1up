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
    library_item_id: int
    profile_id: int | None
    launch_history_id: int | None = None
    started_at: datetime = field(default_factory=datetime.utcnow)


_registry: dict[int, ProcessEntry] = {}
_lock = threading.Lock()


def register(pid: int, entry: ProcessEntry) -> None:
    with _lock:
        _registry[pid] = entry


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
                removed.append((pid, entry))
                if entry.job_handle is not None:
                    try:
                        entry.job_handle.close()
                    except Exception:
                        pass
    return removed


def count() -> int:
    with _lock:
        return len(_registry)
