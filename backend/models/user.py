from datetime import datetime
from typing import Optional

from pydantic import field_validator
from sqlalchemy import Column, DateTime, func
from sqlmodel import Field, SQLModel


class UserBase(SQLModel):
    name: str
    is_owner: bool = False
    pin_required: bool = False
    can_launch_media: bool = True
    can_edit_environments: bool = False
    can_manage_software: bool = False
    can_edit_media: bool = False
    can_manage_controllers: bool = False
    can_manage_profiles: bool = False
    can_edit_settings: bool = False
    can_manage_users: bool = False
    is_admin: bool = False
    max_content_rating: Optional[str] = None
    block_unrated_media: bool = False
    is_locked: bool = False
    failed_pin_attempts: int = 0
    session_token_ttl: Optional[int] = None

    @field_validator("max_content_rating")
    @classmethod
    def _check_max_content_rating(cls, v: Optional[str]) -> Optional[str]:
        # An unrecognised ceiling silently uncaps the user (see
        # get_filtered_collections), so reject it wherever a User is validated.
        from backend.core.dependencies import validate_max_content_rating
        return validate_max_content_rating(v)


class User(UserBase, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    pin_hash: Optional[str] = None
    # Server-only root-of-trust key for this user's sessions. Every session
    # token is an HMAC over this secret — never read by any API schema.
    identity_token_secret: Optional[str] = None
    session_token_hash: Optional[str] = None
    session_token_expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False),
    )


class UserRead(UserBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
