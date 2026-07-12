from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, func
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from backend.models.app import AppCollection
    from backend.models.software import SoftwareCollection

class DriveBase(SQLModel):
    name: str
    size_mb: int = 500
    image_path: Optional[str] = None

# ---------------------------------------------------------------------------
# Drive ownership: exactly one of software_collection_id / app_collection_id
# must be set per row. A model_validator(mode="after") does not fire on direct
# construction (Drive(...) + db.add()) on a SQLModel table=True class -- same
# bug class as SoftwareCollection.item_type (backend/models/software.py) and
# MediaLink (backend/models/media.py). This mirrors MediaLink's fix exactly: a
# model_post_init override runs the check once, after the full object is built
# and both FK fields hold their final values. Unlike item_type there is no
# derivation step here (neither FK's value is computed from the other), so no
# @validates hook is needed -- only the post-construction exactly-one check.
# ---------------------------------------------------------------------------

class Drive(DriveBase, table=True):
    __tablename__ = "drives"

    id: Optional[int] = Field(default=None, primary_key=True)
    software_collection_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("software_collections.id", ondelete="CASCADE"),
            nullable=True,
            unique=True,
            index=True,
        ),
    )
    app_collection_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("app_collections.id", ondelete="CASCADE"),
            nullable=True,
            unique=True,
            index=True,
        ),
    )
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )

    software_collection: Optional["SoftwareCollection"] = Relationship(
        back_populates="drive",
        sa_relationship_kwargs={
            "foreign_keys": "Drive.software_collection_id",
            "uselist": False,
        },
    )
    app_collection: Optional["AppCollection"] = Relationship(
        back_populates="drive",
        sa_relationship_kwargs={
            "foreign_keys": "Drive.app_collection_id",
            "uselist": False,
        },
    )

    def model_post_init(self, __context: object) -> None:
        has_software = self.software_collection_id is not None
        has_app = self.app_collection_id is not None
        if has_software == has_app:
            raise ValueError(
                "Exactly one of software_collection_id or app_collection_id must be set on a "
                f"Drive (got software_collection_id={self.software_collection_id!r}, "
                f"app_collection_id={self.app_collection_id!r})."
            )

class DriveRead(DriveBase):
    id: int
    software_collection_id: Optional[int] = None
    app_collection_id: Optional[int] = None
    created_at: datetime