from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import (
    get_active_user, get_filtered_app_item, get_filtered_game_item_bundle,
    require_owner_or_admin, require_permission,
)
from backend.core.logger import get_logger
from backend.models import EnvironmentItem, LaunchHistory
from backend.models.launch_history import LaunchHistoryRead
from backend.models.user import UserItem
from backend.service.launch import coordinator as svc
from backend.service.launch.history import scope_launch_query, user_can_view_launch

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["launches"])

class LaunchRequest(BaseModel):
    profile_item_id: int | None = None


class LaunchResponse(BaseModel):
    launch_history_id: int
    warnings: list[str] = []
    launch_review_flagged: bool = False


@router.post("/game-item-bundle/{collection_id}/launch", status_code=202, response_model=LaunchResponse)
async def launch_collection(
    collection_id: int,
    body: LaunchRequest = LaunchRequest(),
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_launch_media"),
):
    # get_filtered_game_item_bundle enforces the caller's restriction/rating filters and 404s otherwise.
    collection = get_filtered_game_item_bundle(collection_id, active_user, db)
    result = await svc.launch_collection(collection.id, body.profile_item_id, db)
    return LaunchResponse(
        launch_history_id=result.history_id,
        warnings=result.warnings,
        launch_review_flagged=result.launch_review_flagged,
    )


@router.post("/app-item-bundle/{collection_id}/launch", status_code=202, response_model=LaunchResponse)
async def launch_app_collection(
    collection_id: int,
    body: LaunchRequest = LaunchRequest(),
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_launch_media"),
):
    # get_filtered_app_item enforces the caller's manual-blocklist restriction and 404s
    # otherwise. No rating/ceiling filter, Apps have no content_rating concept
    # (backend/models/app.py).
    collection = get_filtered_app_item(collection_id, active_user, db)
    result = await svc.launch_app_collection(collection.id, body.profile_item_id, db)
    return LaunchResponse(
        launch_history_id=result.history_id,
        warnings=result.warnings,
        launch_review_flagged=result.launch_review_flagged,
    )


@router.post("/environment-items/{id}/launch", status_code=202, response_model=LaunchResponse)
async def launch_environment(
    id: int,
    body: LaunchRequest = LaunchRequest(),
    db: Session = Depends(get_db),
    _: UserItem = require_permission("can_launch_media"),
):
    platform = db.get(EnvironmentItem, id)
    if not platform:
        raise HTTPException(status_code=404, detail="Environment not found.")
    logger.info("launch_environment route: id=%d era=%s", id, platform.era)
    try:
        result = await svc.launch_environment(platform, body.profile_item_id, db)
    except HTTPException:
        raise
    except Exception:
        logger.exception("launch_environment route unhandled exception: id=%d", id)
        raise
    return LaunchResponse(
        launch_history_id=result.history_id,
        warnings=result.warnings,
        launch_review_flagged=result.launch_review_flagged,
    )


def _scoped_launch_history(db: Session, active_user: UserItem, q, limit: int) -> list[LaunchHistory]:
    # Scoped: owner/admin see all, other users see only launches attributable to
    # them (their profiles) or unattributed shared launches. See scope_launch_query.
    q = scope_launch_query(q, active_user)
    return q.order_by(LaunchHistory.started_at.desc()).limit(limit).all()


@router.get("/game-item-bundle/{collection_id}/launches", response_model=list[LaunchHistoryRead])
def list_collection_launches(
    collection_id: int,
    db: Session = Depends(get_db),
    active_user: UserItem = Depends(get_active_user),
):
    q = db.query(LaunchHistory).filter(LaunchHistory.game_item_bundle_id == collection_id)
    return _scoped_launch_history(db, active_user, q, limit=20)


@router.get("/launches", response_model=list[LaunchHistoryRead])
def list_launches(
    target_id: Optional[int] = Query(default=None),
    target_type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    active_user: UserItem = Depends(get_active_user),
):
    q = db.query(LaunchHistory)
    if target_id is not None and target_type is not None:
        if target_type == "environment_item":
            q = q.filter(LaunchHistory.environment_item_id == target_id)
        elif target_type == "game_item_bundle":
            q = q.filter(LaunchHistory.game_item_bundle_id == target_id)
        elif target_type == "app_item_bundle":
            q = q.filter(LaunchHistory.app_item_bundle_id == target_id)
        else:
            raise HTTPException(status_code=422, detail=f"Unknown target_type: {target_type!r}")
    return _scoped_launch_history(db, active_user, q, limit=50)


class BulkDeleteLaunchesBody(BaseModel):
    ids: list[int] = []


@router.delete("/launches", status_code=200)
def delete_launches(
    body: BulkDeleteLaunchesBody,
    db: Session = Depends(get_db),
    _: UserItem = Depends(require_owner_or_admin),
):
    """Delete launch history rows by id. Owner/admin only. An empty id list is a
    no-op (returns deleted=0), not an error. Serves both the single-record and
    multi-record ("delete these N checked") UI flows from one endpoint."""
    if not body.ids:
        return {"deleted": 0}
    deleted = (
        db.query(LaunchHistory)
        .filter(LaunchHistory.id.in_(body.ids))
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": deleted}


@router.get("/launches/{history_id}")
def get_launch(
    history_id: int,
    db: Session = Depends(get_db),
    active_user: UserItem = Depends(get_active_user),
):
    record = db.get(LaunchHistory, history_id)
    # Return 404 (not 403) when the record exists but isn't the caller's, so a
    # non-admin can't probe which launch ids exist for other users.
    if not record or not user_can_view_launch(record, active_user, db):
        raise HTTPException(status_code=404, detail="Launch record not found.")
    return record

@router.post("/launches/{history_id}/stop", status_code=200)
def stop_launch(
    history_id: int,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_launch_media"),
):
    return svc.stop_launch(history_id, active_user, db)
