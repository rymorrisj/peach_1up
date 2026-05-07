from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, func
from sqlmodel import Field, SQLModel


class SnapshotBase(SQLModel):
    name: str
    image_path: str
    size_bytes: Optional[int] = None
    notes: Optional[str] = None


class Snapshot(SnapshotBase, table=True):
    __tablename__ = "snapshots"

    id: Optional[int] = Field(default=None, primary_key=True)
    platform_id: int = Field(
        sa_column=Column(Integer, ForeignKey("platforms.id", ondelete="CASCADE"), nullable=False)
    )
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )


class SnapshotCreate(SQLModel):
    name: str
    notes: Optional[str] = None


class SnapshotRead(SnapshotBase):
    id: int
    platform_id: int
    created_at: datetime
