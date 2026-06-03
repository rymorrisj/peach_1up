from sqlalchemy.orm import Session


def defaults_for_era(era_slug: str) -> tuple[str | None, str | None]:
    """Return (emulator_slug, profile_era) for a known era, or (None, None)."""
    match era_slug:
        case "dos":       return ("dosbox-x", "dos")
        case "win31":     return ("dosbox-x", "win31")
        case "win95":     return ("86box", "win95")
        case "win98":     return ("86box", "win98")
        case "winxp":     return ("86box", "winxp")
        case "ps1":       return ("duckstation", "ps1")
        case "ps2":       return ("pcsx2", "ps2")
        case "xbox":      return ("xemu", "xbox")
        case "nes":       return ("mesen", "nes")
        case "snes":      return ("mesen", "snes")
        case "n64":       return ("project64", "n64")
        case "dreamcast": return ("flycast", "dreamcast")
        case _:           return (None, None)


def lookup_platform_and_profile(
    emulator_slug: str,
    profile_era: str,
    db: Session,
) -> tuple[int | None, int | None]:
    """Return (platform_id, profile_id) for the given emulator and era, querying system records only."""
    from backend.models.platform import Platform
    from backend.models.profile import Profile

    platform = (
        db.query(Platform)
        .filter(Platform.emulator_slug == emulator_slug, Platform.is_system == True)
        .first()
    )
    profile = (
        db.query(Profile)
        .filter(Profile.era == profile_era)
        .first()
    )
    return (platform.id if platform else None, profile.id if profile else None)
