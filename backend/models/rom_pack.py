from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, String, func
from sqlmodel import Field, SQLModel


class RomPackItem(SQLModel, table=True):
    __tablename__ = "rom_pack_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: Optional[str] = Field(default=None, sa_column=Column(String, unique=True, index=True))
    name: str
    emulator_slug: str
    install_path: Optional[str] = None
    source_url: Optional[str] = None
    is_present: bool = Field(sa_column=Column(Boolean, nullable=False, default=False))
    installed_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False),
    )


class RomPackItemRead(SQLModel):
    id: Optional[int] = None
    slug: Optional[str] = None
    name: str
    emulator_slug: str
    install_path: Optional[str] = None
    source_url: Optional[str] = None
    is_present: bool
    installed_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
