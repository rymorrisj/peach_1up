from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, func
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from backend.models.library import LibraryCollection

class DriveBase(SQLModel):
    name: str
    size_mb: int = 500
    image_path: Optional[str] = None

class Drive(DriveBase, table=True):
    __tablename__ = "drives"

    id: Optional[int] = Field(default=None, primary_key=True)
    library_collection_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("library_collections.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        )
    )
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )

    library_collection: Optional["LibraryCollection"] = Relationship(
        back_populates="drive",
        sa_relationship_kwargs={
            "foreign_keys": "Drive.library_collection_id",
            "uselist": False,
        },
    )

class DriveRead(DriveBase):
    id: int
    library_collection_id: int
    created_at: datetime