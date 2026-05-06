from pydantic import BaseModel, ConfigDict


class TagBase(BaseModel):
    name: str
    slug: str
    color: str | None = None


class TagCreate(TagBase):
    pass


class TagUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    color: str | None = None


class TagRead(TagBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
