from datetime import datetime
from typing import Literal, Optional, get_args

from sqlalchemy import Column, DateTime, func
from sqlmodel import Field, SQLModel

# How long launch history rows are kept before the retention sweep deletes them.
# "never" (default) preserves the current unbounded behaviour. Stored as a plain
# string in app_settings under the launch_history_retention key, same convention
# as metadata_provider. The window -> timedelta mapping lives in
# backend/service/launch/history.py.
LaunchHistoryRetention = Literal["never", "1_week", "1_month", "6_months"]

# Set of valid values, used to reject bad writes at the settings PATCH boundary.
LAUNCH_HISTORY_RETENTION_VALUES: frozenset[str] = frozenset(get_args(LaunchHistoryRetention))


class Settings(SQLModel, table=True):
    __tablename__ = "app_settings"

    key: str = Field(primary_key=True)
    value: Optional[str] = None
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False),
    )


class SettingsPatch(SQLModel):
    updates: dict[str, Optional[str | bool]]
