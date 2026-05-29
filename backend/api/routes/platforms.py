from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import require_permission
from backend.core.logger import get_logger
from backend.models.platform import Platform, PlatformCreate, PlatformRead, PlatformUpdate
from backend.models.snapshot import Snapshot, SnapshotCreate, SnapshotRead
from backend.models.user import User
from backend.service.platforms import environments as plat_svc
from backend.service.utils import confirmation_tokens
from backend.service.utils.confirmation_tokens import TOKEN_TTL

router = APIRouter(prefix="/api/v1/platforms", tags=["platforms"], redirect_slashes=False)
logger = get_logger(__name__)


@router.get("", response_model=list[PlatformRead])
def list_platforms(db: Session = Depends(get_db)):
    platforms = db.query(Platform).all()
    result = []
    for p in platforms:
        data = PlatformRead.model_validate(p)
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


@router.get("/health")
def health_summary(db: Session = Depends(get_db), _: User = require_permission("can_edit_platforms")):
    return plat_svc.get_health_summary(db)


@router.post("/health-all")
def health_check_all(db: Session = Depends(get_db), _: User = require_permission("can_edit_platforms")):
    return plat_svc.batch_health_check(db)


@router.get("/storage-stats")
def storage_stats(db: Session = Depends(get_db), _: User = require_permission("can_edit_platforms")):
    return plat_svc.get_storage_stats(db)


@router.get("/{platform_id}", response_model=PlatformRead)
def get_platform(platform_id: int, db: Session = Depends(get_db)):
    platform = db.get(Platform, platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found.")
    return platform


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


# --- Snapshots ---

@router.get("/{platform_id}/snapshots", response_model=list[SnapshotRead])
def list_snapshots(platform_id: int, db: Session = Depends(get_db)):
    if not db.get(Platform, platform_id):
        raise HTTPException(status_code=404, detail="Platform not found.")
    return db.query(Snapshot).filter(Snapshot.platform_id == platform_id).all()


@router.post("/{platform_id}/snapshots", response_model=SnapshotRead, status_code=201)
def create_snapshot(platform_id: int, body: SnapshotCreate, db: Session = Depends(get_db), _: User = require_permission("can_edit_platforms")):
    return plat_svc.create_snapshot(platform_id, body, db)


@router.post("/{platform_id}/snapshots/{snapshot_id}/confirm-restore")
def issue_restore_token(platform_id: int, snapshot_id: int, db: Session = Depends(get_db), _: User = require_permission("can_edit_platforms")):
    snap = db.get(Snapshot, snapshot_id)
    if not snap or snap.platform_id != platform_id:
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    return {"confirmation_token": confirmation_tokens.issue("snapshot", snapshot_id, "restore"), "expires_in_seconds": TOKEN_TTL}


@router.post("/{platform_id}/snapshots/{snapshot_id}/restore", status_code=200)
def restore_snapshot(
    platform_id: int,
    snapshot_id: int,
    confirmation_token: str = Query(...),
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_platforms"),
):
    return plat_svc.restore_snapshot(platform_id, snapshot_id, confirmation_token, db)


@router.post("/{platform_id}/snapshots/{snapshot_id}/confirm-delete")
def issue_snap_delete_token(platform_id: int, snapshot_id: int, db: Session = Depends(get_db), _: User = require_permission("can_edit_platforms")):
    snap = db.get(Snapshot, snapshot_id)
    if not snap or snap.platform_id != platform_id:
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    return {"confirmation_token": confirmation_tokens.issue("snapshot", snapshot_id, "snap-delete"), "expires_in_seconds": TOKEN_TTL}


@router.delete("/{platform_id}/snapshots/{snapshot_id}", status_code=204)
def delete_snapshot(
    platform_id: int,
    snapshot_id: int,
    confirmation_token: str = Query(...),
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_platforms"),
):
    plat_svc.delete_snapshot(platform_id, snapshot_id, confirmation_token, db)
