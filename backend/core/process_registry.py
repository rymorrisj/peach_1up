import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ProcessEntry:
    process_handle: Any
    job_handle: Any | None
    library_item_id: int | None
    profile_id: int | None
    launch_history_id: int | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


_registry: dict[int, ProcessEntry] = {}
_lock = threading.Lock()


def register(pid: int, entry: ProcessEntry) -> None:
    with _lock:
        try:
            _registry[pid] = entry
        except Exception as exc:
            logger.error(
                "Failed to register process pid=%d library_item_id=%s profile_id=%s: %s",
                pid, entry.library_item_id, entry.profile_id, exc,
            )
            raise


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
        except Exception as exc:
            logger.warning("Failed to terminate process pid=%d: %s", pid, exc)
        _registry.pop(pid, None)
        if entry.job_handle is not None:
            try:
                entry.job_handle.terminate_all()
            except Exception as exc:
                logger.warning("Failed to terminate job handle for pid=%d: %s", pid, exc)
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
                    except Exception as exc:
                        logger.error("Failed to close job handle for pid=%d: %s", pid, exc)
    return removed


def count() -> int:
    with _lock:
        return len(_registry)
