from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, func
from sqlmodel import Field, SQLModel


class RestrictionType(str, Enum):
    rating = "rating"
    tag = "tag"
    media_id = "media_id"


class UserBase(SQLModel):
    name: str
    is_owner: bool = False
    pin_required: bool = False
    can_launch_media: bool = True
    can_edit_platforms: bool = False
    can_edit_library: bool = False
    can_manage_profiles: bool = False
    can_edit_settings: bool = False
    is_admin: bool = False
    max_content_rating: Optional[str] = None
    block_unrated_media: bool = False
    is_locked: bool = False
    failed_pin_attempts: int = 0


class User(UserBase, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    pin_hash: Optional[str] = None
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False),
    )


class UserRestrictionBase(SQLModel):
    restriction_type: RestrictionType
    restriction_value: str


class UserRestriction(UserRestrictionBase, table=True):
    __tablename__ = "user_restrictions"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    )
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
