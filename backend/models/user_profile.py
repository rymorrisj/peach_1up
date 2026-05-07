from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, func
from sqlmodel import Field, SQLModel


class UserProfileBase(SQLModel):
    name: str
    avatar_path: Optional[str] = None
    is_owner: bool = False
    platform_slug: Optional[str] = None
    era: Optional[str] = None
    custom_flags: Optional[str] = None
    rom_pack_path: Optional[str] = None
    custom_script: Optional[str] = None
    notes: Optional[str] = None


class UserProfile(UserProfileBase, table=True):
    __tablename__ = "user_profiles"

    id: Optional[int] = Field(default=None, primary_key=True)
    pin_hash: Optional[str] = None
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
    last_active_at: Optional[datetime] = None


class UserProfileCreate(UserProfileBase):
    pin: Optional[str] = None


class UserProfileUpdate(SQLModel):
    name: Optional[str] = None
    avatar_path: Optional[str] = None
    pin: Optional[str] = None
    platform_slug: Optional[str] = None
    era: Optional[str] = None
    custom_flags: Optional[str] = None
    rom_pack_path: Optional[str] = None
    custom_script: Optional[str] = None
    notes: Optional[str] = None


class UserProfileRead(UserProfileBase):
    id: int
    created_at: datetime
    last_active_at: Optional[datetime] = None


class ProfilePermissionsBase(SQLModel):
    can_install_media: bool = False
    can_edit_library: bool = False
    can_manage_profiles: bool = False
    can_edit_settings: bool = False
    is_admin: bool = False


class ProfilePermissions(ProfilePermissionsBase, table=True):
    __tablename__ = "profile_permissions"

    profile_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("user_profiles.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        )
    )


class ProfilePermissionsUpdate(ProfilePermissionsBase):
    pass


class ProfilePermissionsRead(ProfilePermissionsBase):
    profile_id: int


class ContentRatingBase(SQLModel):
    name: str
    slug: str = Field(unique=True)
    description: Optional[str] = None
    is_restricted: bool = False


class ContentRating(ContentRatingBase, table=True):
    __tablename__ = "content_ratings"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_by_profile_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True),
    )


class ContentRatingCreate(ContentRatingBase):
    pass


class ContentRatingRead(ContentRatingBase):
    id: int
    created_by_profile_id: Optional[int] = None
