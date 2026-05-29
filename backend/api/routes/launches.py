import asyncio
import hashlib
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.core.settings import get_base_path
from backend.service.utils.fat import FAT16_SIZE_MIN_MB, FAT16_SIZE_MAX_MB, format_fat16, write_file_to_image, read_file_from_image

from backend.core import process_registry
from backend.core.database import get_db
from backend.core.dependencies import get_active_user, require_permission
from backend.core.logger import get_logger
from backend.core.process_registry import ProcessEntry
from backend.models import LaunchHistory, LibraryItem, Platform, Profile
from backend.models.drive import Drive
from backend.models.launch_history import LaunchHistoryRead
from backend.models.user import User

router = APIRouter(prefix="/api/v1", tags=["launches"])
logger = get_logger(__name__)

def _resolve_item_drive(item, profile, db):
    return db.query(Drive).filter(Drive.library_item_id == item.id).first()

def _copy_loose_files_to_drive(src_dir: Path, img_path: Path, size_mb: int) -> None:
    if not src_dir.is_dir():
        raise RuntimeError(f"src_dir is not a directory: {src_dir}")
    files = [f for f in src_dir.rglob("*") if f.is_file() and f.resolve() != img_path.resolve()]
    if not files:
        raise RuntimeError(f"No files found under {src_dir}")
    for f in files:
        data = f.read_bytes()
        src_md5 = hashlib.md5(data).hexdigest()
        rel = f.relative_to(src_dir)
        dest = str(rel).replace("\\", "/")
        write_file_to_image(img_path, dest, data)
        read_back = read_file_from_image(img_path, dest)
        img_md5 = hashlib.md5(read_back).hexdigest()
        if src_md5 != img_md5:
            raise RuntimeError(
                f"MD5 mismatch for {f}: src={src_md5} img={img_md5}"
            )

class LaunchRequest(BaseModel):
    profile_id: int | None = None

class LaunchResponse(BaseModel):
    launch_history_id: int
    warnings: list[str] = []
    launch_review_flagged: bool = False

def _finalize_launch(
    history: LaunchHistory,
    result,
    db: Session,
    *,
    network_blocked: bool,
    item_id: int | None = None,
    profile_id: int | None = None,
) -> None:
    proc = result[0] if isinstance(result, tuple) else result
    job = result[1] if isinstance(result, tuple) and len(result) > 1 else None

    if proc is not None:
        if job is None or getattr(job, "job_handle", None) is None:
            try:
                proc.kill()
            except Exception:
                pass
            history.error_message = "Launch aborted: Job Object isolation is required but unavailable."
            history.ended_at = datetime.now(timezone.utc)
            history.exit_code = -1
            db.commit()
            raise HTTPException(
                status_code=500,
                detail="Launch failed: Job Object isolation is required but unavailable on this system.",
            )
        entry = ProcessEntry(
            process_handle=proc,
            job_handle=job,
            library_item_id=item_id,
            profile_id=profile_id,
            launch_history_id=history.id,
        )
        process_registry.register(proc.pid, entry)
        history.job_isolated = True
        history.sandboxed = True
        history.sandbox_memory_limit_mb = job.memory_limit_mb
        history.sandbox_cpu_limit_percent = job.cpu_limit_percent
        history.network_blocked = network_blocked
        db.commit()


def _flag_short_lived_item(item_id: int) -> None:
    from backend.core.database import get_engine
    from sqlalchemy.orm import Session as _Session
    try:
        with _Session(get_engine()) as db:
            item = db.get(LibraryItem, item_id)
            if item is not None:
                item.launch_review_flagged = True
                db.commit()
    except Exception as exc:
        logger.warning("Failed to set launch_review_flagged for item %d: %s", item_id, exc)

def _monitor_short_lived_launch(item_id: int, proc, launch_time: float, *, _timeout: float = 3.0) -> None:
    deadline = launch_time + _timeout
    exit_code = None
    while time.monotonic() < deadline:
        exit_code = proc.poll()
        if exit_code is not None:
            break
        time.sleep(0.05)

    if exit_code is None:
        return

    lifetime = time.monotonic() - launch_time
    logger.warning(
        "Short-lived DOS launch detected: item_id=%d exit_code=%r lifetime=%.2fs — flagging for review",
        item_id, exit_code, lifetime,
    )
    _flag_short_lived_item(item_id)

