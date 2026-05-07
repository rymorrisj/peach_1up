import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core import process_registry
from backend.core.database import get_db
from backend.core.process_registry import ProcessEntry
from backend.models import LaunchHistory, LibraryItem, Profile
from backend.schemas.launch_history import LaunchHistoryRead

router = APIRouter(prefix="/api/v1", tags=["launches"])


class LaunchRequest(BaseModel):
    profile_id: int | None = None


@router.post("/library/{item_id}/launch", status_code=202)
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
    from backend.service.utils.settings import get_binary_path

    history = LaunchHistory(
        library_item_id=item.id,
        profile_id=profile.id if profile else None,
        emulator_slug=profile.emulator_slug if profile else "",
        started_at=datetime.utcnow(),
        network_blocked=True,
        job_isolated=False,
    )
    db.add(history)
    db.commit()
    db.refresh(history)

    try:
        proc = await asyncio.to_thread(
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

    if proc is not None:
        entry = ProcessEntry(
            process_handle=proc,
            job_handle=None,
            library_item_id=item.id,
            profile_id=profile.id if profile else None,
        )
        process_registry.register(proc.pid, entry)
        history.job_isolated = True
        db.commit()

    return {"launch_history_id": history.id}


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
