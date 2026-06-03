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
from backend.service.launch.launch_spec import LaunchSpec
from backend.service.launch.monitor import register_short_lived_check
from backend.service.utils.era_media import resolve_media_file_from_directory

if TYPE_CHECKING:
    from backend.models.drive import Drive

logger = get_logger(__name__)

_resolve_media_file_from_directory = resolve_media_file_from_directory


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


def _build_spec_for_item(
    item: LibraryItem,
    profile: Profile,
    platform: Platform | None,
    drive: Drive | None,
    effective_media_path: str,
) -> LaunchSpec:
    """Resolve all ORM fields to plain values and construct a LaunchSpec."""
    from backend.constants_generated import BackendSlug, Era
    from backend.service.utils.backend_router import resolve_backend_name, get_executable_path

    era_enum = Era(item.era)
    slug = resolve_backend_name(era_enum)

    # box86 and xemu resolve their own binary paths internally.
    executable_path: str | None = None
    if slug not in (BackendSlug.BOX86.value, BackendSlug.XEMU.value):
        path = get_executable_path(era_enum)
        if not path:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"The emulator for era '{item.era}' is not installed. "
                    "Install it via the Emulators page."
                ),
            )
        executable_path = path

    drive_id: int | None = None
    drive_image_path: Path | None = None
    drive_size_mb: int | None = None
    if drive is not None:
        drive_id = drive.id
        if drive.image_path:
            drive_image_path = Path(drive.image_path)
        drive_size_mb = drive.size_mb

    vm_dir: Path | None = None
    config_path: Path | None = None
    working_image_path: Path | None = None
    base_image_path: Path | None = None
    hardware_profile = "standard"
    platform_name: str | None = None
    platform_slug_val: str | None = None

    if platform is not None:
        if platform.config_path:
            config_path = Path(platform.config_path)
            vm_dir = config_path.parent.resolve()
        if platform.working_image_path:
            working_image_path = Path(platform.working_image_path)
        if platform.base_image_path:
            base_image_path = Path(platform.base_image_path)
        hardware_profile = platform.hardware_profile or "standard"
        platform_name = platform.name
        platform_slug_val = platform.slug

    return LaunchSpec(
        slug=slug,
        era=item.era,
        emulator_slug=profile.emulator_slug,
        media_path=Path(effective_media_path),
        executable_path=executable_path,
        enable_networking=bool(profile.enable_networking),
        enable_dgvoodoo2=bool(profile.enable_dgvoodoo2),
        launch_commands=list(item.launch_commands or []),
        profile_id=profile.id,
        profile_launch_commands=list(profile.launch_commands or []),
        use_drive=bool(profile.use_drive),
        container_enabled=profile.container_enabled,
        drive_id=drive_id,
        drive_image_path=drive_image_path,
        drive_size_mb=drive_size_mb,
        vm_dir=vm_dir,
        config_path=config_path,
        working_image_path=working_image_path,
        base_image_path=base_image_path,
        hardware_profile=hardware_profile,
        platform_name=platform_name,
        platform_slug=platform_slug_val,
        item_id=item.id,
        launch_review_flagged=bool(item.launch_review_flagged),
    )


def _build_spec_for_environment(
    platform: Platform,
    profile: Profile,
) -> LaunchSpec:
    """Resolve all ORM fields to plain values and construct a LaunchSpec."""
    from backend.constants_generated import Era
    from backend.service.utils.backend_router import resolve_backend_name

    slug = resolve_backend_name(Era(platform.era))

    config_path = Path(platform.config_path)
    vm_dir = config_path.parent.resolve()

    return LaunchSpec(
        slug=slug,
        era=platform.era,
        emulator_slug=profile.emulator_slug,
        media_path=None,
        executable_path=None,
        enable_networking=bool(profile.enable_networking),
        enable_dgvoodoo2=bool(profile.enable_dgvoodoo2),
        profile_id=profile.id,
        vm_dir=vm_dir,
        config_path=config_path,
        working_image_path=Path(platform.working_image_path) if platform.working_image_path else None,
        base_image_path=Path(platform.base_image_path) if platform.base_image_path else None,
        hardware_profile=platform.hardware_profile or "standard",
        platform_name=platform.name,
        platform_slug=platform.slug,
        platform_id=platform.id,
    )


async def launch(spec: LaunchSpec, db: Session) -> LaunchResult:
    """Execute a fully resolved LaunchSpec under Job Object isolation.

    ORM resolution must be complete before constructing the spec.
    Use launch_item() or launch_environment() as convenience entry points
    that handle resolution and pre-launch gates.

    Args:
        spec: Fully resolved LaunchSpec with all plain-value fields set.
        db: Database session for history writes.

    Returns:
        LaunchResult with history_id and any warnings.
    """
    from backend.constants_generated import BackendSlug
    from backend.service.utils.backend_router import dispatch

    network_blocked = not spec.enable_networking
    # item_id is set for item launches; environment launches have platform_id only.
    is_environment = spec.item_id is None

    history = LaunchHistory(
        target_type="environment" if is_environment else "library_item",
        library_item_id=spec.item_id,
        platform_id=spec.platform_id,
        profile_id=spec.profile_id,
        emulator_slug=spec.emulator_slug,
        started_at=datetime.now(timezone.utc),
        network_blocked=False,
        job_isolated=False,
    )
    db.add(history)
    db.commit()
    db.refresh(history)

    try:
        result = await asyncio.to_thread(dispatch, spec)
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
        item_id=spec.item_id,
        profile_id=spec.profile_id,
    )

    if proc is not None and spec.slug == BackendSlug.DOSBOX.value:
        register_short_lived_check(spec.item_id, proc, time.monotonic())

    return LaunchResult(
        history_id=history.id,
        warnings=[],
        launch_review_flagged=spec.launch_review_flagged,
    )


async def launch_item(item: LibraryItem, profile_id: int | None, db: Session) -> LaunchResult:
    exited = process_registry.cleanup_exited()
    if exited:
        await asyncio.to_thread(write_session_ends, exited)

    _gate_single_active_launch(profile_id if profile_id is not None else item.profile_id)

    profile = _resolve_profile_for_item(item, profile_id, db)
    platform_record = db.query(Platform).filter(Platform.profile_id == profile.id).first()

    drive = hydrate_drive_for_item(item, db)

    effective_media_path = item.executable_path if item.executable_path else item.media_path
    if Path(effective_media_path).is_dir() and drive is None:
        try:
            resolved = _resolve_media_file_from_directory(Path(effective_media_path), item.era)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        effective_media_path = str(resolved)

    spec = _build_spec_for_item(item, profile, platform_record, drive, effective_media_path)
    return await launch(spec, db)


async def launch_environment(platform: Platform, profile_id: int | None, db: Session) -> LaunchResult:
    exited = process_registry.cleanup_exited()
    if exited:
        await asyncio.to_thread(write_session_ends, exited)

    _gate_single_active_launch(profile_id if profile_id is not None else platform.profile_id)

    profile = _resolve_profile_for_environment(platform, profile_id, db)

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

    spec = _build_spec_for_environment(platform, profile)
    return await launch(spec, db)


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
