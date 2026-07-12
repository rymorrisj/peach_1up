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
    software_collection_id: int | None
    profile_item_id: int | None
    app_collection_id: int | None = None
    launch_history_id: int | None = None
    emulator_slug: str | None = None
    user_item_id: int | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class Reservation:
    """Token returned by try_reserve(); pass to release() exactly once."""
    profile_item_id: int | None
    emulator_scope: tuple[str, int | None] | None


_registry: dict[int, ProcessEntry] = {}
_pending_profiles: set[int] = set()
_pending_emulator_scopes: set[tuple[str, int | None]] = set()
_lock = threading.Lock()


def register(pid: int, entry: ProcessEntry) -> None:
    with _lock:
        try:
            _registry[pid] = entry
        except Exception as exc:
            logger.error(
                "Failed to register process pid=%d software_collection_id=%s profile_item_id=%s: %s",
                pid, entry.software_collection_id, entry.profile_item_id, exc,
            )
            raise


def get(pid: int) -> ProcessEntry | None:
    with _lock:
        return _registry.get(pid)


def get_all() -> dict[int, ProcessEntry]:
    with _lock:
        return dict(_registry)


def try_reserve(profile_item_id: int | None, emulator_slug: str | None, user_item_id: int | None) -> Reservation | None:
    """Atomically check both launch-guard keys against current state and reserve them.

    Closes the TOCTOU window between "is anything already running for this
    key" and the new process landing in the registry: the check and the
    reservation happen under the same lock, so two concurrent callers for the
    same key can never both succeed. Returns None if either key (profile_item_id,
    or the (emulator_slug, user_item_id) pair) is already active or pending.
    Callers must call release() exactly once, regardless of outcome.
    """
    emulator_scope = (emulator_slug, user_item_id) if emulator_slug is not None else None
    with _lock:
        if profile_item_id is not None:
            active_profiles = {e.profile_item_id for e in _registry.values() if e.profile_item_id is not None}
            if profile_item_id in active_profiles or profile_item_id in _pending_profiles:
                return None
        if emulator_scope is not None:
            active_scopes = {
                (e.emulator_slug, e.user_item_id) for e in _registry.values() if e.emulator_slug is not None
            }
            if emulator_scope in active_scopes or emulator_scope in _pending_emulator_scopes:
                return None
        if profile_item_id is not None:
            _pending_profiles.add(profile_item_id)
        if emulator_scope is not None:
            _pending_emulator_scopes.add(emulator_scope)
        return Reservation(profile_item_id=profile_item_id, emulator_scope=emulator_scope)


def release(reservation: Reservation | None) -> None:
    """Release a reservation from try_reserve(). Safe to call once registration has
    superseded it -- it only clears the pending marker, never touches _registry."""
    if reservation is None:
        return
    with _lock:
        if reservation.profile_item_id is not None:
            _pending_profiles.discard(reservation.profile_item_id)
        if reservation.emulator_scope is not None:
            _pending_emulator_scopes.discard(reservation.emulator_scope)


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
                entry.job_handle.teardown()
            except Exception as exc:
                logger.warning("Failed to terminate job handle for pid=%d: %s", pid, exc)
        return True


def cleanup_exited() -> list[tuple[int, ProcessEntry]]:
    removed = []
    with _lock:
        for pid, entry in list(_registry.items()):
            try:
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
                            logger.warning("Failed to close job handle for pid=%d: %s", pid, exc)
            except Exception as exc:
                logger.warning("Failed to check/cleanup process pid=%d: %s", pid, exc)
    return removed


def count() -> int:
    with _lock:
        return len(_registry)
