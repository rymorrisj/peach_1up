from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    avatar_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pin_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    platform_slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    era: Mapped[str | None] = mapped_column(String(50), nullable=True)
    custom_flags: Mapped[str | None] = mapped_column(Text, nullable=True)
    rom_pack_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    custom_script: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ProfilePermissions(Base):
    __tablename__ = "profile_permissions"

    profile_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), primary_key=True)
    can_install_media: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_edit_library: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_manage_profiles: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_edit_settings: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ContentRating(Base):
    __tablename__ = "content_ratings"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_restricted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True
    )
