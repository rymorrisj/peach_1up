import asyncio
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
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

_HISTORY_LIMIT = 10


class LaunchRequest(BaseModel):
    profile_id: int | None = None


class LaunchResponse(BaseModel):
    launch_history_id: int
    warnings: list[str] = []


def _trim_history(db: Session, target_type: str, target_id: int) -> None:
    """Delete records beyond the last _HISTORY_LIMIT for a given target."""
    if target_type == "library_item":
        q = db.query(LaunchHistory).filter(LaunchHistory.library_item_id == target_id)
    else:
        q = db.query(LaunchHistory).filter(LaunchHistory.environment_id == target_id)
    to_delete = q.order_by(LaunchHistory.started_at.desc()).offset(_HISTORY_LIMIT).all()
    for record in to_delete:
        db.delete(record)
    if to_delete:
        db.commit()


@router.post("/library/{item_id}/launch", status_code=202, response_model=LaunchResponse)
async def launch_item(
    item_id: int,
    body: LaunchRequest,
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
):
    item = db.get(LibraryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Library item not found.")

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

    if profile is None and item.profile_id:
        profile = db.get(Profile, item.profile_id)

    if profile is None:
        raise HTTPException(status_code=422, detail="No profile associated with this library item.")

    platform_record = db.query(Platform).filter(Platform.profile_id == profile.id).first()

    from backend.service.utils.backend_router import launch_media

    network_blocked = not bool(getattr(profile, 'enable_networking', False))

    history = LaunchHistory(
        target_type="library_item",
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
    _trim_history(db, "library_item", item.id)

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
            target_type="library_item",
            target_id=item.id,
            job_isolated=job_isolated,
        )
        process_registry.register(proc.pid, entry)
        history.job_isolated = job_isolated
        history.sandboxed = job_isolated
        history.sandbox_memory_limit_mb = job.memory_limit_mb if job_isolated else None
        history.sandbox_cpu_limit_percent = job.cpu_limit_percent if job_isolated else None
        db.commit()

    return LaunchResponse(launch_history_id=history.id, warnings=warnings)


@router.post("/environments/{env_id}/launch", status_code=202, response_model=LaunchResponse)
async def launch_environment(
    env_id: int,
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
):
    platform = db.get(Platform, env_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Environment not found.")
    if platform.is_system:
        raise HTTPException(status_code=422, detail="Cannot launch a system platform directly.")

    _exited = process_registry.cleanup_exited()
    if _exited:
        from backend.core.lifespan import _write_session_ends
        await asyncio.to_thread(_write_session_ends, _exited)

    # Resolve profile: platform-assigned first, then bundled default for era
    profile: Profile | None = None
    if platform.profile_id:
        profile = db.get(Profile, platform.profile_id)
    if profile is None:
        profile = (
            db.query(Profile)
            .filter(Profile.era == platform.era, Profile.is_bundled == True)
            .first()
        )
    if profile is None:
        raise HTTPException(
            status_code=422,
            detail=f"No profile configured for era '{platform.era}'. Assign a profile to this environment or ensure a bundled profile exists.",
        )

    for _, entry in process_registry.get_all().items():
        if entry.profile_id == profile.id:
            raise HTTPException(status_code=409, detail="A launch is already active for this profile.")

    # Determine media_path: None for platform-backends (VirtualBox/86Box, which use
    # the working_image_path already attached to the VM), or working_image_path for
    # DOSBox-X which requires an explicit media mount.
    from backend.service.utils.backend_router import resolve_backend_name
    from backend.constants_generated import Era
    try:
        era_enum = Era(platform.era)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown era '{platform.era}'.")

    accuracy_mode = bool(getattr(profile, 'is_accuracy_mode', False))
    try:
        backend_name = resolve_backend_name(era_enum, accuracy_mode)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    _platform_backends = {"virtualbox", "box86"}
    if backend_name in _platform_backends:
        media_path = None
    else:
        if not platform.working_image_path:
            raise HTTPException(
                status_code=422,
                detail="Working image path is required to launch a DOS/Win3.1 environment.",
            )
        media_path = platform.working_image_path

    network_blocked = not bool(getattr(profile, 'enable_networking', False))

    history = LaunchHistory(
        target_type="environment",
        environment_id=platform.id,
        profile_id=profile.id,
        emulator_slug=profile.emulator_slug,
        started_at=datetime.utcnow(),
        network_blocked=network_blocked,
        job_isolated=False,
    )
    db.add(history)
    db.commit()
    db.refresh(history)
    _trim_history(db, "environment", platform.id)

    warnings: list[str] = []

    try:
        from backend.service.utils.backend_router import launch_media
        result = await asyncio.to_thread(
            launch_media,
            platform.era,
            media_path,
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
            target_type="environment",
            target_id=platform.id,
            job_isolated=job_isolated,
        )
        process_registry.register(proc.pid, entry)
        history.job_isolated = job_isolated
        history.sandboxed = job_isolated
        history.sandbox_memory_limit_mb = job.memory_limit_mb if job_isolated else None
        history.sandbox_cpu_limit_percent = job.cpu_limit_percent if job_isolated else None
        db.commit()

    return LaunchResponse(launch_history_id=history.id, warnings=warnings)


@router.get("/library/{item_id}/launches", response_model=list[LaunchHistoryRead])
def list_item_launches(item_id: int, db: Session = Depends(get_db)):
    return (
        db.query(LaunchHistory)
        .filter(LaunchHistory.library_item_id == item_id)
        .order_by(LaunchHistory.started_at.desc())
        .limit(_HISTORY_LIMIT)
        .all()
    )


@router.get("/launches", response_model=list[LaunchHistoryRead])
def list_launches(
    db: Session = Depends(get_db),
    target_id: int | None = Query(default=None),
    target_type: str | None = Query(default=None),
):
    q = db.query(LaunchHistory)
    if target_id is not None and target_type is not None:
        if target_type == "library_item":
            q = q.filter(LaunchHistory.library_item_id == target_id)
        elif target_type == "environment":
            q = q.filter(LaunchHistory.environment_id == target_id)
    return q.order_by(LaunchHistory.started_at.desc()).limit(_HISTORY_LIMIT).all()


def _entry_to_data(pid: int, entry, exit_code: int | None = None, ended_at: str | None = None) -> dict:
    return {
        "launch_id": entry.launch_history_id,
        "target_id": entry.target_id,
        "target_type": entry.target_type,
        "pid": pid,
        "started_at": entry.started_at.isoformat() if entry.started_at else None,
        "ended_at": ended_at,
        "exit_code": exit_code,
        "job_isolated": entry.job_isolated,
    }


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.get("/launches/stream")
async def launches_stream(request: Request):
    # Inline auth — open/close session immediately so no DB connection is held
    # for the lifetime of the stream.
    from backend.core.database import get_engine
    from sqlalchemy.orm import sessionmaker
    _sf = sessionmaker(bind=get_engine())
    with _sf() as _db:
        owner = _db.query(User).filter(User.is_owner.is_(True)).first()
        if owner is None:
            raise HTTPException(status_code=503, detail="No owner account configured.")

    async def generate():
        # Initial snapshot of all currently active processes
        entries = process_registry.get_all()
        snapshot = [
            _entry_to_data(pid, e)
            for pid, e in entries.items()
            if e.launch_history_id is not None
        ]
        yield _sse("snapshot", snapshot)

        q = process_registry.subscribe()
        try:
            next_ping = asyncio.get_event_loop().time() + 15.0
            while True:
                timeout = max(0.1, next_ping - asyncio.get_event_loop().time())
                try:
                    event = await asyncio.wait_for(q.get(), timeout=timeout)
                    etype = event["type"]
                    pid = event["pid"]
                    entry = event["entry"]
                    exit_code = event.get("exit_code")
                    ended_at = datetime.utcnow().isoformat() if etype in ("exited", "cleaned") else None
                    data = _entry_to_data(pid, entry, exit_code=exit_code, ended_at=ended_at)
                    yield _sse(etype, data)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    next_ping = asyncio.get_event_loop().time() + 15.0
        except asyncio.CancelledError:
            pass
        finally:
            process_registry.unsubscribe(q)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


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
    # Match by launch_history_id first (precise, works for both library and environment)
    for pid, entry in process_registry.get_all().items():
        if entry.launch_history_id == history_id:
            process_registry.terminate(pid)
            stopped = True
            break
    # Fallback: match by library_item_id for legacy registry entries without history_id
    if not stopped and record.library_item_id is not None:
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
