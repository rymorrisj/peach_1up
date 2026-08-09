from datetime import datetime
from typing import Optional

from pydantic import model_validator
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlmodel import Field, SQLModel
from backend.constants_generated import EmulatorCatalogSlug


class LaunchHistoryBase(SQLModel):
    emulator_slug: EmulatorCatalogSlug = Field(sa_column=Column(String, nullable=False))
    network_blocked: bool = True
    job_isolated: bool = False
    sandboxed: bool = False
    sandbox_memory_limit_mb: Optional[int] = None
    sandbox_cpu_limit_percent: Optional[int] = None


class LaunchHistory(LaunchHistoryBase, table=True):
    __tablename__ = "launch_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    game_item_bundle_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("game_item_bundles.id", ondelete="CASCADE"), nullable=True),
    )
    app_item_bundle_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("app_item_bundles.id", ondelete="CASCADE"), nullable=True),
    )
    environment_item_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("environment_items.id", ondelete="CASCADE"), nullable=True),
    )
    profile_item_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("profile_items.id", ondelete="SET NULL"), nullable=True),
    )
    started_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
    ended_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    error_message: Optional[str] = None


class LaunchHistoryRead(LaunchHistoryBase):
    id: int
    game_item_bundle_id: Optional[int] = None
    app_item_bundle_id: Optional[int] = None
    environment_item_id: Optional[int] = None
    profile_item_id: Optional[int] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    error_message: Optional[str] = None
    # Derived discriminator (not stored): a bundle launch vs an environment launch.
    target_type: Optional[str] = None
    # Populated only by GET /launches/{history_id}, computed on read (not a stored
    # column). Requires joining ProfileItem and resolving container_enabled, which
    # this model alone cannot do, so it stays None on every other endpoint that
    # returns LaunchHistoryRead (list endpoints included).
    container_moniker: Optional[str] = None

    @model_validator(mode="after")
    def _derive_target_type(self) -> "LaunchHistoryRead":
        if self.game_item_bundle_id is not None:
            self.target_type = "game_item_bundle"
        elif self.app_item_bundle_id is not None:
            self.target_type = "app_item_bundle"
        elif self.environment_item_id is not None:
            self.target_type = "environment_item"
        return self
