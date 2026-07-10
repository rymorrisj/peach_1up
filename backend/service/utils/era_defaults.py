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
    """Return (environment_id, profile_id) for the given emulator and era, querying system records only."""
    from backend.models.environment import Environment
    from backend.models.profile import Profile

    platform = (
        db.query(Environment)
        .filter(Environment.emulator_slug == emulator_slug, Environment.is_system == True)
        .first()
    )
    profile = (
        db.query(Profile)
        .filter(Profile.era == profile_era)
        .first()
    )
    return (platform.id if platform else None, profile.id if profile else None)


def lookup_system_environment_by_era(era: str, db: Session):
    """Return the is_system Environment whose era matches *era*, or None.

    Runtime fallback for a PC SoftwareCollection whose environment_id is still
    null (doc 02 A5, transition window before existing rows are backfilled).
    Era-matched rather than emulator_slug-matched (unlike
    lookup_environment_and_profile above) because the caller already knows the
    collection's era and has no emulator_slug to key off.
    """
    from backend.models.environment import Environment

    return (
        db.query(Environment)
        .filter(Environment.era == era, Environment.is_system == True)
        .first()
    )


def system_environment_eras(eras: set[str], db: Session) -> set[str]:
    """Batch form of lookup_system_environment_by_era: which of *eras* have a
    matching is_system Environment. One query for N collections instead of N
    queries -- used by the read-time launch-blocked gate (collections_to_read_bulk)."""
    from backend.models.environment import Environment

    if not eras:
        return set()
    rows = (
        db.query(Environment.era)
        .filter(Environment.era.in_(eras), Environment.is_system == True)
        .all()
    )
    return {row[0] for row in rows}
