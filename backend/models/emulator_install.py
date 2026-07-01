from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, String, func
from sqlmodel import Field, SQLModel


class EmulatorInstall(SQLModel, table=True):
    __tablename__ = "emulator_installs"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(sa_column=Column(String, nullable=False, index=True, unique=True))
    installed_version: str
    installed_at: datetime = Field(
        sa_column=Column(DateTime, server_default=func.now(), nullable=False)
    )
    install_path: str
    asset_filename: str
    asset_url: str
    sha256_digest: Optional[str] = None
    digest_verified: bool = Field(sa_column=Column(Boolean, nullable=False, default=False))
    latest_known_version: Optional[str] = None
    last_checked_at: Optional[datetime] = None
