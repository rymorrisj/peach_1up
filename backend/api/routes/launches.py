import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from backend.core import process_registry
from backend.core.database import get_db
from backend.core.dependencies import get_active_user
from backend.core.process_registry import ProcessEntry
from backend.models import LaunchHistory, LibraryItem, Platform, Profile
from backend.models.launch_history import LaunchHistoryRead
from backend.models.user import User

router = APIRouter(prefix="/api/v1", tags=["launches"])


class LaunchRequest(BaseModel):
    profile_id: int | None = None


class LaunchResponse(BaseModel):
    launch_history_id: int
    warnings: list[str] = []


@router.post("/library/{item_id}/launch", status_code=202, response_model=LaunchResponse)
async def launch_item(
    item_id: int,
    body: LaunchRequest = LaunchRequest(),
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
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

    # Enforce one active launch per user profile
    if body.profile_id is not None:
        for _, entry in process_registry.get_all().items():
            if entry.profile_id == body.profile_id:
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

    history = LaunchHistory(
        library_item_id=item.id,
        profile_id=profile.id if profile else None,
        emulator_slug=profile.emulator_slug if profile else "",
        started_at=datetime.utcnow(),
        network_blocked=network_blocked,
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
            item.media_path,
            profile,
            platform_record,
        )
    except Exception as exc:
        logger.exception("Launch failed")
        history.error_message = str(exc)
        history.ended_at = datetime.utcnow()
        history.exit_code = -1
        db.commit()
        raise HTTPException(status_code=500, detail=f"Launch failed: {exc}")

    proc = result[0] if isinstance(result, tuple) else result
    job = result[1] if isinstance(result, tuple) and len(result) > 1 else None

    if proc is not None:
        job_isolated = job is not None and getattr(job, 'job_handle', None) is not None
        if not job_isolated:
            warnings.append(
                "Job Object isolation is unavailable on this system. "
                "The emulator launched without process-level resource limits. "
                "Network isolation still applies via the emulator adapter setting."
            )
        entry = ProcessEntry(
            process_handle=proc,
            job_handle=job,
            library_item_id=item.id,
            profile_id=profile.id if profile else None,
            launch_history_id=history.id,
        )
        process_registry.register(proc.pid, entry)
        history.job_isolated = job_isolated
        history.sandboxed = job_isolated
        history.sandbox_memory_limit_mb = job.memory_limit_mb if job_isolated else None
        history.sandbox_cpu_limit_percent = job.cpu_limit_percent if job_isolated else None
        db.commit()

    return LaunchResponse(launch_history_id=history.id, warnings=warnings)


@router.post("/environments/{platform_id}/launch", status_code=202, response_model=LaunchResponse)
async def launch_environment(
    platform_id: int,
    body: LaunchRequest = LaunchRequest(),
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
):
    platform = db.get(Platform, platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Environment not found.")

    _exited = process_registry.cleanup_exited()
    if _exited:
        from backend.core.lifespan import _write_session_ends
        await asyncio.to_thread(_write_session_ends, _exited)

    if body.profile_id is not None:
        for _, entry in process_registry.get_all().items():
            if entry.profile_id == body.profile_id:
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

    from backend.service.utils.backend_router import launch_media

    network_blocked = not bool(getattr(profile, 'enable_networking', False))

    history = LaunchHistory(
        target_type="environment",
        platform_id=platform.id,
        profile_id=profile.id,
        emulator_slug=profile.emulator_slug,
        started_at=datetime.utcnow(),
        network_blocked=network_blocked,
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
        history.ended_at = datetime.utcnow()
        history.exit_code = -1
        db.commit()
        raise HTTPException(status_code=500, detail=f"Launch failed: {exc}")

    proc = result[0] if isinstance(result, tuple) else result
    job = result[1] if isinstance(result, tuple) and len(result) > 1 else None

    if proc is not None:
        job_isolated = job is not None and getattr(job, 'job_handle', None) is not None
        if not job_isolated:
            warnings.append(
                "Job Object isolation is unavailable on this system. "
                "The emulator launched without process-level resource limits. "
                "Network isolation still applies via the emulator adapter setting."
            )
        entry = ProcessEntry(
            process_handle=proc,
            job_handle=job,
            library_item_id=None,
            profile_id=profile.id,
            launch_history_id=history.id,
        )
        process_registry.register(proc.pid, entry)
        history.job_isolated = job_isolated
        history.sandboxed = job_isolated
        history.sandbox_memory_limit_mb = job.memory_limit_mb if job_isolated else None
        history.sandbox_cpu_limit_percent = job.cpu_limit_percent if job_isolated else None
        db.commit()

    old_records = (
        db.query(LaunchHistory)
        .filter(LaunchHistory.platform_id == platform.id, LaunchHistory.target_type == "environment")
        .order_by(LaunchHistory.started_at.desc())
        .offset(10)
        .all()
    )
    for old in old_records:
        db.delete(old)
    if old_records:
        db.commit()

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
def stop_launch(history_id: int, db: Session = Depends(get_db)):
    record = db.get(LaunchHistory, history_id)
    if not record:
        raise HTTPException(status_code=404, detail="Launch record not found.")

    stopped = False
    for pid, entry in process_registry.get_all().items():
        if entry.library_item_id == record.library_item_id:
            process_registry.terminate(pid)
            stopped = True
            break

    if stopped:
        record.ended_at = datetime.utcnow()
        record.exit_code = -15
        db.commit()

    return {"stopped": stopped}
