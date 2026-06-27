from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint, text
from sqlmodel import Field, SQLModel

from backend.constants_generated import TagColor

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class EntityTag(SQLModel, table=True):
    """Polymorphic tag assignment: one row per (tag, entity_type, entity_id) triple.

    entity_type is a plain string ("library_item", "library_set", …).
    entity_id is an int with NO database-level foreign key — SQLite cannot
    FK one column to multiple target tables. Integrity is enforced at the
    application layer; callers must always supply the correct entity_type.
    """
    __tablename__ = "entity_tags"
    __table_args__ = (UniqueConstraint("tag_id", "entity_type", "entity_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    tag_id: int = Field(
        sa_column=Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    entity_type: str = Field(sa_column=Column(String, nullable=False))
    entity_id: int = Field(sa_column=Column(Integer, nullable=False))


class Tag(SQLModel, table=True):
    __tablename__ = "tags"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String, unique=True, index=True, nullable=False))
    color: TagColor = Field(
        default="slate",
        sa_column=Column(String, nullable=False, server_default=text("'slate'")),
    )
    is_system: bool = False


class TagCreate(SQLModel):
    name: str
    color: TagColor = "slate"


class TagRead(SQLModel):
    id: int
    name: str
    color: TagColor = "slate"
    item_count: int = 0
    is_system: bool = False


def get_tags_for_entity(entity_type: str, entity_id: int, db: "Session") -> list[TagRead]:
    from sqlalchemy import select as _select
    rows = db.execute(
        _select(Tag)
        .join(EntityTag, EntityTag.tag_id == Tag.id)
        .where(EntityTag.entity_type == entity_type, EntityTag.entity_id == entity_id)
        .order_by(Tag.name)
    ).scalars().all()
    return [TagRead.model_validate(t) for t in rows]
