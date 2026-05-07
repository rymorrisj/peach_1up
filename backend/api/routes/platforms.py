import logging
import secrets
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from backend.core.database import get_db
from backend.core.settings import get_settings
from backend.models import Platform, Snapshot
from backend.schemas.platform import PlatformCreate, PlatformRead, PlatformUpdate
from backend.schemas.snapshot import SnapshotCreate, SnapshotRead
from backend.service.utils.settings import get_binary_path

router = APIRouter(prefix="/api/v1/platforms", tags=["platforms"], redirect_slashes=False)

_TOKEN_TTL = 60
_confirm_tokens: dict[str, tuple[int, str, float]] = {}

# Maps emulator_slug (as stored on Platform) to the key expected by get_binary_path().
# dosbox-x and 86box differ from their slug because get_binary_path() uses the shorter
# legacy keys ("dosbox", "box86") that predate the platform slug scheme.
_EMULATOR_SLUG_TO_BINARY_KEY: dict[str, str] = {
    "dosbox-x":    "dosbox",
    "86box":       "box86",
    "virtualbox":  "virtualbox",
    "duckstation": "duckstation",
    "pcsx2":       "pcsx2",
    "xemu":        "xemu",
    "mesen":       "mesen",
    "project64":   "project64",
}


def _validate_image_path(path_str: str) -> Path:
    """Resolve path and reject anything outside IMAGES_PATH."""
    svc = get_settings()
    images_root = Path(svc.get("IMAGES_PATH", "") or "images").resolve()
    resolved = Path(path_str).resolve()
    if not str(resolved).startswith(str(images_root)):
        raise HTTPException(
            status_code=400,
            detail="Path escapes the permitted images directory. Path traversal rejected.",
        )
    return resolved


def _issue_token(resource_id: int, action: str) -> str:
    token = secrets.token_urlsafe(32)
    _confirm_tokens[token] = (resource_id, action, time.monotonic() + _TOKEN_TTL)
    return token


def _consume_token(token: str, resource_id: int, action: str) -> bool:
    now = time.monotonic()
    expired = [k for k, (_, _, exp) in _confirm_tokens.items() if exp < now]
    for k in expired:
        _confirm_tokens.pop(k, None)
    entry = _confirm_tokens.pop(token, None)
    if entry is None:
        return False
    rid, act, expires_at = entry
    if now > expires_at:
        return False
    return rid == resource_id and act == action


@router.get("", response_model=list[PlatformRead])
def list_platforms(db: Session = Depends(get_db)):
    return db.query(Platform).all()


@router.post("", response_model=PlatformRead, status_code=201)
def create_platform(body: PlatformCreate, db: Session = Depends(get_db)):
    if body.base_image_path:
        _validate_image_path(body.base_image_path)
    if body.working_image_path:
        _validate_image_path(body.working_image_path)
    platform = Platform(**body.model_dump())
    db.add(platform)
    db.commit()
    db.refresh(platform)
    return platform


