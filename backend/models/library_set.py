from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from pydantic import model_validator
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlmodel import Field, SQLModel

from backend.constants_generated import EraValue
from backend.models.tag import TagRead, get_tags_for_entity

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class LibrarySetItem(SQLModel, table=True):
    __tablename__ = "library_set_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    set_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("library_sets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    disc_number: int
    media_path: str
    cover_art_path: Optional[str] = None
    executable_path: Optional[str] = None
    file_size_bytes: Optional[int] = None



class LibrarySet(SQLModel, table=True):
    __tablename__ = "library_sets"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    sort_title: Optional[str] = None
    era: EraValue = Field(sa_column=Column(String, nullable=False))
    category: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[int] = None
    igdb_id: Optional[int] = None
    metadata_source: Optional[str] = None
    content_rating: Optional[str] = Field(default=None, index=True)
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
        sa_column=Column(Integer, ForeignKey("drives.id", ondelete="SET NULL"), nullable=True),
    )
    # Logical FKs to library_set_items.id. Not DB-level constraints to avoid a circular
    # reference between library_sets and library_set_items during table creation.
    launch_disk_id: Optional[int] = Field(default=None)
    # Which item's art is shown as the stack front-face. Falls back to launch_disk_id when null.
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



class LibrarySetItemRead(SQLModel):
    id: int
    set_id: int
    disc_number: int
    media_path: str
    cover_art_path: Optional[str] = None
    cover_art_url: Optional[str] = None
    executable_path: Optional[str] = None
    file_size_bytes: Optional[int] = None

    @model_validator(mode="after")
    def _compute_cover_art_url(self) -> "LibrarySetItemRead":
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


class LibrarySetRead(SQLModel):
    id: int
    title: str
    sort_title: Optional[str] = None
    era: str
    category: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[int] = None
    igdb_id: Optional[int] = None
    metadata_source: Optional[str] = None
    content_rating: Optional[str] = None
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
    items: list[LibrarySetItemRead] = []
    tags: list[TagRead] = []


class LibrarySetItemUpdate(SQLModel):
    executable_path: Optional[str] = None


class LibrarySetUpdate(SQLModel):
    display_disk_id: Optional[int] = None
    title: Optional[str] = None
    sort_title: Optional[str] = None
    era: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[int] = None
    content_rating: Optional[str] = None
    platform_id: Optional[int] = None
    profile_id: Optional[int] = None


def set_to_read(s: LibrarySet, db: "Session") -> LibrarySetRead:
    """Build a LibrarySetRead from a LibrarySet ORM object.

    Items are loaded via a direct query (no ORM relationship) to avoid
    SQLAlchemy 2.x / SQLModel 0.0.x annotation compatibility issues with
    list[...] relationship types in same-file circular models.
    """
    from sqlalchemy import select as _select

    items_orm = db.execute(
        _select(LibrarySetItem)
        .where(LibrarySetItem.set_id == s.id)
        .order_by(LibrarySetItem.disc_number)
    ).scalars().all()

    read = LibrarySetRead.model_validate(s)
    read.items = [LibrarySetItemRead.model_validate(i) for i in items_orm]
    read.tags = get_tags_for_entity("library_set", s.id, db)
    return read
