from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class LaunchHistory(Base):
    __tablename__ = "launch_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    library_item_id: Mapped[int] = mapped_column(ForeignKey("library_items.id", ondelete="CASCADE"), nullable=False)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True)
    emulator_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    network_blocked: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    job_isolated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
