from datetime import datetime
from typing import Optional

from pydantic import model_validator
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlmodel import Field, SQLModel
from backend.constants_generated import EmulatorCatalogSlug


class LaunchHistoryBase(SQLModel):
    emulator_slug: EmulatorCatalogSlug = Field(sa_column=Column(String, nullable=False))
    network_blocked: bool = True
    job_isolated: bool = False
    sandboxed: bool = False
    sandbox_memory_limit_mb: Optional[int] = None
    sandbox_cpu_limit_percent: Optional[int] = None


class LaunchHistory(LaunchHistoryBase, table=True):
    __tablename__ = "launch_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    library_collection_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("software_collections.id", ondelete="CASCADE"), nullable=True),
    )
    platform_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("environments.id", ondelete="CASCADE"), nullable=True),
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
    library_collection_id: Optional[int] = None
    platform_id: Optional[int] = None
    profile_id: Optional[int] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    error_message: Optional[str] = None
    # Derived discriminator (not stored): a collection launch vs an environment launch.
    target_type: Optional[str] = None

    @model_validator(mode="after")
    def _derive_target_type(self) -> "LaunchHistoryRead":
        if self.library_collection_id is not None:
            self.target_type = "library_collection"
        elif self.platform_id is not None:
            self.target_type = "environment"
        return self
