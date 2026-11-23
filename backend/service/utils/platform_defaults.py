from typing import Literal

from sqlalchemy.orm import Session

from backend.constants import BOX86_PLATFORMS, DOSBOX_PLATFORMS, PC_PLATFORMS
from backend.constants_generated import PLATFORM_BACKENDS

# Platforms whose user-created Environments get an auto-provisioned working
# image (86Box VHD+config, or the DOSBox-X FAT16 C: drive) when created or
# launched without one. Shared by coordinator._ensure_environment_provisioned
# and environments.create_environment_item.
PROVISIONABLE_PLATFORMS: frozenset[str] = BOX86_PLATFORMS | DOSBOX_PLATFORMS


def defaults_for_platform(platform_slug: str) -> tuple[str | None, str | None]:
    """Return (emulator_slug, profile_platform) for a known platform, or (None, None)."""
    emulator_slug = PLATFORM_BACKENDS.get(platform_slug)
    if emulator_slug is None:
        return (None, None)
    return (emulator_slug, platform_slug)


def lookup_default_profile(emulator_slug: str, profile_platform: str, db: Session) -> int | None:
    """Return the id of the bundled profile for *profile_platform* and *emulator_slug*, or None.

    Bundled profiles only: a user profile is never picked as a default.
    """
    from backend.models.profile import ProfileItem

    profile = (
        db.query(ProfileItem)
        .filter(
            ProfileItem.platform == profile_platform,
            ProfileItem.emulator_slug == emulator_slug,
            ProfileItem.is_bundled.is_(True),
        )
        .order_by(ProfileItem.id)
        .first()
    )
    return profile.id if profile else None


def resolve_platform_defaults(platform: str, db: Session) -> int | None:
    """Return the suggested profile id for *platform*, or None.

    Used at ingest and when a bundle's platform changes. The Environment is
    never suggested: the user creates and chooses it. "unknown" and any
    platform without a backend resolve to None.
    """
    emulator_slug, profile_platform = defaults_for_platform(platform)
    if not emulator_slug or not profile_platform:
        return None
    return lookup_default_profile(emulator_slug, profile_platform, db)


def rebind_for_platform_change(
    stored_profile_item_id: int | None,
    stored_environment_item_id: int | None,
    fields: dict,
    new_platform: str,
    db: Session,
) -> None:
    """Apply a platform change to a bundle PATCH's *fields* (Games and Apps).

    The profile is refilled with *new_platform*'s suggested profile unless the
    request chose a different one: a value counts as chosen only when it is
    not None and differs from the stored id, since the edit form echoes the
    stored ids on every save. The Environment is never suggested; a console
    platform clears it under the same echo rule, a PC platform keeps it.
    """
    chosen_profile = fields.get("profile_item_id")
    if chosen_profile is None or chosen_profile == stored_profile_item_id:
        fields["profile_item_id"] = resolve_platform_defaults(new_platform, db)
    if new_platform not in PC_PLATFORMS:
        chosen_environment = fields.get("environment_item_id")
        if chosen_environment is None or chosen_environment == stored_environment_item_id:
            fields["environment_item_id"] = None


def environment_is_installed(env) -> bool:
    """Whether *env* (an EnvironmentItem) satisfies the "OS installed" gate.

    Reads installed_at (set by the "Mark as Installed" action). DOSBox-X
    environments have no install step, so they always count as installed.
    """
    if env.platform in DOSBOX_PLATFORMS:
        return True
    return env.installed_at is not None


def resolve_environment_for_launch_gate(environment_item_id: int | None, db: Session):
    """The Environment evaluate_launch_readiness gates against: the item's
    own environment_item_id, or None. Mirrors
    coordinator._resolve_environment_for_pc_entity."""
    from backend.models.environment import EnvironmentItem

    if environment_item_id is None:
        return None
    return db.get(EnvironmentItem, environment_item_id)


def resolve_environments_for_launch_gate_bulk(items: list, db: Session) -> dict[int, object]:
    """Batch form of resolve_environment_for_launch_gate for read-bulk builders.

    *items* is any list of objects with .id and .environment_item_id
    (GameItemBundle or AppItemBundle rows). Returns {item.id: EnvironmentItem|None}
    in one query.
    """
    from backend.models.environment import EnvironmentItem

    if not items:
        return {}

    explicit_ids = {i.environment_item_id for i in items if i.environment_item_id is not None}
    by_id: dict[int, EnvironmentItem] = {}
    if explicit_ids:
        for row in db.query(EnvironmentItem).filter(EnvironmentItem.id.in_(explicit_ids)).all():
            by_id[row.id] = row

    return {i.id: by_id.get(i.environment_item_id) if i.environment_item_id is not None else None for i in items}


# The full reason vocabulary for both evaluate_launch_readiness call sites,
# plus "environment_not_present". "environment_not_installed" is only ever
# returned for call_site="item". "environment_not_present" is never returned
# by evaluate_launch_readiness itself, it needs a live filesystem check
# (compute_environment_presence); it is part of this Literal so
# GET /api/v1/environment-items?platform=... can report it with the same
# vocabulary.
LaunchBlockedReason = Literal[
    "no_profile",
    "no_environment",
    "environment_not_provisioned",
    "environment_not_installed",
    "environment_not_present",
]

# Placeholder passed as evaluate_launch_readiness's profile_item_id when
# evaluating a single Environment candidate out of context (one row of the
# Environment picker), where "does this item have a profile" does not vary by
# candidate. Only ever None-checked, never resolved against a ProfileItem;
# real ids are positive, so a negative sentinel cannot collide with one.
CANDIDATE_EVAL_PROFILE_SENTINEL = -1


def evaluate_launch_readiness(
    *,
    call_site: Literal["item", "environment"],
    environment,
    is_pc: bool = False,
    profile_item_id: int | None = None,
) -> LaunchBlockedReason | None:
    """Single source of truth for pre-launch gating, used by coordinator.py
    (_launch_entity, launch_environment) and the read-time
    launch_blocked_reason signal (models/game.py, models/app.py).

    call_site="item" is a game/app bundle launch or its read-time signal:
    no_profile, then for PC only: no_environment (none chosen),
    environment_not_provisioned (no working image and its platform can never
    get one auto-provisioned), environment_not_installed (OS never installed,
    see environment_is_installed). Console items need no Environment. There
    is no platform compatibility rule: the user chooses the Environment.

    call_site="environment" is a direct Environment launch, how a user runs
    its own OS installer, so only environment_not_provisioned applies and
    environment_not_installed is structurally unreachable.

    Pure reads of already-resolved state, safe for GET read-model builders.
    """
    if call_site == "environment":
        if (
            environment is not None
            and environment.working_image_path is None
            and environment.platform not in PROVISIONABLE_PLATFORMS
        ):
            return "environment_not_provisioned"
        return None

    if profile_item_id is None:
        return "no_profile"
    if not is_pc:
        return None
    if environment is None:
        return "no_environment"
    if environment.working_image_path is None and environment.platform not in PROVISIONABLE_PLATFORMS:
        return "environment_not_provisioned"
    if not environment_is_installed(environment):
        return "environment_not_installed"
    return None
