from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, ForeignKey, Integer, String, text
from sqlmodel import Field, Relationship, SQLModel

from backend.constants_generated import TagColor

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
    color: TagColor = Field(
        default="slate",
        sa_column=Column(String, nullable=False, server_default=text("'slate'")),
    )

    library_items: list["LibraryItem"] = Relationship(
        back_populates="tags",
        link_model=LibraryItemTag,
    )


class TagCreate(SQLModel):
    name: str
    color: TagColor = "slate"


class TagRead(SQLModel):
    id: int
    name: str
    color: TagColor = "slate"
    item_count: int = 0
