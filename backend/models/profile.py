from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, func
from sqlmodel import Field, SQLModel


class ProfileBase(SQLModel):
    name: str
    slug: str = Field(unique=True)
    emulator_slug: str
    era: str
    config_path: Optional[str] = None
    extra_args: Optional[str] = None
    is_bundled: bool = False
    is_accuracy_mode: bool = False
    enable_networking: bool = False
    notes: Optional[str] = None


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
    emulator_slug: Optional[str] = None
    era: Optional[str] = None
    config_path: Optional[str] = None
    extra_args: Optional[str] = None
    is_accuracy_mode: Optional[bool] = None
    enable_networking: Optional[bool] = None
    notes: Optional[str] = None


class ProfileRead(ProfileBase):
    id: int
    created_at: datetime
    updated_at: datetime
