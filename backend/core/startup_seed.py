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
        "supported_eras": json.dumps(["dos"]),
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


def _seed_system_environments(db) -> bool:
    try:
        from backend.models import EnvironmentItem
        added = 0
        for data in _SYSTEM_PLATFORMS:
            if not db.query(EnvironmentItem).filter(EnvironmentItem.slug == data["slug"]).first():
                db.add(EnvironmentItem(**data))
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


# DOS environment. Seeded to provide a Platform record with a
# linked bundled profile so item launches resolve the right emulator/settings
# via Platform.profile_id. Per-item drives are created lazily by drive_hydration
# at launch time; no shared working image is mounted by DOSBox-X item launches.
_DOSBOX_ENVIRONMENTS = [
    {"slug": "dos",   "name": "DOS",          "era": "dos",   "profile_slug": "dos-default",   "image_rel": "os/dos/dos.img"},
]


def _seed_dosbox_environments(db) -> bool:
    """Seed the DOS environment platform.

    Must run after _seed_default_profiles so the bundled dos-default
    profile exists to link via profile_id. working_image_path is
    preset to a canonical path under library/system/os/ but is not mounted by
    DOSBox-X item launches; per-item drives are created lazily by drive_hydration.
    """
    try:
        from backend.models import EnvironmentItem, Profile
        from backend.core.settings import get_base_path

        os_root = get_base_path() / "library" / "system"
        added = 0
        for env in _DOSBOX_ENVIRONMENTS:
            if db.query(EnvironmentItem).filter(EnvironmentItem.slug == env["slug"]).first():
                continue
            profile = db.query(Profile).filter(Profile.slug == env["profile_slug"]).first()
            if profile is None:
                logger.error(
                    "Cannot seed '%s' environment: bundled profile '%s' not found",
                    env["slug"], env["profile_slug"],
                )
                return False
            image_path = str((os_root / env["image_rel"]).resolve())
            db.add(EnvironmentItem(
                slug=env["slug"],
                name=env["name"],
                era=env["era"],
                emulator_slug="dosbox-x",
                profile_id=profile.id,
                working_image_path=image_path,
                is_system=True,
                status="unconfigured",
            ))
            added += 1
        if added:
            db.flush()
            logger.info("Seeded %d DOS environment(s)", added)
        return True
    except Exception as exc:
        db.rollback()
        logger.error("DOS environment seeding failed: %s", exc)
        return False
