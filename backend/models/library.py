from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Table, func
from sqlmodel import Field, SQLModel


library_item_tag = Table(
    "library_item_tags",
    SQLModel.metadata,
    Column("library_item_id", Integer, ForeignKey("library_items.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class LibraryItemBase(SQLModel):
    title: str
    sort_title: Optional[str] = None
    era: str
    category: Optional[str] = None
    media_path: str
    media_type: Optional[str] = None
    cover_art_path: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[int] = None
    igdb_id: Optional[int] = None
    metadata_source: Optional[str] = None


class LibraryItem(LibraryItemBase, table=True):
    __tablename__ = "library_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    platform_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("platforms.id", ondelete="SET NULL"), nullable=True),
    )
    profile_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True),
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


class LibraryItemCreate(LibraryItemBase):
    platform_id: Optional[int] = None
    profile_id: Optional[int] = None


class LibraryItemUpdate(SQLModel):
    title: Optional[str] = None
    sort_title: Optional[str] = None
    era: Optional[str] = None
    category: Optional[str] = None
    media_path: Optional[str] = None
    media_type: Optional[str] = None
    platform_id: Optional[int] = None
    profile_id: Optional[int] = None
    cover_art_path: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[int] = None
    igdb_id: Optional[int] = None
    metadata_source: Optional[str] = None


class LibraryItemRead(LibraryItemBase):
    id: int
    platform_id: Optional[int] = None
    profile_id: Optional[int] = None
    last_launched_at: Optional[datetime] = None
    launch_count: int
    created_at: datetime
    updated_at: datetime
