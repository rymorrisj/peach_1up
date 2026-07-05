from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import model_validator
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, func
from sqlmodel import Field, Relationship, SQLModel

from backend.constants_generated import EraValue, MediaType
from backend.models.drive import Drive, DriveRead
from backend.models.tag import TagRead, get_tags_for_entities, get_tags_for_entity

_YEAR_MIN = 1970
_YEAR_MAX = 2050

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Leaf entity: LibraryItem (one disc / media record within a collection).
# Renamed from the former LibrarySetItem; single-disc games are collections-of-one.
# ---------------------------------------------------------------------------

class LibraryItem(SQLModel, table=True):
    __tablename__ = "library_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    library_collection_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("library_collections.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    disc_number: int = 1
    media_path: str = Field(sa_column=Column(String, nullable=False, index=True))
    executable_path: Optional[str] = None
    cover_art_path: Optional[str] = None
    media_type: Optional[MediaType] = Field(default=None, sa_column=Column(String))
    folder_path: Optional[str] = Field(default=None, index=True)
    detection_reason: Optional[str] = None
    file_size_bytes: Optional[int] = None
    # One-time snapshot of the source folder/file name at import time, before
    # any slug-based rename. Lets a later scan match a disk path back to this
    # row even after the on-disk name has since diverged from the DB slug.
    original_name: Optional[str] = None
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False),
    )

    library_collection: Optional["LibraryCollection"] = Relationship(
        back_populates="items"
    )

class LibraryItemRead(SQLModel):
    id: int
    library_collection_id: int
    disc_number: int
    media_path: str
    executable_path: Optional[str] = None
    cover_art_path: Optional[str] = None
    cover_art_url: Optional[str] = None
    media_type: Optional[MediaType] = None
    folder_path: Optional[str] = None
    detection_reason: Optional[str] = None
    file_size_bytes: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _compute_cover_art_url(self) -> "LibraryItemRead":
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

class LibraryItemUpdate(SQLModel):
    executable_path: Optional[str] = None
    cover_art_path: Optional[str] = None

# ---------------------------------------------------------------------------
# Parent entity: LibraryCollection (the game / collection). Renamed from LibrarySet;
# owns metadata, the writable drive (DOS/win31), and the ordered leaf list.
# ---------------------------------------------------------------------------

class LibraryCollection(SQLModel, table=True):
    __tablename__ = "library_collections"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: Optional[str] = Field(default=None, index=True, unique=True)
    title: str
    sort_title: Optional[str] = None
    era: EraValue = Field(sa_column=Column(String, nullable=False))
    category: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[int] = None
    external_game_id: Optional[int] = None
    metadata_source: Optional[str] = None
    content_rating: Optional[str] = Field(default=None, index=True)
    launch_commands: Optional[list[str]] = Field(default=None, sa_column=Column(JSON))
    installed: bool = False
    requires_install: bool = False
    launch_review_flagged: bool = Field(default=False)

    platform_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("platforms.id", ondelete="SET NULL"), nullable=True),
    )
    profile_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True),
    )
    drive_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("drives.id"), nullable=True),
    )
    # Logical FKs to library_items.id. Not DB-level constraints to avoid a circular
    # reference between library_collections and library_items during table creation.
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

    items: list["LibraryItem"] = Relationship(
        back_populates="library_collection",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "order_by": "LibraryItem.disc_number",
        },
    )

    drive: Optional["Drive"] = Relationship(
        back_populates="library_collection",
        sa_relationship_kwargs={
            "foreign_keys": "Drive.library_collection_id",
            "uselist": False,
        },
    )


class LibraryCollectionCreate(SQLModel):
    title: str
    media_path: str
    era: EraValue = "unknown"
    profile_id: Optional[int] = None


class LibraryCollectionUpdate(SQLModel):
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
    platform_id: Optional[int] = None
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


class LibraryCollectionRead(SQLModel):
    id: int
    slug: Optional[str] = None
    title: str
    sort_title: Optional[str] = None
    era: str
    category: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[int] = None
    external_game_id: Optional[int] = None
    metadata_source: Optional[str] = None
    content_rating: Optional[str] = None
    launch_commands: Optional[list[str]] = None
    installed: bool = False
    requires_install: bool = False
    launch_review_flagged: bool = False
    platform_id: Optional[int] = None
    profile_id: Optional[int] = None
    drive_id: Optional[int] = None
    launch_disk_id: Optional[int] = None
    display_disk_id: Optional[int] = None
    last_launched_at: Optional[datetime] = None
    launch_count: int = 0
    created_at: datetime
    updated_at: datetime
    items: list[LibraryItemRead] = []
    drive: Optional[DriveRead] = None
    tags: list[TagRead] = []


# ---------------------------------------------------------------------------
# Scan / import DTOs (unchanged shape).
# ---------------------------------------------------------------------------


class ScanPreviewItem(SQLModel):
    title: str
    media_path: str
    detected_era: Optional[str] = None
    is_loose: bool
    is_zip: bool


class ScanStatus(SQLModel):
    running: bool
    preview: list[ScanPreviewItem]
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


def _leaves_for_collection(collection_id: int, db: "Session") -> list[LibraryItem]:
    from sqlalchemy import select as _select

    return list(
        db.execute(
            _select(LibraryItem)
            .where(LibraryItem.library_collection_id == collection_id)
            .order_by(LibraryItem.disc_number)
        ).scalars().all()
    )


def collection_to_read(c: "LibraryCollection", db: "Session") -> LibraryCollectionRead:
    """Build a LibraryCollectionRead, nesting ordered leaves and tags."""
    read = LibraryCollectionRead.model_validate(c)
    read.items = [LibraryItemRead.model_validate(i) for i in c.items]
    read.tags = get_tags_for_entity("library_collection", c.id, db)
    return read


def collections_to_read_bulk(
    collections: list["LibraryCollection"], db: "Session"
) -> list[LibraryCollectionRead]:
    """collection_to_read over a list in two bulk queries total (all leaves,
    then all tags) instead of the two-queries-per-collection N+1."""
    from sqlalchemy import select as _select

    if not collections:
        return []

    collection_ids = [c.id for c in collections]
    leaves = db.execute(
        _select(LibraryItem)
        .where(LibraryItem.library_collection_id.in_(collection_ids))
        .order_by(LibraryItem.library_collection_id, LibraryItem.disc_number)
    ).scalars().all()

    leaves_by_collection: dict[int, list[LibraryItemRead]] = {}
    for leaf in leaves:
        leaves_by_collection.setdefault(leaf.library_collection_id, []).append(
            LibraryItemRead.model_validate(leaf)
        )

    tag_map = get_tags_for_entities("library_collection", collection_ids, db)

    reads: list[LibraryCollectionRead] = []
    for c in collections:
        read = LibraryCollectionRead.model_validate(c)
        read.items = leaves_by_collection.get(c.id, [])
        read.tags = tag_map.get(c.id, [])
        reads.append(read)
    return reads