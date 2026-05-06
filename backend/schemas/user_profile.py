from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserProfileBase(BaseModel):
    name: str
    avatar_path: str | None = None
    is_owner: bool = False


class UserProfileCreate(UserProfileBase):
    pin: str | None = Field(default=None, exclude=True)


class UserProfileUpdate(BaseModel):
    name: str | None = None
    avatar_path: str | None = None
    pin: str | None = Field(default=None, exclude=True)


class UserProfileRead(UserProfileBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    last_active_at: datetime | None


class ProfilePermissionsBase(BaseModel):
    can_install_media: bool = False
    can_edit_library: bool = False
    can_manage_profiles: bool = False
    can_edit_settings: bool = False
    is_admin: bool = False


class ProfilePermissionsUpdate(ProfilePermissionsBase):
    pass


class ProfilePermissionsRead(ProfilePermissionsBase):
    model_config = ConfigDict(from_attributes=True)
    profile_id: int


class ContentRatingBase(BaseModel):
    name: str
    slug: str
    description: str | None = None
    is_restricted: bool = False


class ContentRatingCreate(ContentRatingBase):
    pass


class ContentRatingRead(ContentRatingBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_by_profile_id: int | None
