from backend.core.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_PROFILES = [
    {"name": "DOS Default", "slug": "dos-default", "platform": "dos", "emulator_slug": "dosbox-x", "is_bundled": True},
    {
        "name": "Win 95 Default",
        "slug": "win95-compat",
        "platform": "win95",
        "emulator_slug": "86box",
        "is_bundled": True,
    },
    {
        "name": "Win 98 Default",
        "slug": "win98-compat",
        "platform": "win98",
        "emulator_slug": "86box",
        "is_bundled": True,
    },
    {
        "name": "Win XP Default",
        "slug": "winxp-default",
        "platform": "winxp",
        "emulator_slug": "86box",
        "is_bundled": True,
    },
    {
        "name": "PS1 Default",
        "slug": "ps1-default",
        "platform": "ps1",
        "emulator_slug": "duckstation",
        "is_bundled": True,
    },
    {"name": "PS2 Default", "slug": "ps2-default", "platform": "ps2", "emulator_slug": "pcsx2", "is_bundled": True},
    {"name": "PS3 Default", "slug": "ps3-default", "platform": "ps3", "emulator_slug": "rpcs3", "is_bundled": True},
    {
        "name": "Xbox OG Default",
        "slug": "xbox-default",
        "platform": "xbox",
        "emulator_slug": "xemu",
        "is_bundled": True,
    },
    {
        "name": "xbox 360 Default",
        "slug": "xbox-360-default",
        "platform": "xbox360",
        "emulator_slug": "xenia",
        "is_bundled": True,
    },
    {"name": "NES Default", "slug": "nes-default", "platform": "nes", "emulator_slug": "mesen", "is_bundled": True},
    {"name": "SNES Default", "slug": "snes-default", "platform": "snes", "emulator_slug": "mesen", "is_bundled": True},
    {"name": "N64 Default", "slug": "n64-default", "platform": "n64", "emulator_slug": "project64", "is_bundled": True},
    {
        "name": "Dreamcast Default",
        "slug": "dreamcast-default",
        "platform": "dreamcast",
        "emulator_slug": "flycast",
        "is_bundled": True,
    },
]


# System tags seeded so the is_system delete guard in the tags route is
# actually reachable and the frontend "System tags" section renders real
# API data instead of hardcoded constants. Names and grouping are migrated
# verbatim from frontend/src/pages/Tags/index.tsx (SYSTEM_HARDWARE_TAGS,
# SYSTEM_CONTENT_TAGS, and the PLATFORM_LABELS-derived platform pills). Platform names are
# pulled from the shared PLATFORM_LABELS constant rather than re-listed here so
# they cannot drift from the generated source of truth. Colors are drawn from
# the TagColor swatch set to preserve the original hardware/content/platform visual
# grouping (amber/sky/coral); they are not new categories.
_SYSTEM_HARDWARE_TAG_NAMES = [
    "MT-32",
    "Sound Blaster 16",
    "AdLib",
    "Voodoo 1",
    "Voodoo 3",
    "Gravis Ultrasound",
]

_SYSTEM_CONTENT_TAG_NAMES = [
    "Game",
    "Application",
    "Utility",
    "Demo",
    "ROM Pack",
]


def _seed_system_tags(db) -> bool:
    """Seed the read-only system tags (is_system=True).

    Idempotent check-before-insert keyed on the unique tag name, matching the
    environment/profile seeders. Runs on every startup; existing tags are left
    untouched so this is safe to re-run.
    """
    try:
        from backend.models.tag import Tag
        from backend.constants_generated import PLATFORM_LABELS

        # (name, color) pairs. Platform names come from PLATFORM_LABELS so they track the
        # generated constant; hardware/content are the verbatim frontend labels.
        specs: list[tuple[str, str]] = (
            [(label, "coral") for label in PLATFORM_LABELS.values()]
            + [(name, "amber") for name in _SYSTEM_HARDWARE_TAG_NAMES]
            + [(name, "sky") for name in _SYSTEM_CONTENT_TAG_NAMES]
        )
        added = 0
        for name, color in specs:
            if not db.query(Tag).filter(Tag.name == name).first():
                db.add(Tag(name=name, color=color, is_system=True))
                added += 1
        if added:
            db.flush()
            logger.info("Seeded %d system tag(s)", added)
        return True
    except Exception as exc:
        db.rollback()
        logger.error("System tag seeding failed: %s", exc)
        return False


def _seed_default_profiles(db) -> bool:
    try:
        from backend.models import ProfileItem

        added = 0
        for data in _DEFAULT_PROFILES:
            if not db.query(ProfileItem).filter(ProfileItem.slug == data["slug"]).first():
                db.add(ProfileItem(**data))
                added += 1
        if added:
            db.flush()
            logger.info("Seeded %d default profile(s)", added)
        return True
    except Exception as exc:
        db.rollback()
        logger.error("Default profile seeding failed: %s", exc)
        return False


# DOS environment. Seeded as a normal Environment (is_system False) with a
# linked bundled profile, so it is listed on the Environments page and in the
# Environment field like a user-created one. Per-item drives are created
# lazily by drive_hydration; DOSBox-X item launches mount no shared image.
_DOSBOX_ENVIRONMENTS = [
    {"slug": "dos", "name": "DOS", "platform": "dos", "profile_slug": "dos-default", "image_rel": "os/dos/dos.img"},
]


def _seed_dosbox_environments(db) -> bool:
    """Seed the DOS environment.

    Must run after _seed_default_profiles so the bundled dos-default
    profile exists to link via profile_item_id. working_image_path is
    preset to a canonical path under library/system/os/ but is not mounted by
    DOSBox-X item launches; per-item drives are created lazily by drive_hydration.
    """
    try:
        from backend.models import EnvironmentItem, ProfileItem
        from backend.core.settings import get_base_path

        os_root = get_base_path() / "library" / "system"
        added = 0
        for env in _DOSBOX_ENVIRONMENTS:
            if db.query(EnvironmentItem).filter(EnvironmentItem.slug == env["slug"]).first():
                continue
            profile = db.query(ProfileItem).filter(ProfileItem.slug == env["profile_slug"]).first()
            if profile is None:
                logger.error(
                    "Cannot seed '%s' environment: bundled profile '%s' not found",
                    env["slug"],
                    env["profile_slug"],
                )
                return False
            image_path = str((os_root / env["image_rel"]).resolve())
            db.add(
                EnvironmentItem(
                    slug=env["slug"],
                    name=env["name"],
                    platform=env["platform"],
                    emulator_slug="dosbox-x",
                    profile_item_id=profile.id,
                    working_image_path=image_path,
                    is_system=False,
                )
            )
            added += 1
        if added:
            db.flush()
            logger.info("Seeded %d DOS environment(s)", added)
        return True
    except Exception as exc:
        db.rollback()
        logger.error("DOS environment seeding failed: %s", exc)
        return False
