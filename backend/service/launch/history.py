from __future__ import annotations

from datetime import datetime, timezone


def write_session_ends(exited: list, exit_code_override: int | None = None) -> None:
    if not exited:
        return
    from backend.core.database import get_engine
    from backend.models import LaunchHistory
    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(bind=get_engine())
    with session_factory() as db:
        for _pid, entry in exited:
            if entry.launch_history_id is None:
                continue
            history = db.get(LaunchHistory, entry.launch_history_id)
            if history and history.ended_at is None:
                history.ended_at = datetime.now(timezone.utc)
                if exit_code_override is not None:
                    history.exit_code = exit_code_override
                else:
                    rc = getattr(entry.process_handle, "returncode", None) if entry.process_handle else None
                    # Leave exit_code as None (the column's default/unset state) rather
                    # than coercing an unpolled handle to -1 -- coordinator.py already
                    # writes real -1s for genuine aborts (timeout, crash, stop_launch),
                    # so collapsing "never confirmed" into the same value would make a
                    # clean-but-unpolled exit indistinguishable from a real abort in
                    # history. The frontend already treats a null exit_code as non-error
                    # (LaunchHistory.tsx: `exit_code != null && exit_code !== 0`).
                    history.exit_code = rc
        db.commit()
