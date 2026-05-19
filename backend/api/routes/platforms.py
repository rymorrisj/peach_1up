import re
import secrets
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import require_permission
from backend.core.logger import get_logger
from backend.models.platform import Platform, PlatformCreate, PlatformRead, PlatformUpdate
from backend.models.snapshot import Snapshot, SnapshotCreate, SnapshotRead
from backend.models.user import User
from backend.service.utils.settings import get_binary_path

router = APIRouter(prefix="/api/v1/platforms", tags=["platforms"], redirect_slashes=False)
logger = get_logger(__name__)

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

_PC_ERAS = frozenset({"dos", "win31", "win95", "win98", "winxp"})
_PROVISIONABLE_ERAS = frozenset({"win95", "win98", "winxp"})


def _generate_slug(name: str, db: Session) -> str:
    base = re.sub(r'[^a-z0-9-]', '', re.sub(r'\s+', '-', name.lower())).strip('-') or 'platform'
    candidate = base
    n = 2
    while db.query(Platform).filter(Platform.slug == candidate).first():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _validate_image_path(path_str: str) -> Path:
    """Normalise and validate an image path."""
    from backend.service.utils.path_utils import normalise_path
    try:
        resolved = normalise_path(path_str)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not resolved.exists():
        raise HTTPException(status_code=400, detail="Path does not exist.")
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file.")
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
def create_platform(body: PlatformCreate, db: Session = Depends(get_db), _: User = require_permission("can_edit_platforms")):
    if body.era not in _PC_ERAS:
        raise HTTPException(status_code=422, detail=f"Only PC eras are supported: {', '.join(sorted(_PC_ERAS))}.")
    if body.base_image_path:
        _validate_image_path(body.base_image_path)
    if body.working_image_path:
        _validate_image_path(body.working_image_path)
    platform = Platform(**body.model_dump())
    if not platform.slug:
        platform.slug = _generate_slug(platform.name, db)
    db.add(platform)
    db.commit()
    db.refresh(platform)

    if not platform.working_image_path and platform.era in _PROVISIONABLE_ERAS:
        try:
            from backend.service.utils.vm_provisioner import provision_platform
            iso_path, working_path, config_path = provision_platform(platform)
            if iso_path and not platform.base_image_path:
                platform.base_image_path = iso_path
            if working_path:
                platform.working_image_path = working_path
            if config_path:
                platform.config_path = config_path
            db.commit()
            db.refresh(platform)
        except Exception as exc:
            logger.warning(
                "Auto-provisioning failed for platform %d (%s/%s): %s",
                platform.id, platform.era, platform.slug, exc,
            )

    working = platform.working_image_path
    base = platform.base_image_path
    if not working and not base:
        platform.status = "unconfigured"
    else:
        working_ok = bool(working and Path(working).is_file())
        base_ok = bool(base and Path(base).is_file())
        if working_ok:
            platform.status = "healthy"
        elif base_ok:
            platform.status = "degraded"
        else:
            platform.status = "error"
    platform.last_health_check = datetime.now(timezone.utc)
    db.commit()
    db.refresh(platform)

    return platform


@router.post("/health-all")
def health_check_all(db: Session = Depends(get_db)):

    platforms_to_check = db.query(Platform).filter(Platform.is_system == False).all()
    results = []
    for platform in platforms_to_check:
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
        platform.last_health_check = datetime.now(timezone.utc)
        results.append({"id": platform.id, "status": platform.status})
    db.commit()
    return {"results": results, "checked": len(results)}


@router.get("/{platform_id}", response_model=PlatformRead)
def get_platform(platform_id: int, db: Session = Depends(get_db)):
    platform = db.get(Platform, platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found.")
    return platform


@router.patch("/{platform_id}", response_model=PlatformRead)
def update_platform(platform_id: int, body: PlatformUpdate, db: Session = Depends(get_db), _: User = require_permission("can_edit_platforms")):
    platform = db.get(Platform, platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found.")
    updates = body.model_dump(exclude_none=True)
    if "era" in updates and updates["era"] not in _PC_ERAS:
        raise HTTPException(status_code=422, detail=f"Only PC eras are supported: {', '.join(sorted(_PC_ERAS))}.")
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
def issue_delete_token(platform_id: int, db: Session = Depends(get_db), _: User = require_permission("can_edit_platforms")):
    if not db.get(Platform, platform_id):
        raise HTTPException(status_code=404, detail="Platform not found.")
    return {"confirmation_token": _issue_token(platform_id, "delete"), "expires_in_seconds": _TOKEN_TTL}


@router.delete("/{platform_id}", status_code=204)
def delete_platform(
    platform_id: int,
    confirmation_token: str = Query(...),
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_platforms"),
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

    platform = db.get(Platform, platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found.")

    if platform.is_system:
        emulator_key = _EMULATOR_SLUG_TO_BINARY_KEY.get(platform.emulator_slug, "")
        binary_path = get_binary_path(emulator_key) if emulator_key else ""
        exists = bool(binary_path and Path(binary_path).is_file())
        platform.status = "ok" if exists else "missing"
        platform.last_health_check = datetime.now(timezone.utc)
        db.commit()
        return {"status": platform.status, "binary_exists": exists, "binary_path": binary_path or None}

    working = platform.working_image_path
    base = platform.base_image_path

    if not working and not base:
        status = "unconfigured"
    else:
        working_ok = bool(working and Path(working).is_file())
        base_ok = bool(base and Path(base).is_file())
        if working_ok:
            status = "healthy"
        elif base_ok:
            status = "degraded"
        else:
            status = "error"

    platform.status = status
    platform.last_health_check = datetime.now(timezone.utc)
    db.commit()
    return {
        "status": status,
        "working_image_exists": bool(working and Path(working).is_file()),
        "base_image_exists": bool(base and Path(base).is_file()),
    }


# --- Snapshots ---

@router.get("/{platform_id}/snapshots", response_model=list[SnapshotRead])
def list_snapshots(platform_id: int, db: Session = Depends(get_db)):
    if not db.get(Platform, platform_id):
        raise HTTPException(status_code=404, detail="Platform not found.")
    return db.query(Snapshot).filter(Snapshot.platform_id == platform_id).all()


@router.post("/{platform_id}/snapshots", response_model=SnapshotRead, status_code=201)
def create_snapshot(platform_id: int, body: SnapshotCreate, db: Session = Depends(get_db), _: User = require_permission("can_edit_platforms")):
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
def issue_restore_token(platform_id: int, snapshot_id: int, db: Session = Depends(get_db), _: User = require_permission("can_edit_platforms")):
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
    _: User = require_permission("can_edit_platforms"),
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
def issue_snap_delete_token(platform_id: int, snapshot_id: int, db: Session = Depends(get_db), _: User = require_permission("can_edit_platforms")):
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
    _: User = require_permission("can_edit_platforms"),
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
