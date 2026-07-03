from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import get_active_user, get_filtered_collection, require_permission
from backend.core.logger import get_logger
from backend.models import LaunchHistory, Platform
from backend.models.launch_history import LaunchHistoryRead
from backend.models.user import User
from backend.service.launch import coordinator as svc

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["launches"])

class LaunchRequest(BaseModel):
    profile_id: int | None = None


class LaunchResponse(BaseModel):
    launch_history_id: int
    warnings: list[str] = []
    launch_review_flagged: bool = False


@router.post("/library/{collection_id}/launch", status_code=202, response_model=LaunchResponse)
async def launch_collection(
    collection_id: int,
    body: LaunchRequest = LaunchRequest(),
    db: Session = Depends(get_db),
    active_user: User = require_permission("can_launch_media"),
):
    # get_filtered_collection enforces the caller's restriction/rating filters and 404s otherwise.
    collection = get_filtered_collection(collection_id, active_user, db)
    result = await svc.launch_collection(collection.id, body.profile_id, db)
    return LaunchResponse(
        launch_history_id=result.history_id,
        warnings=result.warnings,
        launch_review_flagged=result.launch_review_flagged,
    )


@router.post("/environments/{platform_id}/launch", status_code=202, response_model=LaunchResponse)
async def launch_environment(
    platform_id: int,
    body: LaunchRequest = LaunchRequest(),
    db: Session = Depends(get_db),
    _: User = require_permission("can_launch_media"),
):
    platform = db.get(Platform, platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Environment not found.")
    logger.info("launch_environment route: platform_id=%d era=%s", platform_id, platform.era)
    try:
        result = await svc.launch_environment(platform, body.profile_id, db)
    except HTTPException:
        raise
    except Exception:
        logger.exception("launch_environment route unhandled exception: platform_id=%d", platform_id)
        raise
    return LaunchResponse(
        launch_history_id=result.history_id,
        warnings=result.warnings,
        launch_review_flagged=result.launch_review_flagged,
    )


@router.get("/library/{collection_id}/launches", response_model=list[LaunchHistoryRead])
def list_collection_launches(
    collection_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_active_user),
):
    return (
        db.query(LaunchHistory)
        .filter(LaunchHistory.library_collection_id == collection_id)
        .order_by(LaunchHistory.started_at.desc())
        .limit(20)
        .all()
    )


@router.get("/launches", response_model=list[LaunchHistoryRead])
def list_launches(
    target_id: Optional[int] = Query(default=None),
    target_type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_active_user),
):
    q = db.query(LaunchHistory)
    if target_id is not None and target_type is not None:
        if target_type == "environment":
            q = q.filter(LaunchHistory.platform_id == target_id)
        elif target_type == "library_collection":
            q = q.filter(LaunchHistory.library_collection_id == target_id)
    return q.order_by(LaunchHistory.started_at.desc()).limit(50).all()

@router.get("/launches/{history_id}")
def get_launch(
    history_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_active_user),
):
    record = db.get(LaunchHistory, history_id)
    if not record:
        raise HTTPException(status_code=404, detail="Launch record not found.")
    return record

@router.post("/launches/{history_id}/stop", status_code=200)
def stop_launch(
    history_id: int,
    db: Session = Depends(get_db),
    active_user: User = require_permission("can_launch_media"),
):
    return svc.stop_launch(history_id, active_user, db)