@router.post("/library/{item_id}/launch", status_code=202, response_model=LaunchResponse)
async def launch_item(
    item_id: int,
    body: LaunchRequest = LaunchRequest(),
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
    _: User = require_permission("can_launch_media"),
):
    item = db.get(LibraryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Library item not found.")

    # Reap any processes that exited since the last monitor poll so the gate
    # check below never blocks on a dead registry entry.
    _exited = process_registry.cleanup_exited()
    if _exited:
        from backend.core.lifespan import _write_session_ends
        await asyncio.to_thread(_write_session_ends, _exited)

    # Enforce one active launch per user profile.
    # Fall back to item.profile_id so the gate fires even when the caller omits profile_id.
    _gate_profile_id = body.profile_id if body.profile_id is not None else item.profile_id
    if _gate_profile_id is not None:
        for _, entry in process_registry.get_all().items():
            if entry.profile_id == _gate_profile_id:
                raise HTTPException(status_code=409, detail="A launch is already active for this profile.")

    # Resolve profile — binary path comes from settings, not request
    profile: Profile | None = None
    if body.profile_id:
        profile = db.get(Profile, body.profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found.")

    if profile is None and item.profile_id:
        profile = db.get(Profile, item.profile_id)

    if profile is None:
        raise HTTPException(status_code=422, detail="No profile associated with this library item.")

    platform_record = db.query(Platform).filter(Platform.profile_id == profile.id).first()

    from backend.service.utils.backend_router import launch_media

    network_blocked = not bool(getattr(profile, 'enable_networking', False))

    drive = _resolve_item_drive(item, profile, db)
    if drive is None:
        from backend.service.utils.drive_utils import create_drive_for_item
        drive = create_drive_for_item(item, db)

    # First-launch copy for loose-file DOS items
    if (
        drive is not None
        and not item.installed
        and not item.requires_install
        and Path(item.media_path).is_dir()
    ):
        if not drive.image_path:
            raise RuntimeError(f"Drive id={drive.id!r} has no image_path — re-add the library item.")
        img_path = Path(drive.image_path)
        # item.installed is False → any existing image is from a prior failed attempt; remove it.
        if img_path.exists():
            img_path.unlink()
        from backend.service.utils.drive_utils import compute_drive_size_mb
        fresh_size = max(FAT16_SIZE_MIN_MB, min(
            compute_drive_size_mb(Path(item.media_path), item.media_type or ""),
            FAT16_SIZE_MAX_MB,
        ))
        if fresh_size != drive.size_mb:
            drive.size_mb = fresh_size
            db.add(drive)
            db.commit()
        format_fat16(img_path, fresh_size)
        _copy_loose_files_to_drive(Path(item.media_path), img_path, fresh_size)
        item.installed = True
        db.add(item)
        db.commit()

    # Prefer the item's explicitly set launch file over the raw media_path.
    # For folder-based items (scanned from a folder), media_path is the
    # folder — executable_path is the detected or user-set launch file.
    effective_media_path = item.executable_path if item.executable_path else item.media_path
    if Path(effective_media_path).is_dir() and drive is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "No launch file is set for this item. "
                "Open the item detail page and browse to select the file to launch."
            ),
        )

    history = LaunchHistory(
        library_item_id=item.id,
        profile_id=profile.id if profile else None,
        emulator_slug=profile.emulator_slug if profile else "",
        started_at=datetime.now(timezone.utc),
        network_blocked=False,
        job_isolated=False,
    )
    db.add(history)
    db.commit()
    db.refresh(history)

    warnings: list[str] = []

    try:
        result = await asyncio.to_thread(
            launch_media,
            item.era,
            effective_media_path,
            profile,
            platform_record,
            launch_commands=item.launch_commands,
            drive=drive,
        )
    except Exception as exc:
        logger.exception("Launch failed")
        history.error_message = str(exc)
        history.ended_at = datetime.now(timezone.utc)
        history.exit_code = -1
        db.commit()
        raise HTTPException(status_code=500, detail=f"Launch failed: {exc}")

    proc = result[0] if isinstance(result, tuple) else result
    _finalize_launch(
        history, result, db,
        network_blocked=network_blocked,
        item_id=item.id,
        profile_id=profile.id if profile else None,
    )

    if proc is not None:
        from backend.service.utils.backend_router import resolve_backend_name
        from backend.constants_generated import BackendSlug, Era
        try:
            _backend_name = resolve_backend_name(Era(item.era))
        except Exception:
            _backend_name = ""
        if _backend_name == BackendSlug.DOSBOX.value:
            threading.Thread(
                target=_monitor_short_lived_launch,
                args=(item.id, proc, time.monotonic()),
                daemon=True,
                name=f"peach1up_shortlived_{item.id}",
            ).start()

    return LaunchResponse(
        launch_history_id=history.id,
        warnings=warnings,
        launch_review_flagged=item.launch_review_flagged,
    )

