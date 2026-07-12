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
# Leaf entity: AppItem (one file/part within an app collection). Mirrors
# SoftwareItem (backend/models/software.py) minus disc_number — apps have no
# disc-swap concept, so items are ordered by id (insertion order) rather than
# an explicit position column. Most apps are single-item; the collection/item
# split exists mainly for multi-part installs.
# ---------------------------------------------------------------------------


class AppItem(SQLModel, table=True):
    __tablename__ = "app_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    app_collection_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("app_collections.id", ondelete="CASCADE"),
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
    # Same semantics as SoftwareItem.folder_owned: True only when folder_path
    # was created/renamed exclusively for this item by the app's own create
    # flow — safe to rmtree on delete. False/None means folder_path is a
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

    app_collection: Optional["AppCollection"] = Relationship(back_populates="items")


class AppItemRead(SQLModel):
    id: int
    app_collection_id: int
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
        # Same pattern as SoftwareItemRead._compute_cover_art_url.
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
# Parent entity: AppCollection. Mirrors SoftwareCollection deliberately (see
# backend/models/software.py) but is always PC — there is no console case, no
# era-driven launch fallback, and no item_type column. environment_id is
# required and non-nullable: an App with no verified Environment is not a
# creatable entity, unlike PC Software where environment_id may start null
# and be backfilled later.
#
# era is deliberately NOT stored here. SoftwareCollection stores era
# redundantly alongside environment_id because console SoftwareCollections
# have no Environment to derive it from (era is the only source of truth for
# those rows) and because item_type is validated against era on every write.
# Neither condition applies to Apps: they are always PC, always carry a
# non-null environment_id, and have no item_type. Storing era again here
# would just be a second, independently-driftable copy of a value the linked
# Environment already owns — derive it at read time instead (see
# app_to_read/apps_to_read_bulk below).
#
# content_rating is dropped rather than carried over. SECURITY.md's rationale
# for MediaRestriction (manual per-user restriction, no automatic rating
# filter) is that there is no reliable signal to derive or enforce a rating
# for archival media — the same reasoning applies here even more directly:
# utility software (a calculator, a CAD package, an old Word install) has no
# age-rating concept at all, not just an undetectable one. launch_review_flagged
# is dropped alongside it since that flag exists specifically to gate a launch
# pending content-rating review.
# ---------------------------------------------------------------------------


class AppCollection(SQLModel, table=True):
    __tablename__ = "app_collections"

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
    # explicitly overrides it for this collection only.
    delete_media_override: Optional[bool] = None

    # Required, non-nullable: an App without a verified Environment is
    # meaningless and must never exist in a creatable state (doc 02 A5's
    # "environment required" backfill window does not apply here — there is
    # no legacy Apps data to migrate). RESTRICT (not SET NULL, which would
    # violate this column's NOT NULL constraint) so deleting an in-use
    # Environment fails loudly at the DB layer; the service layer
    # (environments.delete_platform) checks for referencing AppCollections
    # up front and returns a clean 409 before that constraint is ever hit.
    environment_id: int = Field(
        sa_column=Column(Integer, ForeignKey("environments.id", ondelete="RESTRICT"), nullable=False)
    )
    profile_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True),
    )
    drive_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("drives.id"), nullable=True),
    )
    # Logical FKs to app_items.id. Not DB-level constraints, mirroring
    # SoftwareCollection.launch_disk_id/display_disk_id (avoids a circular
    # reference between app_collections and app_items during table creation).
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
        back_populates="app_collection",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "order_by": "AppItem.id",
        },
    )

    drive: Optional["Drive"] = Relationship(
        back_populates="app_collection",
        sa_relationship_kwargs={
            "foreign_keys": "Drive.app_collection_id",
            "uselist": False,
        },
    )


class AppCollectionCreate(SQLModel):
    title: str
    file_path: str
    environment_id: int
    profile_id: Optional[int] = None


class AppCollectionUpdate(SQLModel):
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
    environment_id: Optional[int] = None
    profile_id: Optional[int] = None
    display_disk_id: Optional[int] = None
    launch_disk_id: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def _reject_null_environment(cls, data: object) -> object:
        # environment_id is NOT NULL at the DB level; reject an explicit null
        # here with a clear 422 instead of letting it fall through to an
        # IntegrityError. Omitting the field entirely (leaving it unset) is
        # fine and simply means "no change."
        if isinstance(data, dict) and "environment_id" in data and data["environment_id"] is None:
            raise ValueError("environment_id cannot be cleared; every App requires an Environment.")
        return data


class AppCollectionRead(SQLModel):
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
    environment_id: int
    profile_id: Optional[int] = None
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
    # module docstring above the AppCollection class for the reasoning).
    era: Optional[EraValue] = None


# ---------------------------------------------------------------------------
# Read-model builders — same shape as backend/models/software.py's
# collection_to_read / collections_to_read_bulk.
# ---------------------------------------------------------------------------


def _leaf_to_read(leaf: AppItem) -> Optional[AppItemRead]:
    """Validate one leaf into an AppItemRead, isolating a single bad row.

    Mirrors SoftwareItem's _leaf_to_read degrade-then-drop path so one row
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
    from backend.models.environment import Environment

    if not environment_ids:
        return {}
    rows = db.query(Environment.id, Environment.era).filter(Environment.id.in_(environment_ids)).all()
    return {row[0]: row[1] for row in rows}


def app_to_read(c: "AppCollection", db: "Session") -> AppCollectionRead:
    """Build an AppCollectionRead, nesting ordered leaves, tags, and the
    Environment-derived era."""
    read = AppCollectionRead.model_validate(c)
    read.items = [r for i in c.items if (r := _leaf_to_read(i)) is not None]
    read.tags = get_tags_for_entity("app_collection", c.id, db)
    read.era = _eras_for_environments({c.environment_id}, db).get(c.environment_id)
    return read


def apps_to_read_bulk(collections: list["AppCollection"], db: "Session") -> list[AppCollectionRead]:
    """app_to_read over a list in bulk queries instead of the per-collection N+1."""
    from sqlalchemy import select as _select

    if not collections:
        return []

    collection_ids = [c.id for c in collections]
    leaves = db.execute(
        _select(AppItem)
        .where(AppItem.app_collection_id.in_(collection_ids))
        .order_by(AppItem.app_collection_id, AppItem.id)
    ).scalars().all()

    leaves_by_collection: dict[int, list[AppItemRead]] = {}
    for leaf in leaves:
        leaf_read = _leaf_to_read(leaf)
        if leaf_read is None:
            continue
        leaves_by_collection.setdefault(leaf.app_collection_id, []).append(leaf_read)

    tag_map = get_tags_for_entities("app_collection", collection_ids, db)
    era_map = _eras_for_environments({c.environment_id for c in collections}, db)

    reads: list[AppCollectionRead] = []
    for c in collections:
        read = AppCollectionRead.model_validate(c)
        read.items = leaves_by_collection.get(c.id, [])
        read.tags = tag_map.get(c.id, [])
        read.era = era_map.get(c.environment_id)
        reads.append(read)
    return reads
