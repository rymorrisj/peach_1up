import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ProcessEntry:
    process_handle: Any
    job_handle: Any | None
    library_item_id: int
    profile_id: int | None
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
        return True


def cleanup_exited() -> list[int]:
    removed = []
    with _lock:
        for pid, entry in list(_registry.items()):
            proc = entry.process_handle
            if proc is not None and proc.poll() is not None:
                _registry.pop(pid)
                removed.append(pid)
    return removed


def count() -> int:
    with _lock:
        return len(_registry)
