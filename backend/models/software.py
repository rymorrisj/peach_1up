from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import model_validator
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, func
from sqlmodel import Field, Relationship, SQLModel

from backend.constants import PC_ERAS
from backend.constants_generated import EraValue, FileType, ItemType
from backend.models.drive import Drive, DriveRead
from backend.models.tag import TagRead, get_tags_for_entities, get_tags_for_entity

_YEAR_MIN = 1970
_YEAR_MAX = 2050

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Leaf entity: SoftwareItem (one disc / media record within a collection).
# Renamed from the former LibrarySetItem; single-disc games are collections-of-one.
# ---------------------------------------------------------------------------

class SoftwareItem(SQLModel, table=True):
    __tablename__ = "software_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    library_collection_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("software_collections.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    disc_number: int = 1
    file_path: str = Field(sa_column=Column(String, nullable=False, index=True))
    executable_path: Optional[str] = None
    cover_art_path: Optional[str] = None
    file_type: Optional[FileType] = Field(default=None, sa_column=Column(String))
    folder_path: Optional[str] = Field(default=None, index=True)
    detection_reason: Optional[str] = None
    file_size_bytes: Optional[int] = None
    # One-time snapshot of the source folder/file name at import time, before
    # any slug-based rename. Lets a later scan match a disk path back to this
    # row even after the on-disk name has since diverged from the DB slug.
    original_name: Optional[str] = None
    # True only when folder_path was created/renamed exclusively for this item
    # (or, for a multi-disc set, this collection) by the ingest pipeline itself
    # — safe to rmtree on delete. False/None means folder_path is a pre-existing
    # directory the ingest pipeline does not own (e.g. the parent of a loose
    # file ingested with no MEDIA_PATH configured) and must never be rmtree'd;
    # None covers rows written before this column existed, treated the same as
    # False. See _delete_leaf_media_folders.
    folder_owned: Optional[bool] = None
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False),
    )

    library_collection: Optional["SoftwareCollection"] = Relationship(
        back_populates="items"
    )

class SoftwareItemRead(SQLModel):
    id: int
    library_collection_id: int
    disc_number: int
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
    def _compute_cover_art_url(self) -> "SoftwareItemRead":
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

class SoftwareItemUpdate(SQLModel):
    executable_path: Optional[str] = None
    cover_art_path: Optional[str] = None


class SoftwareItemReorder(SQLModel):
    # Every leaf id belonging to the collection, top-to-bottom. The first id
    # becomes the new launch disc. disc_number columns are existing data, not
    # a schema change — this only adds a write path for them.
    disc_order: list[int]

# ---------------------------------------------------------------------------
# Parent entity: SoftwareCollection (the game / collection). Renamed from LibrarySet;
# owns metadata, the writable drive (DOS), and the ordered leaf list.
# ---------------------------------------------------------------------------


def derive_item_type(era: EraValue) -> ItemType:
    """era is the source of truth for item_type: PC eras -> "pc", everything else -> "console"."""
    return "pc" if era in PC_ERAS else "console"


class SoftwareCollection(SQLModel, table=True):
    __tablename__ = "software_collections"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: Optional[str] = Field(default=None, index=True, unique=True)
    title: str
    sort_title: Optional[str] = None
    era: EraValue = Field(sa_column=Column(String, nullable=False))
    # Derived-and-validated from era on write (see _derive_item_type_from_era below);
    # default=None only so construction can omit it before the validator fills it in —
    # the stored column is NOT NULL.
    item_type: ItemType = Field(default=None, sa_column=Column(String, nullable=False))
    category: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    developer: Optional[str] = None
    year: Optional[int] = None
    external_game_id: Optional[int] = None
    metadata_source: Optional[str] = None
    content_rating: Optional[str] = Field(default=None, index=True)
    launch_commands: Optional[list[str]] = Field(default=None, sa_column=Column(JSON))
    installed: bool = False
    requires_install: bool = False
    launch_review_flagged: bool = Field(default=False)
    # None = inherit the global delete_media_on_removal setting. True/False
    # explicitly overrides it for this collection only.
    delete_media_override: Optional[bool] = None

    environment_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("environments.id", ondelete="SET NULL"), nullable=True),
    )
    profile_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True),
    )
    drive_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("drives.id"), nullable=True),
    )
    # Logical FKs to software_items.id. Not DB-level constraints to avoid a circular
    # reference between software_collections and software_items during table creation.
    launch_disk_id: Optional[int] = Field(default=None)
    # Which leaf's art is shown as the stack front-face. Falls back to launch_disk_id when null.
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

    items: list["SoftwareItem"] = Relationship(
        back_populates="library_collection",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "order_by": "SoftwareItem.disc_number",
        },
    )

    drive: Optional["Drive"] = Relationship(
        back_populates="software_collection",
        sa_relationship_kwargs={
            "foreign_keys": "Drive.software_collection_id",
            "uselist": False,
        },
    )

    @model_validator(mode="after")
    def _derive_item_type_from_era(self) -> "SoftwareCollection":
        derived = derive_item_type(self.era)
        if self.item_type is not None and self.item_type != derived:
            raise ValueError(
                f"item_type {self.item_type!r} conflicts with era {self.era!r} "
                f"(era implies {derived!r}). item_type is derived from era, not independently settable."
            )
        self.item_type = derived
        return self


