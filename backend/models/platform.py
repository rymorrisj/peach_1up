from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, func
from sqlmodel import Field, SQLModel
from backend.constants_generated import EmulatorCatalogSlug, EraValue, HardwareProfile


class PlatformBase(SQLModel):
    name: str
    era: EraValue = Field(sa_column=Column(String, nullable=False))
    emulator_slug: EmulatorCatalogSlug = Field(sa_column=Column(String, nullable=False))
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
    hardware_profile: HardwareProfile = Field(default="standard", sa_column=Column(String, nullable=False))
    machine_override: Optional[str] = None
    launch_commands: Optional[list[str]] = Field(default=None, sa_column=Column(JSON))


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
    era: Optional[EraValue] = None
    emulator_slug: Optional[EmulatorCatalogSlug] = None
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
    hardware_profile: Optional[HardwareProfile] = None
    machine_override: Optional[str] = None
    launch_commands: Optional[list[str]] = None


class PlatformRead(PlatformBase):
    id: int
    slug: Optional[str] = None
    profile_id: Optional[int] = None
    last_health_check: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    working_image_size_bytes: Optional[int] = None
    base_image_size_bytes: Optional[int] = None


class StorageStats(SQLModel):
    drive_images_bytes: int
    source_media_bytes: int
    os_images_bytes: int
    emulator_binaries_bytes: int


class PlatformHealthCounts(SQLModel):
    total: int
    healthy: int
    degraded: int
    unconfigured: int


class CountTotal(SQLModel):
    total: int


class InstalledCounts(SQLModel):
    total: int
    installed: int


class BiosCounts(SQLModel):
    total: int
    present: int


class HealthSummary(SQLModel):
    platforms: PlatformHealthCounts
    library: CountTotal
    drives: CountTotal
    extensions: CountTotal
    emulators: InstalledCounts
    bios: BiosCounts
    rom_packs: InstalledCounts
