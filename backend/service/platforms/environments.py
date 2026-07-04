from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.models.platform import Platform, PlatformCreate, PlatformUpdate
from backend.models.snapshot import Snapshot, SnapshotCreate
from backend.service.utils.confirmation_tokens import consume as _consume
from backend.service.utils.slug_generator import unique_slug

_PLATFORM_ERAS = frozenset({"dos", "win31", "win95", "win98", "winxp"})
# Only the 86Box eras get an auto-provisioned working image at create time.
# DOS/Win3.1 launches mount the per-item drive (drive_hydration), never the
# platform's working image — dosbox.py reads spec.drive_image_path only, never
# working_image_path — so provisioning one for them writes a file nothing ever
# mounts. Excluded here to avoid that orphaned-on-create image.
_PROVISIONABLE_ERAS = frozenset({"win95", "win98", "winxp"})

MAX_SNAPSHOTS_PER_PLATFORM = 10


def _check_free_space(dest_dir: Path, required_bytes: int) -> None:
    """Raise HTTPException(507) if *dest_dir* has less free space than *required_bytes*."""
    usage = shutil.disk_usage(dest_dir)
    if usage.free < required_bytes:
        raise HTTPException(
            status_code=507,
            detail=(
                f"Insufficient disk space: need {required_bytes // (1024 * 1024)} MiB, "
                f"only {usage.free // (1024 * 1024)} MiB free."
            ),
        )


def _validate_image_path(path_str: str) -> Path:
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


def _probe_image_integrity(path: Path) -> bool:
    """Cheap interrupted-write/corruption check for a working image.

    Not a format validator (working images may be raw .img, .vhd, or a
    pre-installed copy with varying internal layouts) — just confirms the
    file is non-empty and its header and tail (where a VHD footer would
    live, per vm/vhd.py) are actually readable. A zero-byte or truncated
    file from an interrupted copy fails this; a legitimately fresh,
    not-yet-installed disk image does not.
    """
    try:
        size = path.stat().st_size
        if size == 0:
            return False
        with path.open("rb") as f:
            if not f.read(512):
                return False
            f.seek(max(0, size - 512))
            if not f.read(512):
                return False
    except OSError:
        return False
    return True


def _compute_status(era: str, working: str | None, base: str | None) -> str:
    if era not in _PROVISIONABLE_ERAS:
        # DOS/win31 never get a working image (see _PROVISIONABLE_ERAS comment
        # above — launches mount the per-item drive instead), so its absence
        # is the expected, healthy state for these eras, not "degraded". Only
        # base_image_path (optional, Advanced-only field for these eras) is
        # evaluated.
        if not base:
            return "unconfigured"
        return "healthy" if Path(base).is_file() else "error"

    if not working and not base:
        return "unconfigured"
    working_ok = bool(working and Path(working).is_file())
    base_ok = bool(base and Path(base).is_file())
    if not working_ok:
        return "degraded" if base_ok else "error"
    if not base_ok:
        return "degraded"
    if not _probe_image_integrity(Path(working)):
        return "degraded"
    return "healthy"


def compute_live_status(platform: Platform) -> str:
    """Uncached status for *platform*, safe to call on every read (list/summary
    endpoints) as well as before persisting (health-check endpoints) — a single
    implementation for both so the two paths can't drift apart again."""
    if platform.is_system:
        from backend.service.utils.emulator_catalog import get_install_path as _get_install_path
        install_path = _get_install_path(platform.emulator_slug) if platform.emulator_slug else None
        return "ok" if install_path is not None else "missing"
    return _compute_status(platform.era, platform.working_image_path, platform.base_image_path)


def create_platform(body: PlatformCreate, db: Session) -> Platform:
    from backend.core.logger import get_logger
    logger = get_logger(__name__)

    if body.era not in _PLATFORM_ERAS:
        raise HTTPException(status_code=422, detail=f"Only PC eras are supported: {', '.join(sorted(_PLATFORM_ERAS))}.")
    if body.base_image_path:
        _validate_image_path(body.base_image_path)
    if body.working_image_path:
        _validate_image_path(body.working_image_path)

    platform = Platform(**body.model_dump())
    if not platform.slug:
        platform.slug = unique_slug(
            platform.name,
            lambda s: db.query(Platform).filter(Platform.slug == s).first() is not None,
            fallback="platform",
        )
    db.add(platform)
    db.commit()
    db.refresh(platform)

    if not platform.working_image_path and platform.era in _PROVISIONABLE_ERAS:
        try:
            from backend.service.utils.vm import provision_platform
            _iso, working_path, config_path, _install_path, _rom_path = provision_platform(platform)
            if _iso and not platform.base_image_path:
                platform.base_image_path = _iso
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

    platform.status = compute_live_status(platform)
    platform.last_health_check = datetime.now(timezone.utc)
    db.commit()
    db.refresh(platform)
    return platform