class SoftwareCollectionCreate(SQLModel):
    title: str
    file_path: str
    era: EraValue = "unknown"
    profile_id: Optional[int] = None


class SoftwareCollectionUpdate(SQLModel):
    title: Optional[str] = None
    sort_title: Optional[str] = None
    era: Optional[EraValue] = None
    category: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[int] = Field(default=None, ge=_YEAR_MIN, le=_YEAR_MAX)
    external_game_id: Optional[int] = None
    metadata_source: Optional[str] = None
    content_rating: Optional[str] = None
    launch_commands: Optional[list[str]] = None
    launch_review_flagged: Optional[bool] = None
    installed: Optional[bool] = None
    requires_install: Optional[bool] = None
    delete_media_override: Optional[bool] = None
    environment_id: Optional[int] = None
    profile_id: Optional[int] = None
    display_disk_id: Optional[int] = None
    launch_disk_id: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def _reject_dead_fields(cls, data: object) -> object:
        if isinstance(data, dict) and "drive_size_mb" in data:
            raise ValueError(
                "drive_size_mb is not a valid update field and has no database column."
            )
        return data


class SoftwareCollectionRead(SQLModel):
    id: int
    slug: Optional[str] = None
    title: str
    sort_title: Optional[str] = None
    era: str
    category: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    developer: Optional[str] = None
    genres: list[str] = []
    year: Optional[int] = None
    external_game_id: Optional[int] = None
    metadata_source: Optional[str] = None
    content_rating: Optional[str] = None
    launch_commands: Optional[list[str]] = None
    installed: bool = False
    requires_install: bool = False
    launch_review_flagged: bool = False
    delete_media_override: Optional[bool] = None
    environment_id: Optional[int] = None
    profile_id: Optional[int] = None
    drive_id: Optional[int] = None
    launch_disk_id: Optional[int] = None
    display_disk_id: Optional[int] = None
    last_launched_at: Optional[datetime] = None
    launch_count: int = 0
    created_at: datetime
    updated_at: datetime
    items: list[SoftwareItemRead] = []
    drive: Optional[DriveRead] = None
    tags: list[TagRead] = []
    # Pre-launch UX gate (doc 02 A5 part B): set to "no_environment" when this
    # is a PC collection with no resolvable Environment (neither environment_id
    # nor an era-matched system Environment fallback). Always None for console
    # items. Computed at read time in collection_to_read / collections_to_read_bulk,
    # not stored.
    launch_blocked_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Scan / import DTOs (unchanged shape).
# ---------------------------------------------------------------------------


class ScanPreviewItem(SQLModel):
    title: str
    file_path: str
    detected_era: Optional[str] = None
    is_loose: bool
    is_zip: bool


class ScanStatus(SQLModel):
    running: bool
    job_id: Optional[str] = None
    error: Optional[str] = None


class ImportErrorItem(SQLModel):
    path: str
    reason: str


class ImportResult(SQLModel):
    imported: int
    skipped: int
    errors: list[ImportErrorItem]


# ---------------------------------------------------------------------------
# Read-model builders.
# ---------------------------------------------------------------------------


