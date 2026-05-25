import re
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, func
from sqlmodel import Field, SQLModel

_SLUG_RE = re.compile(r"^[a-z0-9-]+$")


class DriveBase(SQLModel):
    slug: str = Field(unique=True)
    name: str
    size_mb: int = 500
    era: str


class Drive(DriveBase, table=True):
    __tablename__ = "drives"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )


class DriveCreate(DriveBase):
    pass


class DriveRead(DriveBase):
    id: int
    created_at: datetime
