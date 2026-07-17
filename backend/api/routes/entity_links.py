from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlmodel import SQLModel

from backend.core.database import get_db
from backend.core.dependencies import get_active_user
from backend.models.media import MediaLink, MediaLinkRead, _link_target_model, make_entity_link
from backend.models.user import UserItem

router = APIRouter(prefix="/api/v1", tags=["entity-links"])

# entity_type -> permission flag required to write a link touching it.
# Values match _ASSIGNMENT_PERMISSIONS in tags.py exactly. _link_target_model
# (backend/models/media.py) is the single source of truth for which model
# backs each entity_type, existence-checks below use it directly rather than
# hand-maintaining a second copy of that mapping here.
_LINK_PERMISSIONS: dict[str, str] = {
    "game_item_bundle": "can_manage_game",
    "app_item_bundle": "can_manage_app",
    "media_item": "can_manage_media",
    "media_item_bundle": "can_manage_media",
}


class EntityLinkCreateBody(SQLModel):
    target_entity_type: str
    target_entity_id: int
    link_note: str | None = None


def _require_link_permission(entity_type: str, active_user: UserItem) -> None:
    """Plain-flag permission check for one side of a link. Owner bypasses
    every flag, mirroring _require_flag_permission in tags.py."""
    if active_user.is_owner:
        return
    flag = _LINK_PERMISSIONS[entity_type]
    if not getattr(active_user, flag, False):
        raise HTTPException(status_code=403, detail=f"Permission denied: requires {flag}.")


def _resolve_link_entities(
    entity_type: str,
    entity_id: int,
    target_entity_type: str,
    target_entity_id: int,
    active_user: UserItem,
    db: Session,
):
    """Shared validation for create/delete link routes.

    Order: unknown entity_type on either side -> 422, self-link -> 422,
    permission on BOTH sides -> 403 (checked before any existence check, so
    an unauthorized caller cannot use a 404-vs-200 response difference to
    learn whether an entity exists), then existence on both sides -> 404.

    Two-sided authorization is mandatory and deliberately NOT the same shape
    as tags.py's single-sided _resolve_assignment_entity: a tag assignment
    only ever touches one polymorphic entity, but a link touches two,
    potentially in two different domains, so the caller must be authorized
    to write to both, not just the one named in the URL. A can_manage_media
    -only caller must not be able to attach a link onto an arbitrary game
    they have no can_manage_game right to touch, and vice versa.
    """
    model_a = _link_target_model(entity_type)
    model_b = _link_target_model(target_entity_type)
    if model_a is None:
        raise HTTPException(status_code=422, detail=f"Unknown entity_type: {entity_type!r}")
    if model_b is None:
        raise HTTPException(status_code=422, detail=f"Unknown entity_type: {target_entity_type!r}")

    if entity_type == target_entity_type and entity_id == target_entity_id:
        raise HTTPException(status_code=422, detail="Cannot link an entity to itself.")

    _require_link_permission(entity_type, active_user)
    _require_link_permission(target_entity_type, active_user)

    entity = db.get(model_a, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail=f"{entity_type} not found.")
    target = db.get(model_b, target_entity_id)
    if not target:
        raise HTTPException(status_code=404, detail=f"{target_entity_type} not found.")

    return entity, target


@router.post("/entity-links/{entity_type}/{entity_id}", response_model=MediaLinkRead, status_code=201)
def create_entity_link(
    entity_type: str,
    entity_id: int,
    body: EntityLinkCreateBody,
    db: Session = Depends(get_db),
    active_user: UserItem = Depends(get_active_user),
):
    _resolve_link_entities(
        entity_type, entity_id, body.target_entity_type, body.target_entity_id, active_user, db
    )
    link = make_entity_link(
        entity_type, entity_id, body.target_entity_type, body.target_entity_id,
        link_note=body.link_note,
    )
    existing = (
        db.query(MediaLink)
        .filter(
            MediaLink.entity_a_type == link.entity_a_type,
            MediaLink.entity_a_id == link.entity_a_id,
            MediaLink.entity_b_type == link.entity_b_type,
            MediaLink.entity_b_id == link.entity_b_id,
        )
        .first()
    )
    if existing:
        return existing
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@router.delete("/entity-links/{entity_type}/{entity_id}", status_code=204)
def delete_entity_link(
    entity_type: str,
    entity_id: int,
    target_entity_type: str = Query(...),
    target_entity_id: int = Query(...),
    db: Session = Depends(get_db),
    active_user: UserItem = Depends(get_active_user),
):
    _resolve_link_entities(entity_type, entity_id, target_entity_type, target_entity_id, active_user, db)
    sorted_link = make_entity_link(entity_type, entity_id, target_entity_type, target_entity_id)
    link = (
        db.query(MediaLink)
        .filter(
            MediaLink.entity_a_type == sorted_link.entity_a_type,
            MediaLink.entity_a_id == sorted_link.entity_a_id,
            MediaLink.entity_b_type == sorted_link.entity_b_type,
            MediaLink.entity_b_id == sorted_link.entity_b_id,
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=404, detail="Link not found.")
    db.delete(link)
    db.commit()
