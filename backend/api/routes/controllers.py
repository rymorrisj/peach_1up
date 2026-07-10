from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import get_active_user
from backend.models.controller_mapping import (
    ControllerMapping,
    ControllerMappingCreate,
    ControllerMappingRead,
    ControllerMappingUpdate,
    mapping_to_read,
)
from backend.models.user import User
from backend.service.utils.slug_generator import unique_slug

router = APIRouter(prefix="/api/v1/controllers", tags=["controllers"])


def require_controller_edit(
    request: Request,
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
) -> User:
    """Bespoke compound-permission dependency for editing an existing mapping.

    require_permission(flag) (dependencies.py:176) only supports "owner-bypass
    OR single flag"; this rule is "creator OR (admin AND can_manage_controllers)"
    — an AND nested inside an OR, which the generic factory can't express.
    Owner still bypasses everything, matching every other guard in the app.
    Mirrors the request.path_params pattern used by require_self_or_admin.
    """
    if active_user.is_owner:
        return active_user
    mapping_id = int(request.path_params.get("id", 0))
    mapping = db.get(ControllerMapping, mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Controller mapping not found.")
    if mapping.created_by == active_user.id:
        return active_user
    if active_user.is_admin and active_user.can_manage_controllers:
        return active_user
    raise HTTPException(
        status_code=403,
        detail="Permission denied: requires ownership of this mapping, or is_admin with can_manage_controllers.",
    )


@router.get("", response_model=list[ControllerMappingRead])
def list_mappings(db: Session = Depends(get_db), _: User = Depends(get_active_user)):
    mappings = db.query(ControllerMapping).order_by(ControllerMapping.name).all()
    return [mapping_to_read(m, db) for m in mappings]


@router.get("/{id}", response_model=ControllerMappingRead)
def get_mapping(id: int, db: Session = Depends(get_db), _: User = Depends(get_active_user)):
    mapping = db.get(ControllerMapping, id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Controller mapping not found.")
    return mapping_to_read(mapping, db)


@router.post("", response_model=ControllerMappingRead, status_code=201)
def create_mapping(
    body: ControllerMappingCreate,
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
):
    mapping = ControllerMapping(
        name=body.name,
        device_signature=body.device_signature,
        mapping_json=body.mapping_json,
        created_by=active_user.id,
    )
    mapping.slug = body.slug or unique_slug(
        body.name,
        lambda s: db.query(ControllerMapping).filter(ControllerMapping.slug == s).first() is not None,
        fallback="controller-mapping",
    )
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return mapping_to_read(mapping, db)


@router.post("/{id}/duplicate", response_model=ControllerMappingRead, status_code=201)
def duplicate_mapping(
    id: int,
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
):
    source = db.get(ControllerMapping, id)
    if not source:
        raise HTTPException(status_code=404, detail="Controller mapping not found.")
    name = f"{source.name} (copy)"
    mapping = ControllerMapping(
        name=name,
        device_signature=source.device_signature,
        mapping_json=source.mapping_json,
        created_by=active_user.id,
    )
    mapping.slug = unique_slug(
        name,
        lambda s: db.query(ControllerMapping).filter(ControllerMapping.slug == s).first() is not None,
        fallback="controller-mapping",
    )
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return mapping_to_read(mapping, db)


@router.patch("/{id}", response_model=ControllerMappingRead)
def update_mapping(
    id: int,
    body: ControllerMappingUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_controller_edit),
):
    mapping = db.get(ControllerMapping, id)
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
    _: User = Depends(require_controller_edit),
):
    mapping = db.get(ControllerMapping, id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Controller mapping not found.")
    db.delete(mapping)
    db.commit()
