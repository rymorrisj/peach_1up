from sqlalchemy.orm import Session

from backend.constants_generated import ERA_BACKENDS

# Eras served by DOSBox-X (per-item FAT16 C: drive, not a shared working image).
DOS_WIN_ERAS: frozenset[str] = frozenset({"dos"})


def defaults_for_era(era_slug: str) -> tuple[str | None, str | None]:
    """Return (emulator_slug, profile_era) for a known era, or (None, None)."""
    emulator_slug = ERA_BACKENDS.get(era_slug)
    if emulator_slug is None:
        return (None, None)
    return (emulator_slug, era_slug)


def lookup_environment_and_profile(
    emulator_slug: str,
    profile_era: str,
    db: Session,
) -> tuple[int | None, int | None]:
    """Return (environment_item_id, profile_item_id) for the given emulator and era, querying system records only."""
    from backend.models.environment import EnvironmentItem
    from backend.models.profile import ProfileItem

    platform = (
        db.query(EnvironmentItem)
        .filter(EnvironmentItem.emulator_slug == emulator_slug, EnvironmentItem.is_system == True)
        .first()
    )
    profile = (
        db.query(ProfileItem)
        .filter(ProfileItem.era == profile_era)
        .first()
    )
    return (platform.id if platform else None, profile.id if profile else None)


def environment_is_installed(env) -> bool:
    """Whether *env* (an EnvironmentItem) satisfies the "OS installed" gate.

    Reads the pre-existing installed_at timestamp (set by the "Mark as
    Installed" action in EnvironmentCard.tsx) rather than a new dedicated
    boolean -- installed_at already recorded exactly this concept before this
    change, and adding a second field for the same fact would recreate the
    same kind of duplicate-state drift this task exists to fix.

    DOS/DOSBox-X environments have no install step (DOSBox-X boots straight
    to a DOS prompt against the per-item drive), so they are always treated
    as installed regardless of installed_at -- checked here, at read time,
    rather than forced true at creation, so the rule can't drift if an
    environment's era is ever changed after creation.
    """
    if env.era in DOS_WIN_ERAS:
        return True
    return env.installed_at is not None


def resolve_environment_for_launch_gate(environment_item_id: int | None, era: str, db: Session):
    """Resolve the Environment compute_launch_blocked_reason should gate
    against for a single item: environment_item_id if set, else the
    era-matched is_system fallback. Mirrors
    coordinator._resolve_environment_for_pc_entity exactly, so the read-time
    gate and the actual launch-time resolution can never disagree."""
    from backend.models.environment import EnvironmentItem

    if environment_item_id is not None:
        return db.get(EnvironmentItem, environment_item_id)
    return lookup_system_environment_by_era(era, db)


def resolve_environments_for_launch_gate_bulk(items: list, db: Session) -> dict[int, object]:
    """Batch form of resolve_environment_for_launch_gate for read-bulk builders.

    *items* is any list of objects with .id, .era, .environment_item_id
    (GameItemBundle or AppItemBundle rows). Returns {item.id: EnvironmentItem|None}
    in two queries total instead of one per item.
    """
    from backend.models.environment import EnvironmentItem

    if not items:
        return {}

    explicit_ids = {i.environment_item_id for i in items if i.environment_item_id is not None}
    fallback_eras = {i.era for i in items if i.environment_item_id is None}

    by_id: dict[int, EnvironmentItem] = {}
    if explicit_ids:
        for row in db.query(EnvironmentItem).filter(EnvironmentItem.id.in_(explicit_ids)).all():
            by_id[row.id] = row

    by_era: dict[str, EnvironmentItem] = {}
    if fallback_eras:
        for row in (
            db.query(EnvironmentItem)
            .filter(EnvironmentItem.era.in_(fallback_eras), EnvironmentItem.is_system == True)
            .all()
        ):
            by_era[row.era] = row

    result: dict[int, EnvironmentItem | None] = {}
    for i in items:
        if i.environment_item_id is not None:
            result[i.id] = by_id.get(i.environment_item_id)
        else:
            result[i.id] = by_era.get(i.era)
    return result


def lookup_system_environment_by_era(era: str, db: Session):
    """Return the is_system Environment whose era matches *era*, or None.

    Runtime fallback for a PC SoftwareCollection whose environment_item_id is still
    null (doc 02 A5, transition window before existing rows are backfilled).
    Era-matched rather than emulator_slug-matched (unlike
    lookup_environment_and_profile above) because the caller already knows the
    collection's era and has no emulator_slug to key off.
    """
    from backend.models.environment import EnvironmentItem

    return (
        db.query(EnvironmentItem)
        .filter(EnvironmentItem.era == era, EnvironmentItem.is_system == True)
        .first()
    )


def compute_launch_blocked_reason(
    *,
    is_pc: bool,
    era: str,
    profile_item_id: int | None,
    environment,
) -> str | None:
    """Read-time mirror of the coordinator's precomputable pre-launch gates.

    Shared by both Game (backend/models/game.py) and App (backend/models/app.py)
    read builders so the two domains never drift. Checks the gates in the exact
    order coordinator._launch_entity enforces them:

    1. Profile is resolved first for every item, pc or console
       (coordinator._resolve_profile_for_item). An item with no profile_item_id
       would 422 "No profile associated" -> "no_profile".
    2. Environment is a PC-only gate resolved after the profile
       (coordinator._resolve_environment_for_pc_entity). *environment* is the
       already-resolved EnvironmentItem (or None) from
       resolve_environment_for_launch_gate / resolve_environments_for_launch_gate_bulk
       -- environment_item_id if set, else the era-matched is_system fallback,
       exactly mirroring the coordinator's own resolution order. No resolvable
       Environment at all -> "no_environment".
    3. Era match is the authoritative gate, added after a real incident where a
       win98 item was bound to a win95-era Environment and silently launched
       because the bound profile happened to carry the correct backend
       (86Box). A resolved Environment whose era does not match the item's
       era -> "environment_era_mismatch", checked before is_installed so the
       more specific, more dangerous mismatch is reported first.
    4. is_installed gates Win9x/WinXp Environments that have never had the OS
       installed inside them (DOS/DOSBox-X environments always pass this,
       see environment_is_installed) -> "environment_not_installed".

    Returns the reason for the first gate that would block, or None if the item
    clears all of them. These gates are determinable from stored state; the
    coordinator's other hard blocks (emulator not installed, media resolution,
    provisioning, 8.3 path, concurrency, spawn/timeout/crash) are runtime
    conditions that cannot be known without attempting the launch.
    """
    if profile_item_id is None:
        return "no_profile"
    if not is_pc:
        return None
    if environment is None:
        return "no_environment"
    if environment.era != era:
        return "environment_era_mismatch"
    if not environment_is_installed(environment):
        return "environment_not_installed"
    return None
