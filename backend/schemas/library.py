from datetime import datetime

from pydantic import BaseModel, ConfigDict

from backend.schemas.tag import TagRead


class LibraryItemBase(BaseModel):
    title: str
    sort_title: str | None = None
    era: str
    category: str | None = None
    media_path: str
    media_type: str | None = None
    platform_id: int | None = None
    profile_id: int | None = None
    cover_art_path: str | None = None
    description: str | None = None
    publisher: str | None = None
    year: int | None = None
    igdb_id: int | None = None
    metadata_source: str | None = None


class LibraryItemCreate(LibraryItemBase):
    pass


class LibraryItemUpdate(BaseModel):
    title: str | None = None
    sort_title: str | None = None
    era: str | None = None
    category: str | None = None
    media_path: str | None = None
    media_type: str | None = None
    platform_id: int | None = None
    profile_id: int | None = None
    cover_art_path: str | None = None
    description: str | None = None
    publisher: str | None = None
    year: int | None = None
    igdb_id: int | None = None
    metadata_source: str | None = None


class LibraryItemRead(LibraryItemBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    last_launched_at: datetime | None
    launch_count: int
    created_at: datetime
    updated_at: datetime
