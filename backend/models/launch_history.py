from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, func
from sqlmodel import Field, SQLModel


class LaunchHistoryBase(SQLModel):
    emulator_slug: str
    network_blocked: bool = True
    job_isolated: bool = False


class LaunchHistory(LaunchHistoryBase, table=True):
    __tablename__ = "launch_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    library_item_id: int = Field(
        sa_column=Column(Integer, ForeignKey("library_items.id", ondelete="CASCADE"), nullable=False)
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
    library_item_id: int
    profile_id: Optional[int] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    error_message: Optional[str] = None
