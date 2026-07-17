from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, func
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from backend.models.app import AppItemBundle
    from backend.models.game import GameItemBundle

class DriveBase(SQLModel):
    name: str
    size_mb: int = 500
    image_path: Optional[str] = None

# ---------------------------------------------------------------------------
# Drive ownership: exactly one of game_item_bundle_id / app_item_bundle_id
# must be set per row. A model_validator(mode="after") does not fire on direct
# construction (Drive(...) + db.add()) on a SQLModel table=True class -- same
# bug class as GameItemBundle.item_type (backend/models/game.py) and
# MediaRestriction (backend/models/media_restriction.py). This mirrors that
# fix exactly: a model_post_init override runs the check once, after the full
# object is built and both FK fields hold their final values. Unlike item_type
# there is no derivation step here (neither FK's value is computed from the
# other), so no @validates hook is needed -- only the post-construction
# exactly-one check. MediaLink (backend/models/media.py) no longer belongs to
# this bug class: it moved to a polymorphic entity_a/entity_b shape with no
# nullable-FK ambiguity to guard, so it has no model_post_init at all now.
# ---------------------------------------------------------------------------

class Drive(DriveBase, table=True):
    __tablename__ = "drives"

    id: Optional[int] = Field(default=None, primary_key=True)
    game_item_bundle_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("game_item_bundles.id", ondelete="CASCADE"),
            nullable=True,
            unique=True,
            index=True,
        ),
    )
    app_item_bundle_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("app_item_bundles.id", ondelete="CASCADE"),
            nullable=True,
            unique=True,
            index=True,
        ),
    )
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )

    game_item_bundle: Optional["GameItemBundle"] = Relationship(
        back_populates="drive",
        sa_relationship_kwargs={
            "foreign_keys": "Drive.game_item_bundle_id",
            "uselist": False,
        },
    )
    app_item_bundle: Optional["AppItemBundle"] = Relationship(
        back_populates="drive",
        sa_relationship_kwargs={
            "foreign_keys": "Drive.app_item_bundle_id",
            "uselist": False,
        },
    )

    def model_post_init(self, __context: object) -> None:
        has_game = self.game_item_bundle_id is not None
        has_app = self.app_item_bundle_id is not None
        if has_game == has_app:
            raise ValueError(
                "Exactly one of game_item_bundle_id or app_item_bundle_id must be set on a "
                f"Drive (got game_item_bundle_id={self.game_item_bundle_id!r}, "
                f"app_item_bundle_id={self.app_item_bundle_id!r})."
            )

class DriveRead(DriveBase):
    id: int
    game_item_bundle_id: Optional[int] = None
    app_item_bundle_id: Optional[int] = None
    created_at: datetime
