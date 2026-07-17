from typing import Optional

from sqlalchemy import Column, ForeignKey, Integer
from sqlmodel import Field, SQLModel

# ---------------------------------------------------------------------------
# Exactly one of game_item_bundle_id/media_item_bundle_id/app_item_bundle_id
# must be set per row. A model_validator(mode="after") does not fire on direct
# construction (MediaRestriction(...) + db.add()) on a SQLModel table=True
# class, same bug class as GameItemBundle.item_type (see backend/models/game.py)
# and Drive (see backend/models/drive.py). @validates on each FK field
# individually does not work either: sqlmodel_table_construct() setattr()s
# every field in class-declaration order, so constructing with only a
# later-declared field passed causes an earlier-declared field's validator to
# fire first while the later field is still unset — it sees both as None and
# incorrectly raises "none set" before the real value is ever assigned. Fixed
# the same way as Drive: a model_post_init override runs the check once,
# after the full object is built and all three fields hold their final
# values. MediaLink (backend/models/media.py) used to share this exact bug
# class but no longer does: it moved to a polymorphic entity_a/entity_b shape
# with no nullable-FK ambiguity to guard, so it has no model_post_init at all
# now.
# ---------------------------------------------------------------------------


class MediaRestriction(SQLModel, table=True):
    __tablename__ = "restrictions"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_item_id: int = Field(
        sa_column=Column(Integer, ForeignKey("user_items.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    game_item_bundle_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("game_item_bundles.id", ondelete="CASCADE"), nullable=True),
    )
    media_item_bundle_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("media_item_bundles.id", ondelete="CASCADE"), nullable=True),
    )
    app_item_bundle_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("app_item_bundles.id", ondelete="CASCADE"), nullable=True),
    )

    def model_post_init(self, __context: object) -> None:
        set_count = sum(
            fk is not None
            for fk in (self.game_item_bundle_id, self.media_item_bundle_id, self.app_item_bundle_id)
        )
        if set_count != 1:
            raise ValueError(
                "Exactly one of game_item_bundle_id, media_item_bundle_id, or "
                "app_item_bundle_id must be set on a MediaRestriction (got "
                f"game_item_bundle_id={self.game_item_bundle_id!r}, "
                f"media_item_bundle_id={self.media_item_bundle_id!r}, "
                f"app_item_bundle_id={self.app_item_bundle_id!r})."
            )
