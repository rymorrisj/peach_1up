from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, func
from sqlmodel import Field, SQLModel


class Settings(SQLModel, table=True):
    __tablename__ = "app_settings"

    key: str = Field(primary_key=True)
    value: Optional[str] = None
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False),
    )


class SettingsRead(SQLModel):
    key: str
    value: Optional[str] = None
    updated_at: datetime


class SettingsPatch(SQLModel):
    updates: dict[str, Optional[str]]
