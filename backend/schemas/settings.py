from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    value: str | None
    updated_at: datetime


class SettingsPatch(BaseModel):
    updates: dict[str, str | None]
