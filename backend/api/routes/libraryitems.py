from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import get_active_user, get_filtered_collection, require_permission
from backend.models.library import LibraryItem, LibraryItemRead, LibraryItemUpdate
from backend.models.user import User
from backend.service.library import items as lib_svc

router = APIRouter(prefix="/api/v1", tags=["library"])


def _visible_leaf(leaf_id: int, active_user: User, db: Session) -> LibraryItem:
    """Return a leaf whose parent collection the caller is allowed to see, else 404."""
    leaf = db.get(LibraryItem, leaf_id)
    if leaf is None:
        raise HTTPException(status_code=404, detail="Library item not found.")
    # Enforces the caller's restriction/rating filters on the owning collection.
    get_filtered_collection(leaf.library_collection_id, active_user, db)
    return leaf


@router.get("/libraryitem/{leaf_id}", response_model=LibraryItemRead)
def get_library_item(
    leaf_id: int,
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
):
    return LibraryItemRead.model_validate(_visible_leaf(leaf_id, active_user, db))


@router.patch("/libraryitem/{leaf_id}", response_model=LibraryItemRead)
def update_library_item(
    leaf_id: int,
    body: LibraryItemUpdate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    leaf = db.get(LibraryItem, leaf_id)
    if leaf is None:
        raise HTTPException(status_code=404, detail="Library item not found.")
    return LibraryItemRead.model_validate(
        lib_svc.update_library_leaf(leaf.library_collection_id, leaf_id, body, db)
    )
