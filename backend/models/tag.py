from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, ForeignKey, Integer, String
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from backend.models.library import LibraryItem


class LibraryItemTag(SQLModel, table=True):
    __tablename__ = "library_item_tags"

    library_item_id: int = Field(
        sa_column=Column(Integer, ForeignKey("library_items.id", ondelete="CASCADE"), primary_key=True)
    )
    tag_id: int = Field(
        sa_column=Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
    )


class Tag(SQLModel, table=True):
    __tablename__ = "tags"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String, unique=True, index=True, nullable=False))

    library_items: list["LibraryItem"] = Relationship(
        back_populates="tags",
        link_model=LibraryItemTag,
    )


class TagCreate(SQLModel):
    name: str


class TagRead(SQLModel):
    id: int
    name: str
    item_count: int = 0
