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
    environment_item_id: int | None,
    system_eras: set[str],
) -> str | None:
    """Read-time mirror of the coordinator's precomputable pre-launch gates.

    Shared by both Game (backend/models/game.py) and App (backend/models/app.py)
    read builders so the two domains never drift. Checks the gates in the exact
    order coordinator._launch_entity enforces them:

    1. Profile is resolved first for every item, pc or console
       (coordinator._resolve_profile_for_item). An item with no profile_item_id
       would 422 "No profile associated" -> "no_profile".
    2. Environment is a PC-only gate resolved after the profile
       (coordinator._resolve_environment_for_pc_entity). A PC item with neither
       its own environment_item_id nor an era-matched is_system Environment
       fallback would 422 -> "no_environment". Console items never touch
       Environment, so they can only be blocked by the profile gate.

    Returns the reason for the first gate that would block, or None if the item
    clears both. Only these two gates are determinable from stored state; the
    coordinator's other hard blocks (emulator not installed, media resolution,
    provisioning, 8.3 path, concurrency, spawn/timeout/crash) are runtime
    conditions that cannot be known without attempting the launch. *system_eras*
    is the set of eras that have a matching is_system Environment, computed once
    by system_environment_eras for the batch.
    """
    if profile_item_id is None:
        return "no_profile"
    if not is_pc:
        return None
    if environment_item_id is not None:
        return None
    if era in system_eras:
        return None
    return "no_environment"


def system_environment_eras(eras: set[str], db: Session) -> set[str]:
    """Batch form of lookup_system_environment_by_era: which of *eras* have a
    matching is_system EnvironmentItem. One query for N collections instead of N
    queries -- used by the read-time launch-blocked gate (collections_to_read_bulk)."""
    from backend.models.environment import EnvironmentItem

    if not eras:
        return set()
    rows = (
        db.query(EnvironmentItem.era)
        .filter(EnvironmentItem.era.in_(eras), EnvironmentItem.is_system == True)
        .all()
    )
    return {row[0] for row in rows}
