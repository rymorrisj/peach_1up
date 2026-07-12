from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, func
from sqlmodel import Field, SQLModel

from backend.models.tag import TagRead, get_tags_for_entity

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class ControllerMappingItemBase(SQLModel):
    name: str
    # SDL GUID format: the 32-hex-character device identifier SDL2 /
    # SDL_GameControllerDB use to key a controller by vendor/product/version/
    # platform — the same identifier format found in gamecontrollerdb.txt,
    # e.g. "030000005e0400008e02000010010000". Plain string, not validated
    # against a live DB here; documented so a future SDL_GameControllerDB-
    # backed lookup can validate against it.
    device_signature: str
    # Flat object keyed by RetroArch's standard-controller input names, with
    # the input_playerN_ prefix dropped (a saved mapping isn't player-specific
    # until applied at launch time):
    #   face buttons:   a, b, x, y
    #   d-pad:          dpad_up, dpad_down, dpad_left, dpad_right
    #   shoulder:       l_btn, r_btn
    #   analog triggers: l2_axis, r2_axis (RetroArch treats these as analog by default)
    #   stick clicks:   l3, r3
    #   analog sticks:  left_x, left_y, right_x, right_y
    #   other:          start, select
    # No parsing/validation against this shape is enforced here — see doc
    # 05_system.md; this column just carries the API request body verbatim.
    mapping_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))


class ControllerMappingItem(ControllerMappingItemBase, table=True):
    __tablename__ = "controller_mapping_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: Optional[str] = Field(default=None, sa_column=Column(String, unique=True, index=True))
    created_by: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False),
    )


class ControllerMappingItemCreate(SQLModel):
    name: str
    device_signature: str
    mapping_json: Optional[dict] = None
    slug: Optional[str] = None


class ControllerMappingItemUpdate(SQLModel):
    name: Optional[str] = None
    device_signature: Optional[str] = None
    mapping_json: Optional[dict] = None
    slug: Optional[str] = None


class ControllerMappingItemRead(SQLModel):
    id: int
    slug: Optional[str] = None
    name: str
    device_signature: str
    mapping_json: Optional[dict] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    tags: list[TagRead] = []


def mapping_to_read(mapping: ControllerMappingItem, db: "Session") -> ControllerMappingItemRead:
    read = ControllerMappingItemRead.model_validate(mapping)
    read.tags = get_tags_for_entity("controller_mapping", mapping.id, db)
    return read