def _leaf_to_read(leaf: SoftwareItem) -> Optional[SoftwareItemRead]:
    """Validate one leaf into a SoftwareItemRead, isolating a single bad row.

    A leaf whose DB-persisted ``file_type`` predates the current FileType
    vocabulary (the column is a bare String and enforces no Literal) would raise
    ValidationError and, unguarded, 500 the entire GET /library list. Here that
    failure is contained to the offending row: the file_type is coerced to None
    and the row still renders (degrade). If it still cannot validate, the row is
    dropped from the response (skip) with a logged warning rather than taking the
    whole list down with it.
    """
    from pydantic import ValidationError

    from backend.core.logger import get_logger

    try:
        return SoftwareItemRead.model_validate(leaf)
    except ValidationError as exc:
        log = get_logger(__name__)
        leaf_id = getattr(leaf, "id", None)
        log.warning(
            "Library item %s failed read validation (%s); serving with file_type "
            "nulled. This usually means a file_type value not in the current "
            "FileType set was persisted before validation existed.",
            leaf_id, exc,
        )
        try:
            payload = {
                name: getattr(leaf, name, None)
                for name in SoftwareItemRead.model_fields
                if name != "cover_art_url"
            }
            payload["file_type"] = None
            return SoftwareItemRead.model_validate(payload)
        except ValidationError as exc2:
            log.warning(
                "Library item %s is unreadable even after degrading file_type; "
                "dropping it from the response: %s",
                leaf_id, exc2,
            )
            return None


def _leaves_for_collection(collection_id: int, db: "Session") -> list[SoftwareItem]:
    from sqlalchemy import select as _select

    return list(
        db.execute(
            _select(SoftwareItem)
            .where(SoftwareItem.library_collection_id == collection_id)
            .order_by(SoftwareItem.disc_number)
        ).scalars().all()
    )


def _launch_blocked_reason(c: "SoftwareCollection", system_eras: set[str]) -> Optional[str]:
    """Returns "no_environment" iff *c* is a PC collection with no resolvable
    Environment (neither its own environment_id nor an era-matched is_system
    Environment fallback -- see coordinator._resolve_environment_for_pc_entity,
    the launch-time counterpart of this same resolution). None for console
    items and any PC item with a resolvable Environment."""
    if c.item_type != "pc":
        return None
    if c.environment_id is not None:
        return None
    if c.era in system_eras:
        return None
    return "no_environment"


def collection_to_read(c: "SoftwareCollection", db: "Session") -> SoftwareCollectionRead:
    """Build a SoftwareCollectionRead, nesting ordered leaves, tags, and genres."""
    from backend.models.metadata_lookup import get_genres_for_collection
    from backend.service.utils.era_defaults import system_environment_eras

    read = SoftwareCollectionRead.model_validate(c)
    read.items = [r for i in c.items if (r := _leaf_to_read(i)) is not None]
    read.tags = get_tags_for_entity("software_collection", c.id, db)
    read.genres = get_genres_for_collection(c.id, db)
    needed_eras = {c.era} if c.item_type == "pc" and c.environment_id is None else set()
    read.launch_blocked_reason = _launch_blocked_reason(c, system_environment_eras(needed_eras, db))
    return read


def collections_to_read_bulk(
    collections: list["SoftwareCollection"], db: "Session"
) -> list[SoftwareCollectionRead]:
    """collection_to_read over a list in three bulk queries total (all leaves,
    all tags, all genres) instead of the per-collection N+1."""
    from sqlalchemy import select as _select

    from backend.models.metadata_lookup import get_genres_for_collections
    from backend.service.utils.era_defaults import system_environment_eras

    if not collections:
        return []

    collection_ids = [c.id for c in collections]
    leaves = db.execute(
        _select(SoftwareItem)
        .where(SoftwareItem.library_collection_id.in_(collection_ids))
        .order_by(SoftwareItem.library_collection_id, SoftwareItem.disc_number)
    ).scalars().all()

    leaves_by_collection: dict[int, list[SoftwareItemRead]] = {}
    for leaf in leaves:
        leaf_read = _leaf_to_read(leaf)
        if leaf_read is None:
            continue
        leaves_by_collection.setdefault(leaf.library_collection_id, []).append(leaf_read)

    tag_map = get_tags_for_entities("software_collection", collection_ids, db)
    genre_map = get_genres_for_collections(collection_ids, db)

    # One batched query for every era that might need the system-Environment
    # fallback, instead of a per-collection lookup (N+1).
    needed_eras = {
        c.era for c in collections if c.item_type == "pc" and c.environment_id is None
    }
    system_eras = system_environment_eras(needed_eras, db)

    reads: list[SoftwareCollectionRead] = []
    for c in collections:
        read = SoftwareCollectionRead.model_validate(c)
        read.items = leaves_by_collection.get(c.id, [])
        read.tags = tag_map.get(c.id, [])
        read.genres = genre_map.get(c.id, [])
        read.launch_blocked_reason = _launch_blocked_reason(c, system_eras)
        reads.append(read)
    return reads
