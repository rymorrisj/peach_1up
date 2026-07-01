import re
from datetime import datetime
from typing import Optional

from pydantic import field_validator
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


_SAFE_SNAPSHOT_NAME = re.compile(r"^[^/\\]+$")


class SnapshotCreate(SQLModel):
    name: str
    notes: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _no_path_separators(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Snapshot name must not be empty.")
        if not _SAFE_SNAPSHOT_NAME.match(v):
            raise ValueError("Snapshot name must not contain path separators (/ or \\).")
        return v


class SnapshotRead(SnapshotBase):
    id: int
    platform_id: int
    created_at: datetime
