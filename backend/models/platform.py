from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, func
from sqlmodel import Field, SQLModel


class PlatformBase(SQLModel):
    name: str
    era: str
    emulator_slug: str
    base_image_path: Optional[str] = None
    working_image_path: Optional[str] = None
    config_path: Optional[str] = None
    status: str = "unknown"
    notes: Optional[str] = None
    is_system: bool = False
    download_url: Optional[str] = None
    supported_eras: Optional[str] = None
    default_flags: Optional[str] = None
    installed_at: Optional[datetime] = None


class Platform(PlatformBase, table=True):
    __tablename__ = "platforms"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: Optional[str] = Field(default=None, unique=True)
    profile_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True),
    )
    last_health_check: Optional[datetime] = None
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False),
    )


class PlatformCreate(PlatformBase):
    slug: Optional[str] = None
    profile_id: Optional[int] = None


class PlatformUpdate(SQLModel):
    name: Optional[str] = None
    era: Optional[str] = None
    emulator_slug: Optional[str] = None
    profile_id: Optional[int] = None
    base_image_path: Optional[str] = None
    working_image_path: Optional[str] = None
    config_path: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    slug: Optional[str] = None
    download_url: Optional[str] = None
    supported_eras: Optional[str] = None
    default_flags: Optional[str] = None
    installed_at: Optional[datetime] = None


class PlatformRead(PlatformBase):
    id: int
    slug: Optional[str] = None
    profile_id: Optional[int] = None
    last_health_check: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
