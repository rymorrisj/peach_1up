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
