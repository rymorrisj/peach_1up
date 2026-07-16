from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from pydantic import model_validator
from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import validates
from sqlmodel import Field, Relationship, SQLModel

from backend.constants import PC_ERAS
from backend.constants_generated import EraValue, FileType
from backend.models.tag import TagRead, get_tags_for_entities, get_tags_for_entity

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from backend.models.drive import Drive

# ---------------------------------------------------------------------------
# Leaf entity: AppItem (one file/part within an app bundle). Mirrors
# GameItem (backend/models/game.py) minus disc_number, apps have no
# disc-swap concept, so items are ordered by id (insertion order) rather than
# an explicit position column. Most apps are single-item; the bundle/item
# split exists mainly for multi-part installs.
# ---------------------------------------------------------------------------


class AppItem(SQLModel, table=True):
    __tablename__ = "app_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    app_item_bundle_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("app_item_bundles.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    file_path: str = Field(sa_column=Column(String, nullable=False, index=True))
    executable_path: Optional[str] = None
    cover_art_path: Optional[str] = None
    file_type: Optional[FileType] = Field(default=None, sa_column=Column(String))
    folder_path: Optional[str] = Field(default=None, index=True)
    detection_reason: Optional[str] = None
    file_size_bytes: Optional[int] = None
    original_name: Optional[str] = None
    # Same semantics as GameItem.folder_owned: True only when folder_path
    # was created/renamed exclusively for this item by the app's own create
    # flow, safe to rmtree on delete. False/None means folder_path is a
    # pre-existing directory not owned by this app and must never be rmtree'd.
    folder_owned: Optional[bool] = None
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False),
    )

    app_item_bundle: Optional["AppItemBundle"] = Relationship(back_populates="items")


class AppItemRead(SQLModel):
    id: int
    app_item_bundle_id: int
    file_path: str
    executable_path: Optional[str] = None
    cover_art_path: Optional[str] = None
    cover_art_url: Optional[str] = None
    file_type: Optional[FileType] = None
    folder_path: Optional[str] = None
    detection_reason: Optional[str] = None
    file_size_bytes: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _compute_cover_art_url(self) -> "AppItemRead":
        # Same pattern as GameItemRead._compute_cover_art_url.
        if not self.cover_art_path:
            return self
        try:
            from backend.service.utils import settings as _s

            lib_root = Path(_s.get("LIBRARY_PATH"))
            resolved = Path(self.cover_art_path).resolve()
            rel = resolved.relative_to(lib_root.resolve())
            if resolved.exists():
                self.cover_art_url = "/media/" + rel.as_posix()
        except ValueError:
            pass
        return self


