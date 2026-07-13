from typing import Callable, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import (
    get_filtered_app_item, get_filtered_game_item_bundle, get_filtered_media_item_bundle, require_permission,
)
from backend.models.media_restriction import MediaRestriction
from backend.models.user import UserItem

router = APIRouter(prefix="/api/v1", tags=["restrictions"])

RestrictionDomain = Literal["game", "media", "app"]


class RestrictionsBody(BaseModel):
    user_item_ids: list[int]


class RestrictionsRead(BaseModel):
    restricted_user_item_ids: list[int]


# Each domain's filtered getter both confirms the entity exists and enforces
# the caller's own visibility (owner-bypass, restriction/rating filters) —
# reused here rather than a raw db.get(), so an admin who is themselves
# restricted from an entity cannot read or edit its restriction list either.
# fk_field is the MediaRestriction column name that scopes rows to that domain.
_DOMAIN_CONFIG: dict[RestrictionDomain, tuple[Callable[[int, UserItem, Session], object], str]] = {
    "game": (get_filtered_game_item_bundle, "game_item_bundle_id"),
    "media": (get_filtered_media_item_bundle, "media_item_bundle_id"),
    "app": (get_filtered_app_item, "app_item_bundle_id"),
}


@router.get("/restrictions/{domain}/{entity_id}", response_model=RestrictionsRead)
def get_restrictions(
    domain: RestrictionDomain,
    entity_id: int,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("is_admin"),
):
    getter, fk_field = _DOMAIN_CONFIG[domain]
    bundle = getter(entity_id, active_user, db)
    column = getattr(MediaRestriction, fk_field)
    rows = db.query(MediaRestriction).filter(column == bundle.id).all()
    return RestrictionsRead(restricted_user_item_ids=[r.user_item_id for r in rows])


@router.put("/restrictions/{domain}/{entity_id}", response_model=RestrictionsRead)
def set_restrictions(
    domain: RestrictionDomain,
    entity_id: int,
    body: RestrictionsBody,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("is_admin"),
):
    getter, fk_field = _DOMAIN_CONFIG[domain]
    bundle = getter(entity_id, active_user, db)
    column = getattr(MediaRestriction, fk_field)
    db.query(MediaRestriction).filter(column == bundle.id).delete()
    for user_item_id in body.user_item_ids:
        db.add(MediaRestriction(user_item_id=user_item_id, **{fk_field: bundle.id}))
    db.commit()
    return RestrictionsRead(restricted_user_item_ids=body.user_item_ids)
