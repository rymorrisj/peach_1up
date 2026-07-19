from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, func
from sqlmodel import Field, SQLModel
from backend.constants_generated import EmulatorCatalogSlug, EraValue, HardwareProfile


class EnvironmentItemBase(SQLModel):
    name: str
    era: EraValue = Field(sa_column=Column(String, nullable=False))
    emulator_slug: EmulatorCatalogSlug = Field(sa_column=Column(String, nullable=False))
    base_image_path: Optional[str] = None
    working_image_path: Optional[str] = None
    config_path: Optional[str] = None
    notes: Optional[str] = None
    is_system: bool = False
    download_url: Optional[str] = None
    supported_eras: Optional[str] = None
    default_flags: Optional[str] = None
    # Whether the OS itself has been installed into this Environment (distinct
    # from any software-item-level installed flag, e.g. GameItemBundle.installed
    #, different entity). Already existed as a "Mark as Installed" affordance
    # in EnvironmentCard.tsx before this change; now also read as the
    # environment_is_installed() launch gate (era_defaults.py) instead of a new
    # duplicate is_installed boolean. Meaningful for Win9x/WinXP under 86Box;
    # DOS/DOSBox-X environments have no install step and are always treated as
    # installed regardless of this value (see environment_is_installed).
    installed_at: Optional[datetime] = None
    hardware_profile: HardwareProfile = Field(default="standard", sa_column=Column(String, nullable=False))
    machine_override: Optional[str] = None
    launch_commands: Optional[list[str]] = Field(default=None, sa_column=Column(JSON))


class EnvironmentItem(EnvironmentItemBase, table=True):
    __tablename__ = "environment_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: Optional[str] = Field(default=None, unique=True)
    profile_item_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("profile_items.id", ondelete="SET NULL"), nullable=True),
    )
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False),
    )


class EnvironmentItemCreate(EnvironmentItemBase):
    slug: Optional[str] = None
    profile_item_id: Optional[int] = None


class EnvironmentItemUpdate(SQLModel):
    name: Optional[str] = None
    era: Optional[EraValue] = None
    emulator_slug: Optional[EmulatorCatalogSlug] = None
    profile_item_id: Optional[int] = None
    base_image_path: Optional[str] = None
    working_image_path: Optional[str] = None
    config_path: Optional[str] = None
    notes: Optional[str] = None
    slug: Optional[str] = None
    download_url: Optional[str] = None
    supported_eras: Optional[str] = None
    default_flags: Optional[str] = None
    installed_at: Optional[datetime] = None
    hardware_profile: Optional[HardwareProfile] = None
    machine_override: Optional[str] = None
    launch_commands: Optional[list[str]] = None


class EnvironmentItemRead(EnvironmentItemBase):
    id: int
    slug: Optional[str] = None
    profile_item_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    working_image_size_bytes: Optional[int] = None
    base_image_size_bytes: Optional[int] = None
    # Live presence check, computed fresh on every read (list/get), never
    # persisted — same philosophy as check_bios_presence: does the on-disk
    # state needed to actually launch through this Environment exist right
    # now. See compute_environment_presence.
    is_present: bool = False


class StorageStats(SQLModel):
    drive_images_bytes: int
    source_media_bytes: int
    os_images_bytes: int
    emulator_binaries_bytes: int


class EnvironmentItemHealthCounts(SQLModel):
    total: int
    present: int


class CountTotal(SQLModel):
    total: int


class InstalledCounts(SQLModel):
    total: int
    installed: int


class BiosCounts(SQLModel):
    total: int
    present: int


class HealthSummary(SQLModel):
    environments: EnvironmentItemHealthCounts
    library: CountTotal
    drives: CountTotal
    extensions: CountTotal
    emulators: InstalledCounts
    bios: BiosCounts
    rom_packs: InstalledCounts
