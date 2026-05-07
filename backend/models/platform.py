from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class Platform(Base):
    __tablename__ = "platforms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    era: Mapped[str] = mapped_column(String(50), nullable=False)
    emulator_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True)
    base_image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    working_image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    config_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="ok", nullable=False)
    last_health_check: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # System platform fields — populated only for pre-seeded emulator records
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    download_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    supported_eras: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of era strings
    default_flags: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
