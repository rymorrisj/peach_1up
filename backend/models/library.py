from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from pydantic import model_validator
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, func
from sqlmodel import Field, Relationship, SQLModel
from backend.models.tag import LibraryItemTag

if TYPE_CHECKING:
    from backend.models.drive import Drive
    from backend.models.tag import Tag


class LibraryItemBase(SQLModel):
    title: str
    sort_title: Optional[str] = None
    era: str
    category: Optional[str] = None
    media_path: str
    media_type: Optional[str] = None
    folder_path: Optional[str] = None
    cover_art_path: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[int] = None
    igdb_id: Optional[int] = None
    metadata_source: Optional[str] = None
    content_rating: Optional[str] = None
    executable_path: Optional[str] = None
    launch_commands: Optional[list[str]] = Field(default=None, sa_column=Column(JSON))
    launch_review_flagged: bool = Field(default=False)
    installed: bool = False
    requires_install: bool = False


class LibraryItem(LibraryItemBase, table=True):
    __tablename__ = "library_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: Optional[str] = Field(default=None)
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

    tags: list["Tag"] = Relationship(
        back_populates="library_items",
        link_model=LibraryItemTag,
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
    folder_path: Optional[str] = None
    platform_id: Optional[int] = None
    profile_id: Optional[int] = None
    cover_art_path: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[int] = None
    igdb_id: Optional[int] = None
    metadata_source: Optional[str] = None
    content_rating: Optional[str] = None
    executable_path: Optional[str] = None
    launch_commands: Optional[list[str]] = None
    launch_review_flagged: Optional[bool] = None
    installed: Optional[bool] = None
    drive_size_mb: Optional[int] = None


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
    cover_art_url: Optional[str] = None

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
