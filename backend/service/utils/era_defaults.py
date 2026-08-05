from typing import Literal

from sqlalchemy.orm import Session

from backend.constants_generated import ERA_BACKENDS

# Eras served by DOSBox-X (per-item FAT16 C: drive, not a shared working image).
DOS_WIN_ERAS: frozenset[str] = frozenset({"dos"})

# Eras that get an auto-provisioned working image (86Box VHD+config, or the
# DOSBox-X FAT16 C: drive) when an Environment is created or launched without
# one. Single definition, previously duplicated as an inline literal in both
# coordinator.py's _ensure_environment_provisioned and environments.py's
# create_environment_item.
PROVISIONABLE_ERAS: frozenset[str] = frozenset({"win95", "win98", "winxp"}) | DOS_WIN_ERAS


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
        .filter(EnvironmentItem.emulator_slug == emulator_slug, EnvironmentItem.is_system == True)  # noqa: E712
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
    boolean, installed_at already recorded exactly this concept before this
    change, and adding a second field for the same fact would recreate the
    same kind of duplicate-state drift this task exists to fix.

    DOS/DOSBox-X environments have no install step (DOSBox-X boots straight
    to a DOS prompt against the per-item drive), so they are always treated
    as installed regardless of installed_at, checked here, at read time,
    rather than forced true at creation, so the rule can't drift if an
    environment's era is ever changed after creation.
    """
    if env.era in DOS_WIN_ERAS:
        return True
    return env.installed_at is not None


def resolve_environment_for_launch_gate(environment_item_id: int | None, era: str, db: Session):
    """Resolve the Environment evaluate_launch_readiness should gate
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
        # Deterministic tiebreaker for the (should-not-happen, defended anyway)
        # case of two is_system rows sharing an era: prefer the row that
        # actually has a working_image_path (a real launch target) over one
        # that doesn't (a catalog/presence-only artifact), lowest id as the
        # final tiebreaker. setdefault keeps the first (best-ranked) row per
        # era and ignores any later ones, instead of the previous unordered
        # .all() where the last row iterated silently won.
        for row in (
            db.query(EnvironmentItem)
            .filter(EnvironmentItem.era.in_(fallback_eras), EnvironmentItem.is_system == True)  # noqa: E712
            .order_by(EnvironmentItem.working_image_path.is_(None), EnvironmentItem.id)
            .all()
        ):
            by_era.setdefault(row.era, row)

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

    Deterministic ORDER BY as defense in depth: seeding is expected to produce
    at most one is_system row per era (fixed at the source after the DOS
    dosbox-x/dos duplicate-row bug), but if a duplicate is ever reintroduced
    (e.g. a manual is_system=True PATCH), this prefers the row with a real
    working_image_path over a presence-only catalog artifact, lowest id as
    the final tiebreaker, instead of leaving the choice to unordered .first().
    """
    from backend.models.environment import EnvironmentItem

    return (
        db.query(EnvironmentItem)
        .filter(EnvironmentItem.era == era, EnvironmentItem.is_system == True)  # noqa: E712
        .order_by(EnvironmentItem.working_image_path.is_(None), EnvironmentItem.id)
        .first()
    )


# The full reason vocabulary for both evaluate_launch_readiness call sites.
# "environment_not_installed" is only ever returned for call_site="item";
# see evaluate_launch_readiness's docstring.
LaunchBlockedReason = Literal[
    "no_profile",
    "no_environment",
    "environment_era_mismatch",
    "environment_not_provisioned",
    "environment_not_installed",
]


def evaluate_launch_readiness(
    *,
    call_site: Literal["item", "environment"],
    environment,
    is_pc: bool = False,
    era: str | None = None,
    profile_item_id: int | None = None,
) -> LaunchBlockedReason | None:
    """Single source of truth for pre-launch gating. Real enforcement in
    coordinator.py (_launch_entity, launch_environment) and the read-time
    launch_blocked_reason UI signal (models/game.py, models/app.py) both call
    this instead of each re-implementing the sequence.

    Two call sites, deliberately different gate sets, this distinction is
    security-relevant and must not be collapsed into one shared check:

    call_site="item" is a game/app bundle launch (coordinator._launch_entity's
    PC branch) or its read-time signal. Runs the full sequence in order:
    no profile -> no_environment (PC only, no resolvable Environment) ->
    environment_era_mismatch -> environment_not_provisioned (no working image
    and this era can never get one auto-provisioned) -> environment_not_installed
    (a provisioned Environment whose OS has never actually been installed, see
    environment_is_installed). "environment_not_installed" only ever applies
    to this call site.

    call_site="environment" is a direct Environment launch
    (coordinator.launch_environment), how a user boots an Environment to run
    its own OS installer in the first place. Only environment_not_provisioned
    applies here. Profile resolution, era match, and environment_not_installed
    are meaningless or actively wrong to check on this path: blocking a direct
    Environment launch on "not installed yet" would make it impossible to ever
    finish installing. This function must never return
    "environment_not_installed" for call_site="environment", enforced
    structurally below (that branch is not reachable from this call_site at
    all, not merely skipped by a condition).

    All checks are pure reads of already-resolved state, no filesystem
    provisioning and no writes, safe to call from a GET-triggered read-model
    builder. Media resolution, path containment, and emulator-installed remain
    enforced inline in _launch_entity / _build_spec_for_entity, not here: they
    need the entity's actually-resolved media/executable paths and do real
    filesystem work, folding them in here would mean every library list/detail
    response pays that I/O cost per row.
    """
    if call_site == "environment":
        if (
            environment is not None
            and environment.working_image_path is None
            and environment.era not in PROVISIONABLE_ERAS
        ):
            return "environment_not_provisioned"
        return None

    if profile_item_id is None:
        return "no_profile"
    if not is_pc:
        return None
    if environment is None:
        return "no_environment"
    if environment.era != era:
        return "environment_era_mismatch"
    if environment.working_image_path is None and environment.era not in PROVISIONABLE_ERAS:
        return "environment_not_provisioned"
    if not environment_is_installed(environment):
        return "environment_not_installed"
    return None
