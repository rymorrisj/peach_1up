from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Retention window -> age past which launch history rows are pruned. "never" maps
# to None (no pruning). Keep the keys in sync with
# models/settings.py LaunchHistoryRetention.
_RETENTION_WINDOWS: dict[str, timedelta | None] = {
    "never": None,
    "1_week": timedelta(weeks=1),
    "1_month": timedelta(days=30),
    "6_months": timedelta(days=182),
}


def scope_launch_query(q, active_user):
    """Restrict a LaunchHistory query to rows *active_user* may read.

    Owner/admin see everything. Every other user sees launches that are not
    attributable to a *different* user: rows with no launching profile, rows
    whose profile has no owner (bundled/shared profiles), and rows whose profile
    they own. This mirrors coordinator.stop_launch's ownership check and closes
    P1-S1 (one user seeing another identified user's launch activity) without
    hiding the shared-profile launches the history UI depends on.
    """
    if active_user.is_owner or active_user.is_admin:
        return q
    from sqlalchemy import or_, select
    from backend.models import LaunchHistory
    from backend.models.profile import ProfileItem

    visible_profile_ids = select(ProfileItem.id).where(
        or_(
            ProfileItem.user_item_id.is_(None),
            ProfileItem.user_item_id == active_user.id,
        )
    )
    return q.filter(
        or_(
            LaunchHistory.profile_item_id.is_(None),
            LaunchHistory.profile_item_id.in_(visible_profile_ids),
        )
    )


_LAUNCH_TARGET_COLUMNS = (
    ("game_item_bundle", "game_item_bundle_id"),
    ("app_item_bundle", "app_item_bundle_id"),
)


def filter_visible_launch_targets(q, active_user, db):
    """Drop LaunchHistory rows whose game or app target *active_user* cannot
    see, so a hidden title's launch activity is indistinguishable from none.

    Separate from scope_launch_query on purpose: that one is attribution
    (owner/admin bypass), this is content visibility, where only the owner
    bypasses, matching every get_filtered_* helper. Environment launches
    carry no visibility rule and always pass.
    """
    if active_user.is_owner:
        return q
    from sqlalchemy import or_
    from backend.core.dependencies import get_filtered_entity_query
    from backend.models import LaunchHistory
    from backend.models.app import AppItemBundle
    from backend.models.game import GameItemBundle

    models = {"game_item_bundle": GameItemBundle, "app_item_bundle": AppItemBundle}
    for entity_type, column_name in _LAUNCH_TARGET_COLUMNS:
        column = getattr(LaunchHistory, column_name)
        visible_ids = (
            get_filtered_entity_query(entity_type, active_user, db)
            .with_entities(models[entity_type].id)
            .subquery()
        )
        q = q.filter(or_(column.is_(None), column.in_(visible_ids.select())))
    return q


def launch_target_visible(record, active_user, db) -> bool:
    """Record-level counterpart to filter_visible_launch_targets."""
    if active_user.is_owner:
        return True
    from fastapi import HTTPException
    from backend.core.dependencies import get_filtered_entity

    for entity_type, column_name in _LAUNCH_TARGET_COLUMNS:
        target_id = getattr(record, column_name)
        if target_id is None:
            continue
        try:
            get_filtered_entity(entity_type, target_id, active_user, db)
        except HTTPException as exc:
            if exc.status_code == 404:
                return False
            raise
    return True


def user_can_view_launch(record, active_user, db) -> bool:
    """Record-level counterpart to scope_launch_query, for single-row reads."""
    if active_user.is_owner or active_user.is_admin:
        return True
    if record.profile_item_id is None:
        return True
    from backend.models.profile import ProfileItem
    prof = db.get(ProfileItem, record.profile_item_id)
    return prof is None or prof.user_item_id is None or prof.user_item_id == active_user.id


def prune_launch_history() -> int:
    """Delete launch history older than the configured retention window.

    Reads the launch_history_retention app setting; "never" (the default) is a
    no-op. Self-contained (opens its own session, same as write_session_ends) so
    the background sweep can call it directly. Returns the number of rows deleted.
    """
    from backend.core.settings import get_settings
    from backend.core.database import get_engine
    from backend.models import LaunchHistory
    from sqlalchemy.orm import sessionmaker

    window = _RETENTION_WINDOWS.get(get_settings().get("launch_history_retention", "never"))
    if window is None:
        return 0
    cutoff = datetime.now(timezone.utc) - window
    session_factory = sessionmaker(bind=get_engine())
    with session_factory() as db:
        deleted = (
            db.query(LaunchHistory)
            .filter(LaunchHistory.started_at < cutoff)
            .delete(synchronize_session=False)
        )
        if deleted:
            db.commit()
    return deleted


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
                    # than coercing an unpolled handle to -1, coordinator.py already
                    # writes real -1s for genuine aborts (timeout, crash, stop_launch),
                    # so collapsing "never confirmed" into the same value would make a
                    # clean-but-unpolled exit indistinguishable from a real abort in
                    # history. The frontend already treats a null exit_code as non-error
                    # (LaunchHistory.tsx: `exit_code != null && exit_code !== 0`).
                    history.exit_code = rc
        db.commit()
