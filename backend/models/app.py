from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from pydantic import model_validator
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, func
from sqlmodel import Field, Relationship, SQLModel

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
            rel = Path(self.cover_art_path).resolve().relative_to(lib_root.resolve())
            self.cover_art_url = "/media/" + rel.as_posix()
        except ValueError:
            pass
        return self


class AppItemUpdate(SQLModel):
    executable_path: Optional[str] = None
    cover_art_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Parent entity: AppItemBundle. Mirrors GameItemBundle deliberately (see
# backend/models/game.py) but is always PC, there is no console case, no
# era-driven launch fallback, and no item_type column. environment_item_id is
# required and non-nullable: an App with no verified Environment is not a
# creatable entity, unlike PC Games where environment_item_id may start null
# and be backfilled later.
#
# era is deliberately NOT stored here. GameItemBundle stores era
# redundantly alongside environment_item_id because console GameItemBundles
# have no Environment to derive it from (era is the only source of truth for
# those rows) and because item_type is validated against era on every write.
# Neither condition applies to Apps: they are always PC, always carry a
# non-null environment_item_id, and have no item_type. Storing era again here
# would just be a second, independently-driftable copy of a value the linked
# Environment already owns, derive it at read time instead (see
# app_item_bundle_to_read/app_item_bundles_to_read_bulk below).
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


class AppItemBundle(SQLModel, table=True):
    __tablename__ = "app_item_bundles"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: Optional[str] = Field(default=None, index=True, unique=True)
    title: str
    sort_title: Optional[str] = None
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

    # Required, non-nullable: an App without a verified Environment is
    # meaningless and must never exist in a creatable state (doc 02 A5's
    # "environment required" backfill window does not apply here, there is
    # no legacy Apps data to migrate). RESTRICT (not SET NULL, which would
    # violate this column's NOT NULL constraint) so deleting an in-use
    # Environment fails loudly at the DB layer; the service layer
    # (environments.delete_platform) checks for referencing AppItemBundles
    # up front and returns a clean 409 before that constraint is ever hit.
    environment_item_id: int = Field(
        sa_column=Column(Integer, ForeignKey("environment_items.id", ondelete="RESTRICT"), nullable=False)
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


class AppItemBundleCreate(SQLModel):
    title: str
    file_path: str
    environment_item_id: int
    profile_item_id: Optional[int] = None


class AppItemBundleUpdate(SQLModel):
    title: Optional[str] = None
    sort_title: Optional[str] = None
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

    @model_validator(mode="before")
    @classmethod
    def _reject_null_environment(cls, data: object) -> object:
        # environment_item_id is NOT NULL at the DB level; reject an explicit
        # null here with a clear 422 instead of letting it fall through to an
        # IntegrityError. Omitting the field entirely (leaving it unset) is
        # fine and simply means "no change."
        if isinstance(data, dict) and "environment_item_id" in data and data["environment_item_id"] is None:
            raise ValueError("environment_item_id cannot be cleared; every App requires an Environment.")
        return data


class AppItemBundleRead(SQLModel):
    id: int
    slug: Optional[str] = None
    title: str
    sort_title: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    developer: Optional[str] = None
    year: Optional[int] = None
    launch_commands: Optional[list[str]] = None
    installed: bool = False
    requires_install: bool = False
    delete_media_override: Optional[bool] = None
    environment_item_id: int
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
    # Derived from the linked Environment at read time, never stored (see the
    # module docstring above the AppItemBundle class for the reasoning).
    era: Optional[EraValue] = None


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


def _eras_for_environments(environment_ids: set[int], db: "Session") -> dict[int, EraValue]:
    from backend.models.environment import EnvironmentItem

    if not environment_ids:
        return {}
    rows = db.query(EnvironmentItem.id, EnvironmentItem.era).filter(EnvironmentItem.id.in_(environment_ids)).all()
    return {row[0]: row[1] for row in rows}


def app_item_bundle_to_read(c: "AppItemBundle", db: "Session") -> AppItemBundleRead:
    """Build an AppItemBundleRead, nesting ordered leaves, tags, and the
    Environment-derived era."""
    read = AppItemBundleRead.model_validate(c)
    read.items = [r for i in c.items if (r := _leaf_to_read(i)) is not None]
    read.tags = get_tags_for_entity("app_item_bundle", c.id, db)
    read.era = _eras_for_environments({c.environment_item_id}, db).get(c.environment_item_id)
    return read


def app_item_bundles_to_read_bulk(bundles: list["AppItemBundle"], db: "Session") -> list[AppItemBundleRead]:
    """app_item_bundle_to_read over a list in bulk queries instead of the per-bundle N+1."""
    from sqlalchemy import select as _select

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
    era_map = _eras_for_environments({c.environment_item_id for c in bundles}, db)

    reads: list[AppItemBundleRead] = []
    for c in bundles:
        read = AppItemBundleRead.model_validate(c)
        read.items = leaves_by_bundle.get(c.id, [])
        read.tags = tag_map.get(c.id, [])
        read.era = era_map.get(c.environment_item_id)
        reads.append(read)
    return reads
