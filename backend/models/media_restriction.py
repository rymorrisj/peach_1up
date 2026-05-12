from sqlalchemy import Column, ForeignKey, Integer
from sqlmodel import Field, SQLModel


class MediaRestriction(SQLModel, table=True):
    __tablename__ = "media_restrictions"

    user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    )
    library_item_id: int = Field(
        sa_column=Column(Integer, ForeignKey("library_items.id", ondelete="CASCADE"), primary_key=True)
    )
