import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core import process_registry
from backend.core.database import get_db
from backend.core.process_registry import ProcessEntry
from backend.models import LaunchHistory, LibraryItem, Profile
from backend.models.launch_history import LaunchHistoryRead

router = APIRouter(prefix="/api/v1", tags=["launches"])


class LaunchRequest(BaseModel):
    profile_id: int | None = None


class LaunchResponse(BaseModel):
    launch_history_id: int
    warnings: list[str] = []


@router.post("/library/{item_id}/launch", status_code=202, response_model=LaunchResponse)
async def launch_item(item_id: int, body: LaunchRequest, db: Session = Depends(get_db)):
    item = db.get(LibraryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Library item not found.")

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
        )
    except Exception as exc:
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
        )
        process_registry.register(proc.pid, entry)
        history.job_isolated = job_isolated
        db.commit()

    return LaunchResponse(launch_history_id=history.id, warnings=warnings)


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
