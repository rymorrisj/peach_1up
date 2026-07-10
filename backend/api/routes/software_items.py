from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import get_active_user, get_filtered_collection, require_permission
from backend.models.software import SoftwareItem, SoftwareItemRead, SoftwareItemUpdate
from backend.models.user import User
from backend.service.library import items as lib_svc

router = APIRouter(prefix="/api/v1", tags=["library"])


def _visible_leaf(leaf_id: int, active_user: User, db: Session) -> SoftwareItem:
    """Return a leaf whose parent collection the caller is allowed to see, else 404."""
    leaf = db.get(SoftwareItem, leaf_id)
    if leaf is None:
        raise HTTPException(status_code=404, detail="Software item not found.")
    # Enforces the caller's restriction/rating filters on the owning collection.
    get_filtered_collection(leaf.library_collection_id, active_user, db)
    return leaf


@router.get("/softwareitem/{leaf_id}", response_model=SoftwareItemRead)
def get_library_item(
    leaf_id: int,
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
):
    return SoftwareItemRead.model_validate(_visible_leaf(leaf_id, active_user, db))


@router.patch("/softwareitem/{leaf_id}", response_model=SoftwareItemRead)
def update_library_item(
    leaf_id: int,
    body: SoftwareItemUpdate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_software"),
):
    leaf = db.get(SoftwareItem, leaf_id)
    if leaf is None:
        raise HTTPException(status_code=404, detail="Software item not found.")
    return SoftwareItemRead.model_validate(
        lib_svc.update_library_leaf(leaf.library_collection_id, leaf_id, body, db)
    )
