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
                    history.exit_code = rc if rc is not None else -1
        db.commit()
