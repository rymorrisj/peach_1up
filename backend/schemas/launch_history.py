from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LaunchHistoryBase(BaseModel):
    library_item_id: int
    profile_id: int | None = None
    emulator_slug: str
    network_blocked: bool = True
    job_isolated: bool = False


class LaunchHistoryRead(LaunchHistoryBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    started_at: datetime
    ended_at: datetime | None
    exit_code: int | None
    error_message: str | None
