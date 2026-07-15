from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlmodel import SQLModel

from backend.api.routes.controllers import check_controller_edit_permission
from backend.core.database import get_db
from backend.core.dependencies import get_active_user, require_permission
from backend.models.app import AppItemBundle, AppItem
from backend.models.controller_mapping import ControllerMappingItem
from backend.models.environment import EnvironmentItem
from backend.models.media import MediaItemBundle, MediaItem
from backend.models.rom_pack import RomPackItem
from backend.models.game import GameItemBundle, GameItem
from backend.models.tag import EntityTag, Tag, TagCreate, TagRead
from backend.models.user import UserItem

router = APIRouter(prefix="/api/v1/tags", tags=["tags"])

# entity_type -> model to existence-check entity_id against.
_ASSIGNMENT_TARGETS: dict[str, type] = {
    "game_item_bundle": GameItemBundle,
    "game_item": GameItem,
    "media_item": MediaItem,
    "media_item_bundle": MediaItemBundle,
    "environment_item": EnvironmentItem,
    "rom_pack_item": RomPackItem,
    "controller_mapping": ControllerMappingItem,
    "app_item_bundle": AppItemBundle,
    "app_item": AppItem,
}

# entity_type -> permission flag required to write the assignment.
# controller_mapping is intentionally absent: it uses the bespoke
# check_controller_edit_permission rule instead of a plain flag.
_ASSIGNMENT_PERMISSIONS: dict[str, str] = {
    "game_item_bundle": "can_manage_game",
    "game_item": "can_manage_game",
    "media_item": "can_manage_media",
    "media_item_bundle": "can_manage_media",
    "environment_item": "can_manage_environment",
    "rom_pack_item": "can_manage_environment",
    "app_item_bundle": "can_manage_app",
    "app_item": "can_manage_app",
}


class TagAssignmentBody(SQLModel):
    entity_type: str
    entity_id: int


def _tag_read(tag: Tag, db: Session) -> TagRead:
    count = (
        db.query(func.count(EntityTag.entity_id))
        .filter(EntityTag.tag_id == tag.id)
        .scalar()
        or 0
    )
    return TagRead(id=tag.id, name=tag.name, color=tag.color, item_count=count, is_system=tag.is_system)


@router.get("", response_model=list[TagRead])
def list_tags(db: Session = Depends(get_db), _: UserItem = Depends(get_active_user)):
    tags = db.query(Tag).order_by(Tag.name).all()
    return [_tag_read(t, db) for t in tags]


@router.post("", response_model=TagRead, status_code=201)
def create_tag(
    body: TagCreate,
    db: Session = Depends(get_db),
    _: UserItem = require_permission("can_manage_game"),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Tag name cannot be blank.")
    if db.query(Tag).filter(Tag.name == name).first():
        raise HTTPException(status_code=409, detail="A tag with that name already exists.")
    tag = Tag(name=name, color=body.color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return _tag_read(tag, db)


@router.delete("/{tag_id}", status_code=204)
def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    _: UserItem = require_permission("can_manage_game"),
):
    tag = db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found.")
    if tag.is_system:
        raise HTTPException(status_code=403, detail="System tags cannot be deleted.")
    db.delete(tag)
    db.commit()


def _require_flag_permission(entity_type: str, active_user: UserItem) -> None:
    """Plain-flag permission check for entity_types with a simple can_edit_* rule.

    controller_mapping is handled separately by the caller once the entity is
    resolved, since its rule needs the row itself (created_by), not just a flag.
    """
    if active_user.is_owner:
        return
    flag = _ASSIGNMENT_PERMISSIONS[entity_type]
    if not getattr(active_user, flag, False):
        raise HTTPException(status_code=403, detail=f"Permission denied: requires {flag}.")


def _resolve_assignment_entity(tag_id: int, body: TagAssignmentBody, active_user: UserItem, db: Session):
    """Shared validation for both assignment routes.

    Order: unknown entity_type -> 422, plain-flag permission -> 403 (before any
    existence checks, so an unauthorized caller doesn't learn whether a tag/entity
    exists), tag existence -> 404, system-tag lock -> 403 (system tags are
    read-only, no user may assign or unassign them), entity existence -> 404,
    then the bespoke controller_mapping permission (needs the fetched row) -> 403.
    Returns the resolved entity.
    """
    model = _ASSIGNMENT_TARGETS.get(body.entity_type)
    if model is None:
        raise HTTPException(status_code=422, detail=f"Unknown entity_type: {body.entity_type!r}")

    if body.entity_type != "controller_mapping":
        _require_flag_permission(body.entity_type, active_user)

    tag = db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found.")
    if tag.is_system:
        raise HTTPException(status_code=403, detail="System tags cannot be assigned or unassigned.")

    entity = db.get(model, body.entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail=f"{body.entity_type} not found.")

    if body.entity_type == "controller_mapping":
        check_controller_edit_permission(entity, active_user)

    return entity


@router.post("/{tag_id}/assignments", status_code=204)
def create_tag_assignment(
    tag_id: int,
    body: TagAssignmentBody,
    db: Session = Depends(get_db),
    active_user: UserItem = Depends(get_active_user),
):
    _resolve_assignment_entity(tag_id, body, active_user, db)
    exists = (
        db.query(EntityTag)
        .filter(
            EntityTag.tag_id == tag_id,
            EntityTag.entity_type == body.entity_type,
            EntityTag.entity_id == body.entity_id,
        )
        .first()
    )
    if not exists:
        db.add(EntityTag(tag_id=tag_id, entity_type=body.entity_type, entity_id=body.entity_id))
        db.commit()


@router.delete("/{tag_id}/assignments", status_code=204)
def delete_tag_assignment(
    tag_id: int,
    body: TagAssignmentBody,
    db: Session = Depends(get_db),
    active_user: UserItem = Depends(get_active_user),
):
    _resolve_assignment_entity(tag_id, body, active_user, db)
    link = (
        db.query(EntityTag)
        .filter(
            EntityTag.tag_id == tag_id,
            EntityTag.entity_type == body.entity_type,
            EntityTag.entity_id == body.entity_id,
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=404, detail="Tag not assigned to this entity.")
    db.delete(link)
    db.commit()
