from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SnapshotBase(BaseModel):
    platform_id: int
    name: str
    image_path: str
    size_bytes: int | None = None
    notes: str | None = None


class SnapshotCreate(BaseModel):
    name: str
    notes: str | None = None


class SnapshotRead(SnapshotBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
