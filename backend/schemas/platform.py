from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PlatformBase(BaseModel):
    name: str
    era: str
    emulator_slug: str
    profile_id: int | None = None
    base_image_path: str | None = None
    working_image_path: str | None = None
    config_path: str | None = None
    status: str = "ok"
    notes: str | None = None
    slug: str | None = None
    is_system: bool = False
    download_url: str | None = None
    supported_eras: str | None = None
    default_flags: str | None = None


class PlatformCreate(PlatformBase):
    pass


class PlatformUpdate(BaseModel):
    name: str | None = None
    era: str | None = None
    emulator_slug: str | None = None
    profile_id: int | None = None
    base_image_path: str | None = None
    working_image_path: str | None = None
    config_path: str | None = None
    status: str | None = None
    notes: str | None = None
    slug: str | None = None
    download_url: str | None = None
    supported_eras: str | None = None
    default_flags: str | None = None


class PlatformRead(PlatformBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    last_health_check: datetime | None
    created_at: datetime
    updated_at: datetime