class AppItemUpdate(SQLModel):
    executable_path: Optional[str] = None
    cover_art_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Parent entity: AppItemBundle. Mirrors GameItemBundle (see
# backend/models/game.py): era is the source of truth, is_pc is
# derived-and-validated from era on every write (same @validates +
# model_post_init pattern as GameItemBundle.item_type, see
# derive_is_pc/_validate_is_pc/model_post_init below), and
# environment_item_id is nullable — required for PC apps, forbidden for
# console apps, enforced in the service layer
# (backend/service/apps/items.py::_enforce_environment_binding), same shape
# as GameItemBundle's _enforce_environment_binding rule. Consoles can host
# Apps (utility software, tools) exactly as they can host Games; there is no
# PC-only restriction on this entity.
#
# content_rating is dropped rather than carried over. SECURITY.md's rationale
# for MediaRestriction (manual per-user restriction, no automatic rating
# filter) is that there is no reliable signal to derive or enforce a rating
# for archival media, the same reasoning applies here even more directly:
# utility software (a calculator, a CAD package, an old Word install) has no
# age-rating concept at all, not just an undetectable one. launch_review_flagged
# is dropped alongside it since that flag exists specifically to gate a launch
# pending content-rating review.
# ---------------------------------------------------------------------------


def derive_is_pc(era: EraValue) -> bool:
    """era is the source of truth for is_pc: PC eras -> True, everything else -> False.

    Mirrors backend/models/game.py's derive_item_type exactly, as a bool.
    """
    return era in PC_ERAS


class AppItemBundle(SQLModel, table=True):
    __tablename__ = "app_item_bundles"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: Optional[str] = Field(default=None, index=True, unique=True)
    title: str
    sort_title: Optional[str] = None
    era: EraValue = Field(sa_column=Column(String, nullable=False))
    # Derived-and-validated from era on write (see _validate_is_pc below);
    # default=None only so construction can omit it before the validator
    # fills it in, the stored column is NOT NULL. Mirrors
    # GameItemBundle.item_type exactly, as a bool instead of a "pc"/"console"
    # string since Apps have no other item_type consumer today.
    is_pc: bool = Field(default=None, sa_column=Column(Boolean, nullable=False))
    category: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    developer: Optional[str] = None
    year: Optional[int] = None
    launch_commands: Optional[list[str]] = Field(default=None, sa_column=Column(JSON))
    installed: bool = False
    requires_install: bool = False
    # None = inherit the global delete_media_on_removal setting. True/False
    # explicitly overrides it for this bundle only.
    delete_media_override: Optional[bool] = None

    # Nullable: required for PC apps, forbidden for console apps, enforced
    # in the service layer (_enforce_environment_binding), same shape as
    # GameItemBundle.environment_item_id. SET NULL (not RESTRICT) so
    # deleting an in-use Environment behaves the same as it does for Games.
    environment_item_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("environment_items.id", ondelete="SET NULL"), nullable=True),
    )
    profile_item_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("profile_items.id", ondelete="SET NULL"), nullable=True),
    )
    drive_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("drives.id"), nullable=True),
    )
    # Logical FKs to app_items.id. Not DB-level constraints, mirroring
    # GameItemBundle.launch_disk_id/display_disk_id (avoids a circular
    # reference between app_item_bundles and app_items during table creation).
    launch_disk_id: Optional[int] = Field(default=None)
    display_disk_id: Optional[int] = Field(default=None)

    last_launched_at: Optional[datetime] = None
    launch_count: int = 0
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False),
    )

    items: list["AppItem"] = Relationship(
        back_populates="app_item_bundle",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "order_by": "AppItem.id",
        },
    )

    drive: Optional["Drive"] = Relationship(
        back_populates="app_item_bundle",
        sa_relationship_kwargs={
            "foreign_keys": "Drive.app_item_bundle_id",
            "uselist": False,
        },
    )

    @validates("is_pc")
    def _validate_is_pc(self, key: str, value: Optional[bool]) -> Optional[bool]:
        derived = derive_is_pc(self.era)
        if value is not None and value != derived:
            raise ValueError(
                f"is_pc {value!r} conflicts with era {self.era!r} "
                f"(era implies {derived!r}). is_pc is derived from era, not independently settable."
            )
        return value

    def model_post_init(self, __context: object) -> None:
        # Same double-write caveat as GameItemBundle.model_post_init (see
        # backend/models/game.py) — is_pc can only be reliably derived here,
        # not by returning a different value from _validate_is_pc above.
        self.is_pc = derive_is_pc(self.era)


class AppItemBundleCreate(SQLModel):
    title: str
    file_path: str
    era: EraValue = "unknown"
    environment_item_id: Optional[int] = None
    profile_item_id: Optional[int] = None


class AppItemBundleUpdate(SQLModel):
    title: Optional[str] = None
    sort_title: Optional[str] = None
    era: Optional[EraValue] = None
    category: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    developer: Optional[str] = None
    year: Optional[int] = None
    launch_commands: Optional[list[str]] = None
    installed: Optional[bool] = None
    requires_install: Optional[bool] = None
    delete_media_override: Optional[bool] = None
    environment_item_id: Optional[int] = None
    profile_item_id: Optional[int] = None
    display_disk_id: Optional[int] = None
    launch_disk_id: Optional[int] = None


class AppItemBundleRead(SQLModel):
    id: int
    slug: Optional[str] = None
    title: str
    sort_title: Optional[str] = None
    era: EraValue
    is_pc: bool
    category: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    developer: Optional[str] = None
    year: Optional[int] = None
    launch_commands: Optional[list[str]] = None
    installed: bool = False
    requires_install: bool = False
    delete_media_override: Optional[bool] = None
    environment_item_id: Optional[int] = None
    profile_item_id: Optional[int] = None
    drive_id: Optional[int] = None
    launch_disk_id: Optional[int] = None
    display_disk_id: Optional[int] = None
    last_launched_at: Optional[datetime] = None
    launch_count: int = 0
    created_at: datetime
    updated_at: datetime
    items: list[AppItemRead] = []
    tags: list[TagRead] = []
    # Pre-launch UX gate, same semantics and shared computation as
    # GameItemBundleRead.launch_blocked_reason (see backend/models/game.py and
    # the shared compute_launch_blocked_reason). "no_profile" when the bundle has
    # no launch profile (pc or console); "no_environment" for a PC app with no
    # resolvable Environment; "environment_era_mismatch" or
    # "environment_not_installed" for a resolvable-but-unlaunchable one; None
    # otherwise. Computed at read time, not stored.
    launch_blocked_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Read-model builders, same shape as backend/models/game.py's
