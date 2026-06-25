from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlmodel import Field, SQLModel
from backend.constants_generated import EmulatorCatalogSlug


class LaunchHistoryBase(SQLModel):
    target_type: str = "library_item"
    emulator_slug: EmulatorCatalogSlug = Field(sa_column=Column(String, nullable=False))
    network_blocked: bool = True
    job_isolated: bool = False
    sandboxed: bool = False
    sandbox_memory_limit_mb: Optional[int] = None
    sandbox_cpu_limit_percent: Optional[int] = None


class LaunchHistory(LaunchHistoryBase, table=True):
    __tablename__ = "launch_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    library_item_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("library_items.id", ondelete="CASCADE"), nullable=True),
    )
    library_set_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("library_sets.id", ondelete="CASCADE"), nullable=True),
    )
    platform_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("platforms.id", ondelete="CASCADE"), nullable=True),
    )
    profile_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True),
    )
    started_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
    ended_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    error_message: Optional[str] = None


class LaunchHistoryRead(LaunchHistoryBase):
    id: int
    library_item_id: Optional[int] = None
    library_set_id: Optional[int] = None
    platform_id: Optional[int] = None
    profile_id: Optional[int] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    error_message: Optional[str] = None
