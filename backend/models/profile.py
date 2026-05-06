from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    emulator_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    era: Mapped[str] = mapped_column(String(50), nullable=False)
    config_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extra_args: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_bundled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_accuracy_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
