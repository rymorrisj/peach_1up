from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import get_active_user, get_filtered_game_item_bundle, require_permission
from backend.models.game import GameItem, GameItemRead, GameItemUpdate
from backend.models.user import User
from backend.service.games import items as lib_svc

router = APIRouter(prefix="/api/v1", tags=["games"])


def _visible_leaf(leaf_id: int, active_user: User, db: Session) -> GameItem:
    """Return a leaf whose parent collection the caller is allowed to see, else 404."""
    leaf = db.get(GameItem, leaf_id)
    if leaf is None:
        raise HTTPException(status_code=404, detail="Software item not found.")
    # Enforces the caller's restriction/rating filters on the owning collection.
    get_filtered_game_item_bundle(leaf.game_item_bundle_id, active_user, db)
    return leaf


@router.get("/game-item/{leaf_id}", response_model=GameItemRead)
def get_game_item(
    leaf_id: int,
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
):
    return GameItemRead.model_validate(_visible_leaf(leaf_id, active_user, db))


@router.patch("/game-item/{leaf_id}", response_model=GameItemRead)
def update_game_item(
    leaf_id: int,
    body: GameItemUpdate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_manage_game"),
):
    leaf = db.get(GameItem, leaf_id)
    if leaf is None:
        raise HTTPException(status_code=404, detail="Software item not found.")
    return GameItemRead.model_validate(
        lib_svc.update_library_leaf(leaf.game_item_bundle_id, leaf_id, body, db)
    )
