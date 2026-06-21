import json

from backend.core.logger import get_logger

logger = get_logger(__name__)

_SYSTEM_PLATFORMS = [
    {
        "name": "DOSBox-X",
        "slug": "dosbox-x",
        "era": "dos",
        "emulator_slug": "dosbox-x",
        "is_system": True,
        "supported_eras": json.dumps(["dos", "win31"]),
        "download_url": "https://dosbox-x.com",
        "status": "unknown",
    },
    {
        "name": "86Box",
        "slug": "86box",
        "era": "win95",
        "emulator_slug": "86box",
        "is_system": True,
        "supported_eras": json.dumps(["win95", "win98", "winxp"]),
        "download_url": "https://86box.net",
        "status": "unknown",
    },
    {
        "name": "DuckStation",
        "slug": "duckstation",
        "era": "ps1",
        "emulator_slug": "duckstation",
        "is_system": True,
        "supported_eras": json.dumps(["ps1"]),
        "download_url": "https://www.duckstation.org",
        "status": "unknown",
    },
    {
        "name": "PCSX2",
        "slug": "pcsx2",
        "era": "ps2",
        "emulator_slug": "pcsx2",
        "is_system": True,
        "supported_eras": json.dumps(["ps2"]),
        "download_url": "https://pcsx2.net",
        "status": "unknown",
    },
    {
        "name": "Mesen (NES, SNES)",
        "slug": "mesen",
        "era": "nes",
        "emulator_slug": "mesen",
        "is_system": True,
        "supported_eras": json.dumps(["nes", "snes"]),
        "download_url": "https://www.mesen.ca",
        "status": "unknown",
    },
    {
        "name": "Project64",
        "slug": "project64",
        "era": "n64",
        "emulator_slug": "project64",
        "is_system": True,
        "supported_eras": json.dumps(["n64"]),
        "download_url": "https://www.pj64-emu.com",
        "status": "unknown",
    },
    {
        "name": "Flycast",
        "slug": "flycast",
        "era": "dreamcast",
        "emulator_slug": "flycast",
        "is_system": True,
        "supported_eras": json.dumps(["dreamcast"]),
        "download_url": "https://github.com/flyinghead/flycast",
        "status": "unknown",
    },
    {
        "name": "xemu",
        "slug": "xemu",
        "era": "xbox",
        "emulator_slug": "xemu",
        "is_system": True,
        "supported_eras": json.dumps(["xbox"]),
        "download_url": "https://xemu.app",
        "status": "unknown",
    },
]

_DEFAULT_PROFILES = [
    {"name": "DOS Default",     "slug": "dos-default",   "era": "dos",   "emulator_slug": "dosbox-x",   "is_bundled": True},
    {"name": "Win 3.1 Default", "slug": "win31-default", "era": "win31", "emulator_slug": "dosbox-x",   "is_bundled": True},
    {"name": "Win 95 Default",  "slug": "win95-compat",  "era": "win95", "emulator_slug": "86box",       "is_bundled": True},
    {"name": "Win 98 Default",  "slug": "win98-compat",  "era": "win98", "emulator_slug": "86box",       "is_bundled": True},
    {"name": "Win XP Default",  "slug": "winxp-default", "era": "winxp", "emulator_slug": "86box",       "is_bundled": True},
    {"name": "PS1 Default",     "slug": "ps1-default",   "era": "ps1",   "emulator_slug": "duckstation", "is_bundled": True},
    {"name": "PS2 Default",     "slug": "ps2-default",   "era": "ps2",   "emulator_slug": "pcsx2",       "is_bundled": True},
    {"name": "Xbox OG Default", "slug": "xbox-default",  "era": "xbox",  "emulator_slug": "xemu",        "is_bundled": True},
    {"name": "NES Default",     "slug": "nes-default",   "era": "nes",   "emulator_slug": "mesen",       "is_bundled": True},
    {"name": "SNES Default",    "slug": "snes-default",  "era": "snes",  "emulator_slug": "mesen",       "is_bundled": True},
    {"name": "N64 Default",        "slug": "n64-default",        "era": "n64",       "emulator_slug": "project64",   "is_bundled": True},
    {"name": "Dreamcast Default",  "slug": "dreamcast-default",  "era": "dreamcast", "emulator_slug": "flycast",     "is_bundled": True},
]


def _seed_system_platforms(db) -> bool:
    try:
        from backend.models import Platform
        added = 0
        for data in _SYSTEM_PLATFORMS:
            if not db.query(Platform).filter(Platform.slug == data["slug"]).first():
                db.add(Platform(**data))
                added += 1
        if added:
            db.flush()
            logger.info("Seeded %d system platform(s)", added)
        return True
    except Exception as exc:
        db.rollback()
        logger.error("System platform seeding failed: %s", exc)
        return False


def _seed_default_profiles(db) -> bool:
    try:
        from backend.models import Profile
        added = 0
        for data in _DEFAULT_PROFILES:
            if not db.query(Profile).filter(Profile.slug == data["slug"]).first():
                db.add(Profile(**data))
                added += 1
        if added:
            db.flush()
            logger.info("Seeded %d default profile(s)", added)
        return True
    except Exception as exc:
        db.rollback()
        logger.error("Default profile seeding failed: %s", exc)
        return False