@router.get("/{platform_id}", response_model=PlatformRead)
def get_platform(platform_id: int, db: Session = Depends(get_db)):
    platform = db.get(Platform, platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found.")
    return platform


@router.patch("/{platform_id}", response_model=PlatformRead)
def update_platform(platform_id: int, body: PlatformUpdate, db: Session = Depends(get_db)):
    platform = db.get(Platform, platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found.")
    updates = body.model_dump(exclude_none=True)
    if "base_image_path" in updates:
        _validate_image_path(updates["base_image_path"])
    if "working_image_path" in updates:
        _validate_image_path(updates["working_image_path"])
    for key, value in updates.items():
        setattr(platform, key, value)
    db.commit()
    db.refresh(platform)
    return platform


@router.post("/{platform_id}/confirm-delete")
def issue_delete_token(platform_id: int, db: Session = Depends(get_db)):
    if not db.get(Platform, platform_id):
        raise HTTPException(status_code=404, detail="Platform not found.")
    return {"confirmation_token": _issue_token(platform_id, "delete"), "expires_in_seconds": _TOKEN_TTL}


@router.delete("/{platform_id}", status_code=204)
def delete_platform(
    platform_id: int,
    confirmation_token: str = Query(...),
    db: Session = Depends(get_db),
):
    if not _consume_token(confirmation_token, platform_id, "delete"):
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation token.")
    platform = db.get(Platform, platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found.")
    db.delete(platform)
    db.commit()


@router.post("/{platform_id}/health")
def platform_health(platform_id: int, db: Session = Depends(get_db)):
    from datetime import datetime
    platform = db.get(Platform, platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found.")

    if platform.is_system:
        emulator_key = _EMULATOR_SLUG_TO_BINARY_KEY.get(platform.emulator_slug, "")
        binary_path = get_binary_path(emulator_key) if emulator_key else ""
        exists = bool(binary_path and Path(binary_path).is_file())
        platform.status = "ok" if exists else "missing"
        platform.last_health_check = datetime.utcnow()
        db.commit()
        return {"status": platform.status, "binary_exists": exists, "binary_path": binary_path or None}

    working = platform.working_image_path
    if working:
        try:
            _validate_image_path(working)
            exists = Path(working).exists()
        except HTTPException:
            exists = False
    else:
        exists = False
    platform.status = "ok" if exists else "missing"
    platform.last_health_check = datetime.utcnow()
    db.commit()
    return {"status": platform.status, "working_image_exists": exists}


# --- Snapshots ---

@router.get("/{platform_id}/snapshots", response_model=list[SnapshotRead])
def list_snapshots(platform_id: int, db: Session = Depends(get_db)):
    if not db.get(Platform, platform_id):
        raise HTTPException(status_code=404, detail="Platform not found.")
    return db.query(Snapshot).filter(Snapshot.platform_id == platform_id).all()


@router.post("/{platform_id}/snapshots", response_model=SnapshotRead, status_code=201)
def create_snapshot(platform_id: int, body: SnapshotCreate, db: Session = Depends(get_db)):
    platform = db.get(Platform, platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found.")
    if not platform.working_image_path:
        raise HTTPException(status_code=422, detail="Platform has no working image to snapshot.")
    src = _validate_image_path(platform.working_image_path)
    if not src.exists():
        raise HTTPException(status_code=422, detail="Working image file does not exist.")
    dest = src.parent / f"{src.stem}_snapshot_{body.name}{src.suffix}"
    shutil.copy2(src, dest)
    size = dest.stat().st_size
    snap = Snapshot(
        platform_id=platform_id,
        name=body.name,
        image_path=str(dest),
        size_bytes=size,
        notes=body.notes,
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


@router.post("/{platform_id}/snapshots/{snapshot_id}/confirm-restore")
def issue_restore_token(platform_id: int, snapshot_id: int, db: Session = Depends(get_db)):
    snap = db.get(Snapshot, snapshot_id)
    if not snap or snap.platform_id != platform_id:
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    return {"confirmation_token": _issue_token(snapshot_id, "restore"), "expires_in_seconds": _TOKEN_TTL}


@router.post("/{platform_id}/snapshots/{snapshot_id}/restore", status_code=200)
def restore_snapshot(
    platform_id: int,
    snapshot_id: int,
    confirmation_token: str = Query(...),
    db: Session = Depends(get_db),
):
    if not _consume_token(confirmation_token, snapshot_id, "restore"):
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation token.")
    snap = db.get(Snapshot, snapshot_id)
    if not snap or snap.platform_id != platform_id:
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    platform = db.get(Platform, platform_id)
    if not platform or not platform.working_image_path:
        raise HTTPException(status_code=422, detail="Platform working image not set.")
    src = _validate_image_path(snap.image_path)
    dest = _validate_image_path(platform.working_image_path)
    shutil.copy2(src, dest)
    return {"restored": True, "snapshot": snap.name}


@router.post("/{platform_id}/snapshots/{snapshot_id}/confirm-delete")
def issue_snap_delete_token(platform_id: int, snapshot_id: int, db: Session = Depends(get_db)):
    snap = db.get(Snapshot, snapshot_id)
    if not snap or snap.platform_id != platform_id:
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    return {"confirmation_token": _issue_token(snapshot_id, "snap-delete"), "expires_in_seconds": _TOKEN_TTL}


@router.delete("/{platform_id}/snapshots/{snapshot_id}", status_code=204)
def delete_snapshot(
    platform_id: int,
    snapshot_id: int,
    confirmation_token: str = Query(...),
    db: Session = Depends(get_db),
):
    if not _consume_token(confirmation_token, snapshot_id, "snap-delete"):
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation token.")
    snap = db.get(Snapshot, snapshot_id)
    if not snap or snap.platform_id != platform_id:
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    try:
        p = Path(snap.image_path)
        if p.exists():
            p.unlink()
    except OSError as exc:
        logger.warning("Failed to delete snapshot file %s: %s", snap.image_path, exc)
    db.delete(snap)
    db.commit()
