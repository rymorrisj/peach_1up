from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import get_active_user
from backend.models.controller_mapping import (
    ControllerMappingItem,
    ControllerMappingItemCreate,
    ControllerMappingItemRead,
    ControllerMappingItemUpdate,
    mapping_to_read,
)
from backend.models.user import UserItem
from backend.service.utils.slug_generator import unique_slug

router = APIRouter(prefix="/api/v1/controllers", tags=["controllers"])


def check_controller_edit_permission(mapping: ControllerMappingItem, active_user: UserItem) -> None:
    """Bespoke compound-permission rule for editing an existing mapping.

    require_permission(flag) (dependencies.py:176) only supports "owner-bypass
    OR single flag"; this rule is "creator OR (admin AND can_manage_controllerMapping)"
   , an AND nested inside an OR, which the generic factory can't express.
    Owner still bypasses everything, matching every other guard in the app.

    Extracted from require_controller_edit so the generic tag-assignment
    dispatch (backend/api/routes/tags.py) can reuse the same rule instead of
    duplicating it.
    """
    if active_user.is_owner:
        return
    if mapping.created_by is not None and mapping.created_by == active_user.id:
        return
    if active_user.is_admin and active_user.can_manage_controllerMapping:
        return
    raise HTTPException(
        status_code=403,
        detail="Permission denied: requires ownership of this mapping, or is_admin with can_manage_controllerMapping.",
    )


def require_controller_edit(
    request: Request,
    db: Session = Depends(get_db),
    active_user: UserItem = Depends(get_active_user),
) -> UserItem:
    """FastAPI dependency for PATCH/DELETE /controllers/{id}.

    Mirrors the request.path_params pattern used by require_self_or_admin.
    """
    if active_user.is_owner:
        return active_user
    mapping_id = int(request.path_params.get("id", 0))
    mapping = db.get(ControllerMappingItem, mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Controller mapping not found.")
    check_controller_edit_permission(mapping, active_user)
    return active_user


@router.get("", response_model=list[ControllerMappingItemRead])
def list_mappings(db: Session = Depends(get_db), _: UserItem = Depends(get_active_user)):
    mappings = db.query(ControllerMappingItem).order_by(ControllerMappingItem.name).all()
    return [mapping_to_read(m, db) for m in mappings]


@router.get("/{id}", response_model=ControllerMappingItemRead)
def get_mapping(id: int, db: Session = Depends(get_db), _: UserItem = Depends(get_active_user)):
    mapping = db.get(ControllerMappingItem, id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Controller mapping not found.")
    return mapping_to_read(mapping, db)


@router.post("", response_model=ControllerMappingItemRead, status_code=201)
def create_mapping(
    body: ControllerMappingItemCreate,
    db: Session = Depends(get_db),
    active_user: UserItem = Depends(get_active_user),
):
    mapping = ControllerMappingItem(
        name=body.name,
        device_signature=body.device_signature,
        mapping_json=body.mapping_json,
        created_by=active_user.id,
    )
    mapping.slug = body.slug or unique_slug(
        body.name,
        lambda s: db.query(ControllerMappingItem).filter(ControllerMappingItem.slug == s).first() is not None,
        fallback="controller-mapping",
    )
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return mapping_to_read(mapping, db)


@router.post("/{id}/duplicate", response_model=ControllerMappingItemRead, status_code=201)
def duplicate_mapping(
    id: int,
    db: Session = Depends(get_db),
    active_user: UserItem = Depends(get_active_user),
):
    source = db.get(ControllerMappingItem, id)
    if not source:
        raise HTTPException(status_code=404, detail="Controller mapping not found.")
    name = f"{source.name} (copy)"
    mapping = ControllerMappingItem(
        name=name,
        device_signature=source.device_signature,
        mapping_json=source.mapping_json,
        created_by=active_user.id,
    )
    mapping.slug = unique_slug(
        name,
        lambda s: db.query(ControllerMappingItem).filter(ControllerMappingItem.slug == s).first() is not None,
        fallback="controller-mapping",
    )
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return mapping_to_read(mapping, db)


@router.patch("/{id}", response_model=ControllerMappingItemRead)
def update_mapping(
    id: int,
    body: ControllerMappingItemUpdate,
    db: Session = Depends(get_db),
    _: UserItem = Depends(require_controller_edit),
):
    mapping = db.get(ControllerMappingItem, id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Controller mapping not found.")
    updates = body.model_dump(exclude_none=True)
    for key, value in updates.items():
        setattr(mapping, key, value)
    db.commit()
    db.refresh(mapping)
    return mapping_to_read(mapping, db)


@router.delete("/{id}", status_code=204)
def delete_mapping(
    id: int,
    db: Session = Depends(get_db),
    _: UserItem = Depends(require_controller_edit),
):
    mapping = db.get(ControllerMappingItem, id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Controller mapping not found.")
    db.delete(mapping)
    db.commit()
