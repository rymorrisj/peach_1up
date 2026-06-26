from typing import Optional

from sqlalchemy import Column, ForeignKey, Integer
from sqlmodel import Field, SQLModel


class MediaRestriction(SQLModel, table=True):
    __tablename__ = "media_restrictions"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    library_item_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("library_items.id", ondelete="CASCADE"), nullable=True),
    )
    library_set_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("library_sets.id", ondelete="CASCADE"), nullable=True),
    )
