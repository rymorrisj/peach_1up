from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProfileBase(BaseModel):
    name: str
    slug: str
    emulator_slug: str
    era: str
    config_path: str | None = None
    extra_args: str | None = None
    is_bundled: bool = False
    is_accuracy_mode: bool = False
    notes: str | None = None


class ProfileCreate(ProfileBase):
    pass


class ProfileUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    emulator_slug: str | None = None
    era: str | None = None
    config_path: str | None = None
    extra_args: str | None = None
    is_accuracy_mode: bool | None = None
    notes: str | None = None


class ProfileRead(ProfileBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime
