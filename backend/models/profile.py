from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column, DateTime, String, func
from sqlmodel import Field, SQLModel
from backend.constants_generated import EmulatorCatalogSlug, EraValue


class ProfileBase(SQLModel):
    name: str = Field(unique=True)
    slug: str = Field(unique=True)
    emulator_slug: EmulatorCatalogSlug = Field(sa_column=Column(String, nullable=False))
    era: EraValue = Field(sa_column=Column(String, nullable=False))
    config_path: Optional[str] = None
    extra_args: Optional[str] = None
    is_bundled: bool = False
    enable_networking: bool = False
    enable_dgvoodoo2: bool = False
    notes: Optional[str] = None
    user_id: Optional[int] = None
    launch_commands: Optional[list[str]] = Field(default=None, sa_column=Column(JSON))
    drive_slug: Optional[str] = None
    use_drive: bool = True
    container_enabled: Optional[bool] = None


class Profile(ProfileBase, table=True):
    __tablename__ = "profiles"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False),
    )


class ProfileCreate(ProfileBase):
    pass


class ProfileUpdate(SQLModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    emulator_slug: Optional[EmulatorCatalogSlug] = None
    era: Optional[EraValue] = None
    config_path: Optional[str] = None
    extra_args: Optional[str] = None
    enable_networking: Optional[bool] = None
    enable_dgvoodoo2: Optional[bool] = None
    notes: Optional[str] = None
    launch_commands: Optional[list[str]] = None
    drive_slug: Optional[str] = None
    use_drive: Optional[bool] = None
    container_enabled: Optional[bool] = None


class ProfileRead(ProfileBase):
    id: int
    user_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    item_count: int = 0
    total_launches: int = 0
    last_launched_at: Optional[datetime] = None
