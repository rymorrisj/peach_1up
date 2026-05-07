from typing import Optional

from sqlmodel import Field, SQLModel


class TagBase(SQLModel):
    name: str = Field(unique=True)
    slug: str = Field(unique=True)
    color: Optional[str] = None


class Tag(TagBase, table=True):
    __tablename__ = "tags"

    id: Optional[int] = Field(default=None, primary_key=True)


class TagCreate(TagBase):
    pass


class TagUpdate(SQLModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    color: Optional[str] = None


class TagRead(TagBase):
    id: int