# game_item_bundle_to_read / game_item_bundles_to_read_bulk.
# ---------------------------------------------------------------------------


def _leaf_to_read(leaf: AppItem) -> Optional[AppItemRead]:
    """Validate one leaf into an AppItemRead, isolating a single bad row.

    Mirrors GameItem's _leaf_to_read degrade-then-drop path so one row
    with an out-of-vocabulary file_type cannot 500 the whole list response.
    """
    from pydantic import ValidationError

    from backend.core.logger import get_logger

    try:
        return AppItemRead.model_validate(leaf)
    except ValidationError as exc:
        log = get_logger(__name__)
        leaf_id = getattr(leaf, "id", None)
        log.warning(
            "App item %s failed read validation (%s); serving with file_type nulled.",
            leaf_id, exc,
        )
        try:
            payload = {
                name: getattr(leaf, name, None)
                for name in AppItemRead.model_fields
                if name != "cover_art_url"
            }
            payload["file_type"] = None
            return AppItemRead.model_validate(payload)
        except ValidationError as exc2:
            log.warning(
                "App item %s is unreadable even after degrading file_type; dropping it: %s",
                leaf_id, exc2,
            )
            return None


def app_item_bundle_to_read(c: "AppItemBundle", db: "Session") -> AppItemBundleRead:
    """Build an AppItemBundleRead, nesting ordered leaves, tags, and the
    pre-launch gate.

    era/is_pc come straight off the AppItemBundle row via model_validate
    (see AppItemBundle.era/is_pc). launch_blocked_reason mirrors game.py:
    Environment is only resolved for a PC app (era match and is_installed
    are checked inside compute_launch_blocked_reason once resolved).
    """
    from backend.service.utils.era_defaults import compute_launch_blocked_reason, resolve_environment_for_launch_gate

    read = AppItemBundleRead.model_validate(c)
    read.items = [r for i in c.items if (r := _leaf_to_read(i)) is not None]
    read.tags = get_tags_for_entity("app_item_bundle", c.id, db)
    environment = (
        resolve_environment_for_launch_gate(c.environment_item_id, c.era, db)
        if c.is_pc else None
    )
    read.launch_blocked_reason = compute_launch_blocked_reason(
        is_pc=c.is_pc,
        era=c.era,
        profile_item_id=c.profile_item_id,
        environment=environment,
    )
    return read


def app_item_bundles_to_read_bulk(bundles: list["AppItemBundle"], db: "Session") -> list[AppItemBundleRead]:
    """app_item_bundle_to_read over a list in bulk queries instead of the per-bundle N+1."""
    from sqlalchemy import select as _select

    from backend.service.utils.era_defaults import compute_launch_blocked_reason, resolve_environments_for_launch_gate_bulk

    if not bundles:
        return []

    bundle_ids = [c.id for c in bundles]
    leaves = db.execute(
        _select(AppItem)
        .where(AppItem.app_item_bundle_id.in_(bundle_ids))
        .order_by(AppItem.app_item_bundle_id, AppItem.id)
    ).scalars().all()

    leaves_by_bundle: dict[int, list[AppItemRead]] = {}
    for leaf in leaves:
        leaf_read = _leaf_to_read(leaf)
        if leaf_read is None:
            continue
        leaves_by_bundle.setdefault(leaf.app_item_bundle_id, []).append(leaf_read)

    tag_map = get_tags_for_entities("app_item_bundle", bundle_ids, db)

    # Batched Environment resolution (explicit id + era-matched system
    # fallback) for every PC app bundle, mirroring game.py's bulk path.
    pc_bundles = [c for c in bundles if c.is_pc]
    environment_by_bundle_id = resolve_environments_for_launch_gate_bulk(pc_bundles, db)

    reads: list[AppItemBundleRead] = []
    for c in bundles:
        read = AppItemBundleRead.model_validate(c)
        read.items = leaves_by_bundle.get(c.id, [])
        read.tags = tag_map.get(c.id, [])
        read.launch_blocked_reason = compute_launch_blocked_reason(
            is_pc=c.is_pc,
            era=c.era,
            profile_item_id=c.profile_item_id,
            environment=environment_by_bundle_id.get(c.id),
        )
        reads.append(read)
    return reads
