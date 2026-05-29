from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.core import process_registry
from backend.core.logger import get_logger
from backend.core.process_registry import ProcessEntry
from backend.models import LaunchHistory, LibraryItem, Platform, Profile
from backend.service.launch.drive_hydration import hydrate_drive_for_item
from backend.service.launch.history import write_session_ends
from backend.service.launch.monitor import register_short_lived_check
from backend.service.utils.backend_router import launch_media, resolve_backend_name

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


@dataclass
class LaunchResult:
    history_id: int
    warnings: list[str] = field(default_factory=list)
    launch_review_flagged: bool = False


def _finalize_launch(
    history: LaunchHistory,
    result: object,
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


def _resolve_profile_for_item(item: LibraryItem, profile_id: int | None, db: Session) -> Profile:
    profile: Profile | None = None
    if profile_id:
        profile = db.get(Profile, profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found.")
    if profile is None and item.profile_id:
        profile = db.get(Profile, item.profile_id)
    if profile is None:
        raise HTTPException(status_code=422, detail="No profile associated with this library item.")
    return profile


def _resolve_profile_for_environment(platform: Platform, profile_id: int | None, db: Session) -> Profile:
    profile: Profile | None = None
    if profile_id:
        profile = db.get(Profile, profile_id)
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
    return profile


def _gate_single_active_launch(gate_profile_id: int | None) -> None:
    if gate_profile_id is None:
        return
    for _, entry in process_registry.get_all().items():
        if entry.profile_id == gate_profile_id:
            raise HTTPException(status_code=409, detail="A launch is already active for this profile.")


async def launch_item(item: LibraryItem, profile_id: int | None, db: Session) -> LaunchResult:
    from backend.constants_generated import BackendSlug, Era

    exited = process_registry.cleanup_exited()
    if exited:
        await asyncio.to_thread(write_session_ends, exited)

    _gate_single_active_launch(profile_id if profile_id is not None else item.profile_id)

    profile = _resolve_profile_for_item(item, profile_id, db)
    platform_record = db.query(Platform).filter(Platform.profile_id == profile.id).first()
    network_blocked = not bool(getattr(profile, "enable_networking", False))

    drive = hydrate_drive_for_item(item, db)

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
        profile_id=profile.id,
        emulator_slug=profile.emulator_slug,
        started_at=datetime.now(timezone.utc),
        network_blocked=False,
        job_isolated=False,
    )
    db.add(history)
    db.commit()
    db.refresh(history)

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
    _finalize_launch(history, result, db, network_blocked=network_blocked, item_id=item.id, profile_id=profile.id)

    if proc is not None:
        try:
            backend_name = resolve_backend_name(Era(item.era))
        except Exception:
            backend_name = ""
        if backend_name == BackendSlug.DOSBOX.value:
            register_short_lived_check(item.id, proc, time.monotonic())

    return LaunchResult(
        history_id=history.id,
        warnings=[],
        launch_review_flagged=item.launch_review_flagged,
    )


async def launch_environment(platform: Platform, profile_id: int | None, db: Session) -> LaunchResult:
    exited = process_registry.cleanup_exited()
    if exited:
        await asyncio.to_thread(write_session_ends, exited)

    _gate_single_active_launch(profile_id if profile_id is not None else platform.profile_id)

    profile = _resolve_profile_for_environment(platform, profile_id, db)
    network_blocked = not bool(getattr(profile, "enable_networking", False))

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
            logger.exception("On-launch provisioning failed for platform %d", platform.id)
            raise HTTPException(
                status_code=422,
                detail=f"Environment has no working image and automatic provisioning failed: {exc}",
            )

    if platform.working_image_path is None:
        raise HTTPException(
            status_code=422,
            detail="Environment has no working image. Provisioning is not available for this era.",
        )

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

    return LaunchResult(history_id=history.id, warnings=[])


def stop_launch(history_id: int, active_user, db: Session) -> dict:
    record = db.get(LaunchHistory, history_id)
    if not record:
        raise HTTPException(status_code=404, detail="Launch record not found.")

    if not active_user.is_owner and not active_user.is_admin:
        if record.profile_id is not None:
            from backend.models.profile import Profile as _Profile
            prof = db.get(_Profile, record.profile_id)
            if prof is not None and prof.user_id is not None and prof.user_id != active_user.id:
                raise HTTPException(
                    status_code=403,
                    detail="Permission denied: you can only stop your own launches.",
                )

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