def delete_platform(platform_id: int, token: str, db: Session) -> None:
    if not _consume(token, "platform", platform_id, "delete"):
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation token.")
    platform = db.get(Platform, platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found.")
    db.delete(platform)
    db.commit()


def update_platform(platform_id: int, body: PlatformUpdate, db: Session) -> Platform:
    platform = db.get(Platform, platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found.")
    updates = body.model_dump(exclude_none=True)
    if "era" in updates and updates["era"] not in _PLATFORM_ERAS:
        raise HTTPException(status_code=422, detail=f"Only PC eras are supported: {', '.join(sorted(_PLATFORM_ERAS))}.")
    if "base_image_path" in updates:
        _validate_image_path(updates["base_image_path"])
    if "working_image_path" in updates:
        _validate_image_path(updates["working_image_path"])
    for key, value in updates.items():
        setattr(platform, key, value)
    db.commit()
    db.refresh(platform)
    return platform


def check_platform_health(platform: Platform, db: Session) -> dict:
    status = compute_live_status(platform)
    platform.status = status
    platform.last_health_check = datetime.now(timezone.utc)
    db.commit()

    if platform.is_system:
        from backend.service.utils.emulator_catalog import get_install_path as _get_install_path
        install_path = _get_install_path(platform.emulator_slug) if platform.emulator_slug else None
        return {
            "status": status,
            "binary_exists": install_path is not None,
            "binary_path": str(install_path) if install_path else None,
        }

    return {
        "status": status,
        "working_image_exists": bool(platform.working_image_path and Path(platform.working_image_path).is_file()),
        "base_image_exists": bool(platform.base_image_path and Path(platform.base_image_path).is_file()),
    }


def batch_health_check(db: Session) -> dict:
    platforms = db.query(Platform).filter(Platform.is_system == False).all()
    results = []
    for platform in platforms:
        status = compute_live_status(platform)
        platform.status = status
        platform.last_health_check = datetime.now(timezone.utc)
        results.append({"id": platform.id, "status": status})
    db.commit()
    return {"results": results, "checked": len(results)}


def get_health_summary(db: Session) -> dict:
    from sqlalchemy import func, distinct as sa_distinct
    from backend.models.library import LibraryCollection, LibraryItem
    from backend.service.utils.emulator_catalog import (
        check_bios_presence,
        get_install_path,
        load_bios_requirements,
        load_catalog,
    )

    user_platforms = db.query(Platform).filter(Platform.is_system == False).all()
    # Computed live (not read from the persisted status column) so this always
    # matches what list_platforms/GET /platforms shows on the same page load —
    # see compute_live_status.
    live_statuses = [compute_live_status(p) for p in user_platforms]
    platform_healthy = sum(1 for s in live_statuses if s in ("ok", "healthy"))
    platform_unconfigured = sum(1 for s in live_statuses if s == "unconfigured")
    platform_degraded = len(user_platforms) - platform_healthy - platform_unconfigured

    # "library total" = number of games (collections); a multi-disc set counts once.
    library_count = db.query(LibraryCollection).count()
    # Count actual per-collection Drive rows (mirrors get_drive_images_bytes, which
    # sums those same rows' image files).
    from backend.models.drive import Drive
    drive_count = db.query(Drive).count()
    extension_count = (
        db.query(func.count(sa_distinct(LibraryItem.media_type)))
        .filter(LibraryItem.media_type.isnot(None))
        .scalar() or 0
    )

    catalog = load_catalog()
    emulator_total = len(catalog)
    emulator_installed = sum(1 for e in catalog if get_install_path(e["slug"]) is not None)

    bios_reqs = load_bios_requirements()
    bios_total = len(bios_reqs)
    bios_present = sum(
        1 for b in bios_reqs
        if b.get("bios_path") and check_bios_presence(
            b["bios_path"],
            required_files=b.get("required_files"),
            required_glob=b.get("required_glob"),
            required_glob_excludes=b.get("required_glob_excludes"),
        )
    )

    rom_entries = [e for e in catalog if e.get("install_type") == "rom_pack"]
    rom_total = len(rom_entries)
    rom_installed = sum(1 for e in rom_entries if get_install_path(e["slug"]) is not None)

    return {
        "platforms": {
            "total": len(user_platforms),
            "healthy": platform_healthy,
            "degraded": platform_degraded,
            "unconfigured": platform_unconfigured,
        },
        "library": {"total": library_count},
        "drives": {"total": drive_count},
        "extensions": {"total": extension_count},
        "emulators": {"total": emulator_total, "installed": emulator_installed},
        "bios": {"total": bios_total, "present": bios_present},
        "rom_packs": {"total": rom_total, "installed": rom_installed},
    }


def _safe_file_size(path: str | None) -> int:
    if not path:
        return 0
    try:
        return os.path.getsize(path) if os.path.isfile(path) else 0
    except OSError:
        return 0


def get_drive_images_bytes(db: Session) -> int:
    from backend.models.drive import Drive
    return sum(_safe_file_size(d.image_path) for d in db.query(Drive).all())


def get_storage_stats(db: Session) -> dict:
    from backend.models.library import LibraryItem
    from backend.service.utils import settings as _settings
    from backend.service.utils.emulator_catalog import (
        get_settings_key as _get_settings_key,
        load_catalog as _load_catalog,
    )

    drive_images_bytes = get_drive_images_bytes(db)
    source_media_bytes = sum(_safe_file_size(item.media_path) for item in db.query(LibraryItem).all())
    os_images_bytes = sum(
        _safe_file_size(p.base_image_path) + _safe_file_size(p.working_image_path)
        for p in db.query(Platform).all()
    )
    emulator_binaries_bytes = sum(
        _safe_file_size(_settings.get(_get_settings_key(e["slug"])) or "")
        for e in _load_catalog()
        if e.get("install_type") != "rom_pack"
    )

    return {
        "drive_images_bytes": drive_images_bytes,
        "source_media_bytes": source_media_bytes,
        "os_images_bytes": os_images_bytes,
        "emulator_binaries_bytes": emulator_binaries_bytes,
    }


def _atomic_copy(src: Path, dest: Path) -> None:
    """Copy src onto dest via a same-directory tmp file + atomic replace.

    Mirrors the .tmp + os.replace pattern in routes/emulators.py's
    _write_xemu_toml. A failure partway through shutil.copy2 (disk full,
    process killed) leaves only the orphaned tmp file — dest, if it already
    existed (e.g. a live working image being restored onto), is never seen
    in a partially-written state.
    """
    tmp = dest.parent / (dest.name + ".tmp")
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def create_snapshot(platform_id: int, body: SnapshotCreate, db: Session) -> Snapshot:
    platform = db.get(Platform, platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found.")
    if not platform.working_image_path:
        raise HTTPException(status_code=422, detail="Platform has no working image to snapshot.")
    existing_count = (
        db.query(Snapshot).filter(Snapshot.platform_id == platform_id).count()
    )
    if existing_count >= MAX_SNAPSHOTS_PER_PLATFORM:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Snapshot limit reached ({MAX_SNAPSHOTS_PER_PLATFORM} per platform). "
                "Delete an existing snapshot before creating a new one."
            ),
        )
    src = _validate_image_path(platform.working_image_path)
    if not src.exists():
        raise HTTPException(status_code=422, detail="Working image file does not exist.")
    safe_name = body.name.replace("/", "_").replace("\\", "_").replace("..", "_")
    if not safe_name or safe_name.strip(".") == "":
        raise HTTPException(status_code=422, detail="Snapshot name is invalid.")
    dest = src.parent / f"{src.stem}_snapshot_{safe_name}{src.suffix}"
    _check_free_space(dest.parent, src.stat().st_size)
    _atomic_copy(src, dest)
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


def restore_snapshot(platform_id: int, snapshot_id: int, token: str, db: Session) -> dict:
    if not _consume(token, "snapshot", snapshot_id, "restore"):
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation token.")
    snap = db.get(Snapshot, snapshot_id)
    if not snap or snap.platform_id != platform_id:
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    platform = db.get(Platform, platform_id)
    if not platform or not platform.working_image_path:
        raise HTTPException(status_code=422, detail="Platform working image not set.")
    src = _validate_image_path(snap.image_path)
    dest = _validate_image_path(platform.working_image_path)
    _check_free_space(dest.parent, src.stat().st_size)
    _atomic_copy(src, dest)
    return {"restored": True, "snapshot": snap.name}


def delete_snapshot(platform_id: int, snapshot_id: int, token: str, db: Session) -> None:
    from backend.core.logger import get_logger
    logger = get_logger(__name__)

    if not _consume(token, "snapshot", snapshot_id, "snap-delete"):
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
