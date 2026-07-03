from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from pydantic import field_validator, model_validator
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, func
from sqlmodel import Field, Relationship, SQLModel
from backend.constants_generated import EraValue, MediaType
from backend.models.tag import TagRead, get_tags_for_entities, get_tags_for_entity
from backend.models.drive import DriveRead

if TYPE_CHECKING:
    from backend.models.drive import Drive
    from backend.models.tag import Tag
    from sqlalchemy.orm import Session


class LibraryItemBase(SQLModel):
    title: str
    sort_title: Optional[str] = None
    era: EraValue = Field(sa_column=Column(String, nullable=False))
    category: Optional[str] = None
    media_path: str
    media_type: Optional[MediaType] = Field(default=None, sa_column=Column(String))
    folder_path: Optional[str] = Field(default=None, index=True)
    cover_art_path: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[int] = None
    igdb_id: Optional[int] = None
    metadata_source: Optional[str] = None
    content_rating: Optional[str] = Field(default=None, index=True)
    executable_path: Optional[str] = None
    launch_commands: Optional[list[str]] = Field(default=None, sa_column=Column(JSON))
    launch_review_flagged: bool = Field(default=False)
    installed: bool = False
    requires_install: bool = False
    detection_reason: Optional[str] = None
    file_size_bytes: Optional[int] = None


class LibraryItem(LibraryItemBase, table=True):
    __tablename__ = "library_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: Optional[str] = Field(default=None, index=True, unique=True)
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

    drive: Optional["Drive"] = Relationship(
        back_populates="library_item",
        sa_relationship_kwargs={
            "foreign_keys": "[Drive.library_item_id]",
            "uselist": False,
        },
    )


class LibraryItemCreate(LibraryItemBase):
    era: EraValue = "unknown"
    platform_id: Optional[int] = None
    profile_id: Optional[int] = None


_YEAR_MIN = 1970
_YEAR_MAX = 2050


class LibraryItemUpdate(SQLModel):
    title: Optional[str] = None
    sort_title: Optional[str] = None
    era: Optional[EraValue] = None
    category: Optional[str] = None
    media_path: Optional[str] = None
    media_type: Optional[MediaType] = None
    folder_path: Optional[str] = None
    platform_id: Optional[int] = None
    profile_id: Optional[int] = None
    cover_art_path: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[int] = Field(default=None, ge=_YEAR_MIN, le=_YEAR_MAX)
    igdb_id: Optional[int] = None
    metadata_source: Optional[str] = None
    content_rating: Optional[str] = None
    executable_path: Optional[str] = None
    launch_commands: Optional[list[str]] = None
    launch_review_flagged: Optional[bool] = None
    installed: Optional[bool] = None
    # drive_size_mb intentionally absent — no DB column; requests containing it are rejected below.

    @model_validator(mode="before")
    @classmethod
    def _reject_dead_fields(cls, data: object) -> object:
        if isinstance(data, dict) and "drive_size_mb" in data:
            raise ValueError(
                "drive_size_mb is not a valid update field and has no database column."
            )
        return data


class LibraryItemRead(LibraryItemBase):
    id: int
    slug: Optional[str] = None
    platform_id: Optional[int] = None
    profile_id: Optional[int] = None
    drive_id: Optional[int] = None
    last_launched_at: Optional[datetime] = None
    launch_count: int
    created_at: datetime
    updated_at: datetime
    launch_commands: Optional[list[str]] = None
    launch_review_flagged: bool = False
    installed: bool = False
    detection_reason: Optional[str] = None
    cover_art_url: Optional[str] = None
    drive: Optional[DriveRead] = None
    tags: list[TagRead] = []

    @model_validator(mode='after')
    def _compute_cover_art_url(self) -> 'LibraryItemRead':
        if not self.cover_art_path:
            return self
        try:
            from backend.service.utils import settings as _s
            lib_root = Path(_s.get("LIBRARY_PATH"))
            rel = Path(self.cover_art_path).resolve().relative_to(lib_root.resolve())
            self.cover_art_url = '/media/' + rel.as_posix()
        except ValueError:
            pass
        return self


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


def item_to_read(item: "LibraryItem", db: "Session") -> LibraryItemRead:
    """Build a LibraryItemRead from a LibraryItem ORM object, populating tags via entity_tags."""
    read = LibraryItemRead.model_validate(item)
    read.tags = get_tags_for_entity("library_item", item.id, db)
    return read


def items_to_read_bulk(items: list["LibraryItem"], db: "Session") -> list[LibraryItemRead]:
    """Like ``[item_to_read(i, db) for i in items]`` but loads every item's tags
    in a single query instead of one per item (removes the N+1)."""
    reads = [LibraryItemRead.model_validate(i) for i in items]
    tag_map = get_tags_for_entities("library_item", [i.id for i in items], db)
    for read, item in zip(reads, items):
        read.tags = tag_map.get(item.id, [])
    return reads
