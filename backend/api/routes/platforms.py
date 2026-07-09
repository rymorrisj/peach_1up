from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import get_active_user, require_permission
from backend.core.logger import get_logger
from backend.models.platform import HealthSummary, Platform, PlatformCreate, PlatformRead, PlatformUpdate, StorageStats
from backend.models.user import User
from backend.service.platforms import environments as plat_svc
from backend.service.utils import confirmation_tokens
from backend.service.utils.confirmation_tokens import TOKEN_TTL

router = APIRouter(prefix="/api/v1/platforms", tags=["platforms"], redirect_slashes=False)
logger = get_logger(__name__)


@router.get("", response_model=list[PlatformRead])
def list_platforms(db: Session = Depends(get_db), _: User = Depends(get_active_user)):
    platforms = db.query(Platform).all()
    result = []
    for p in platforms:
        data = PlatformRead.model_validate(p)
        # Recomputed live, not read from the persisted status column, so this
        # always reflects current disk state — same freshness the Emulators
        # page already gets from get_install_path() on every request.
        data.status = plat_svc.compute_live_status(p)
        if p.working_image_path:
            try:
                data.working_image_size_bytes = Path(p.working_image_path).stat().st_size
            except OSError:
                pass
        if p.base_image_path:
            try:
                data.base_image_size_bytes = Path(p.base_image_path).stat().st_size
            except OSError:
                pass
        result.append(data)
    return result


@router.post("", response_model=PlatformRead, status_code=201)
def create_platform(body: PlatformCreate, db: Session = Depends(get_db), _: User = require_permission("can_edit_platforms")):
    return plat_svc.create_platform(body, db)


@router.get("/health", response_model=HealthSummary)
def health_summary(db: Session = Depends(get_db), _: User = require_permission("can_edit_platforms")):
    return plat_svc.get_health_summary(db)


@router.post("/health-all")
def health_check_all(db: Session = Depends(get_db), _: User = require_permission("can_edit_platforms")):
    return plat_svc.batch_health_check(db)


@router.get("/storage-stats", response_model=StorageStats)
def storage_stats(db: Session = Depends(get_db), _: User = require_permission("can_edit_platforms")):
    return plat_svc.get_storage_stats(db)


@router.get("/{platform_id}", response_model=PlatformRead)
def get_platform(platform_id: int, db: Session = Depends(get_db), _: User = Depends(get_active_user)):
    platform = db.get(Platform, platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found.")
    data = PlatformRead.model_validate(platform)
    # Recomputed live, matching list_platforms, so the detail page can't
    # disagree with the list page for the same platform on the same load.
    data.status = plat_svc.compute_live_status(platform)
    return data


@router.patch("/{platform_id}", response_model=PlatformRead)
def update_platform(platform_id: int, body: PlatformUpdate, db: Session = Depends(get_db), _: User = require_permission("can_edit_platforms")):
    return plat_svc.update_platform(platform_id, body, db)


@router.post("/{platform_id}/confirm-delete")
def issue_delete_token(platform_id: int, db: Session = Depends(get_db), _: User = require_permission("can_edit_platforms")):
    if not db.get(Platform, platform_id):
        raise HTTPException(status_code=404, detail="Platform not found.")
    return {"confirmation_token": confirmation_tokens.issue("platform", platform_id, "delete"), "expires_in_seconds": TOKEN_TTL}


@router.delete("/{platform_id}", status_code=204)
def delete_platform(
    platform_id: int,
    confirmation_token: str = Query(...),
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_platforms"),
):
    plat_svc.delete_platform(platform_id, confirmation_token, db)


@router.post("/{platform_id}/health")
def platform_health(platform_id: int, db: Session = Depends(get_db), _: User = require_permission("can_edit_platforms")):
    platform = db.get(Platform, platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found.")
    return plat_svc.check_platform_health(platform, db)