@router.post("/environments/{platform_id}/launch", status_code=202, response_model=LaunchResponse)
async def launch_environment(
    platform_id: int,
    body: LaunchRequest = LaunchRequest(),
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
    _: User = require_permission("can_launch_media"),
):
    platform = db.get(Platform, platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Environment not found.")

    _exited = process_registry.cleanup_exited()
    if _exited:
        from backend.core.lifespan import _write_session_ends
        await asyncio.to_thread(_write_session_ends, _exited)

    _gate_profile_id = body.profile_id if body.profile_id is not None else platform.profile_id
    if _gate_profile_id is not None:
        for _, entry in process_registry.get_all().items():
            if entry.profile_id == _gate_profile_id:
                raise HTTPException(status_code=409, detail="A launch is already active for this profile.")

    profile: Profile | None = None
    if body.profile_id:
        profile = db.get(Profile, body.profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found.")
    if profile is None and platform.profile_id:
        profile = db.get(Profile, platform.profile_id)
    if profile is None:
        profile = db.query(Profile).filter(
            Profile.era == platform.era,
            Profile.is_bundled.is_(True),
        ).first()
    if profile is None:
        raise HTTPException(status_code=422, detail="No profile found for this environment's era.")

    if platform.working_image_path is None and platform.era in {"win95", "win98", "winxp"}:
        try:
            from backend.service.utils.vm import provision_platform
            _iso_path, working_path, config_path = await asyncio.to_thread(provision_platform, platform)
            if _iso_path and not platform.base_image_path:
                db.execute(
                    update(Platform)
                    .where(Platform.id == platform.id)
                    .values(base_image_path=str(_iso_path))
                )
                db.flush()
            if working_path:
                platform.working_image_path = working_path
            if config_path:
                platform.config_path = config_path
            db.commit()
            db.refresh(platform)
        except Exception as exc:
            logger.exception("On-launch provisioning failed for platform %d", platform_id)
            raise HTTPException(
                status_code=422,
                detail=f"Environment has no working image and automatic provisioning failed: {exc}",
            )

    if platform.working_image_path is None:
        raise HTTPException(
            status_code=422,
            detail="Environment has no working image. Provisioning is not available for this era.",
        )

    from backend.service.utils.backend_router import launch_media

    network_blocked = not bool(getattr(profile, 'enable_networking', False))

    history = LaunchHistory(
        target_type="environment",
        platform_id=platform.id,
        profile_id=profile.id,
        emulator_slug=profile.emulator_slug,
        started_at=datetime.now(timezone.utc),
        network_blocked=False,
        job_isolated=False,
    )
    db.add(history)
    db.commit()
    db.refresh(history)

    warnings: list[str] = []

    try:
        result = await asyncio.to_thread(
            launch_media,
            platform.era,
            None,
            profile,
            platform,
        )
    except Exception as exc:
        logger.exception("Environment launch failed")
        history.error_message = str(exc)
        history.ended_at = datetime.now(timezone.utc)
        history.exit_code = -1
        db.commit()
        raise HTTPException(status_code=500, detail=f"Launch failed: {exc}")

    _finalize_launch(history, result, db, network_blocked=network_blocked, profile_id=profile.id)

    return LaunchResponse(launch_history_id=history.id, warnings=warnings)

@router.get("/library/{item_id}/launches", response_model=list[LaunchHistoryRead])
def list_item_launches(item_id: int, db: Session = Depends(get_db)):
    return (
        db.query(LaunchHistory)
        .filter(LaunchHistory.library_item_id == item_id)
        .order_by(LaunchHistory.started_at.desc())
        .limit(20)
        .all()
    )

@router.get("/launches", response_model=list[LaunchHistoryRead])
def list_launches(db: Session = Depends(get_db)):
    return db.query(LaunchHistory).order_by(LaunchHistory.started_at.desc()).limit(50).all()


@router.get("/launches/{history_id}")
def get_launch(history_id: int, db: Session = Depends(get_db)):
    record = db.get(LaunchHistory, history_id)
    if not record:
        raise HTTPException(status_code=404, detail="Launch record not found.")
    return record

@router.post("/launches/{history_id}/stop", status_code=200)
def stop_launch(history_id: int, db: Session = Depends(get_db), active_user: User = require_permission("can_launch_media")):
    record = db.get(LaunchHistory, history_id)
    if not record:
        raise HTTPException(status_code=404, detail="Launch record not found.")

    if not active_user.is_owner and not active_user.is_admin:
        if record.profile_id is not None:
            from backend.models.profile import Profile as _Profile
            prof = db.get(_Profile, record.profile_id)
            if prof is not None and prof.user_id is not None and prof.user_id != active_user.id:
                raise HTTPException(status_code=403, detail="Permission denied: you can only stop your own launches.")

    stopped = False
    for pid, entry in process_registry.get_all().items():
        by_history = entry.launch_history_id == history_id
        by_item = record.library_item_id is not None and entry.library_item_id == record.library_item_id
        if by_history or by_item:
            process_registry.terminate(pid)
            stopped = True
            break

    if stopped:
        record.ended_at = datetime.now(timezone.utc)
        record.exit_code = -15
        db.commit()

    return {"stopped": stopped}
