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
from backend.models import EnvironmentItem, LaunchHistory, Profile
from backend.service.launch.drive_hydration import hydrate_drive_for_entity
from backend.service.launch.history import write_session_ends
from backend.service.launch.launch_spec import LaunchSpec
from backend.service.launch.monitor import register_short_lived_check
from backend.service.utils.era_defaults import DOS_WIN_ERAS
from backend.service.utils.file_types import resolve_media_file_from_directory
from backend.service.utils.fat.directory import _to_83_str
from backend.service.utils.xbox_image import XboxDvdRipDetected

if TYPE_CHECKING:
    from backend.models.drive import Drive
    from backend.service.launch.launchable_resolver import LaunchableEntity

logger = get_logger(__name__)

_resolve_media_file_from_directory = resolve_media_file_from_directory


@dataclass
class LaunchResult:
    history_id: int
    warnings: list[str] = field(default_factory=list)
    launch_review_flagged: bool = False


# Synchronous post-spawn liveness check, run inline before the launch response
# is returned. Bounded short on purpose -- this adds to every launch's
# response time, success or failure, so it only catches the common
# near-instant-crash case (missing DLL, bad args, immediate fault). Slower
# crashes (up to the existing 3s short-lived window) are still caught
# asynchronously by register_short_lived_check/poll_short_lived, which only
# flags the item for the *next* launch's response, not this one.
_INLINE_CRASH_CHECK_TIMEOUT = 0.75
_INLINE_CRASH_CHECK_INTERVAL = 0.1


async def _poll_for_immediate_exit(proc, timeout: float = _INLINE_CRASH_CHECK_TIMEOUT) -> int | None:
    """Poll proc.poll() for up to *timeout* seconds.

    Returns the exit code if the process has already exited within that
    window, or None if it is still running when the window elapses.
    """
    deadline = time.monotonic() + timeout
    while True:
        exit_code = proc.poll()
        if exit_code is not None:
            return exit_code
        if time.monotonic() >= deadline:
            return None
        await asyncio.sleep(_INLINE_CRASH_CHECK_INTERVAL)


def _finalize_launch(
    history: LaunchHistory,
    result: object,
    db: Session,
    *,
    network_blocked: bool,
    collection_id: int | None = None,
    app_collection_id: int | None = None,
    profile_id: int | None = None,
    emulator_slug: str | None = None,
    user_id: int | None = None,
) -> None:
    proc = result[0] if isinstance(result, tuple) else result
    job = result[1] if isinstance(result, tuple) and len(result) > 1 else None

    if proc is not None:
        if job is None or getattr(job, "job_handle", None) is None:
            try:
                proc.kill()
            except Exception as exc:
                logger.error("Failed to kill process %s during aborted launch: %s", getattr(proc, "pid", "?"), exc)
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
            software_collection_id=collection_id,
            app_collection_id=app_collection_id,
            profile_id=profile_id,
            launch_history_id=history.id,
            emulator_slug=emulator_slug,
            user_id=user_id,
        )
        try:
            process_registry.register(proc.pid, entry)
        except Exception as exc:
            logger.error("Failed to register process pid=%s during launch: %s", getattr(proc, "pid", "?"), exc)
            try:
                proc.kill()
            except Exception as kill_exc:
                logger.error(
                    "Failed to kill process %s after registration failure: %s",
                    getattr(proc, "pid", "?"), kill_exc,
                )
            history.error_message = "Launch failed during process registration; process was terminated."
            history.ended_at = datetime.now(timezone.utc)
            history.exit_code = -1
            db.commit()
            raise HTTPException(
                status_code=500,
                detail="Launch failed during process registration; process was terminated.",
            )
        history.job_isolated = True
        history.sandboxed = True
        history.sandbox_memory_limit_mb = job.memory_limit_mb
        history.sandbox_cpu_limit_percent = job.cpu_limit_percent
        history.network_blocked = network_blocked
        db.commit()
    else:
        # A backend returned None/(None, ...) instead of raising. Without this,
        # the caller would treat a launch that never produced a process as a
        # success, leaving history.ended_at unset forever. Same false-success
        # class as the extract-xiso bug: never trust a result without
        # confirming the thing it claims to have produced actually exists.
        logger.error("Launch backend returned no process (proc is None) for history_id=%s", history.id)
        history.error_message = "Launch failed: backend returned no process."
        history.ended_at = datetime.now(timezone.utc)
        history.exit_code = -1
        db.commit()
        raise HTTPException(
            status_code=500,
            detail="Launch failed: the backend did not return a running process.",
        )


def _resolve_profile_for_item(entity_profile_id: int | None, profile_id: int | None, db: Session) -> Profile:
    profile: Profile | None = None
    if profile_id:
        profile = db.get(Profile, profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found.")
    if profile is None and entity_profile_id:
        profile = db.get(Profile, entity_profile_id)
    if profile is None:
        raise HTTPException(status_code=422, detail="No profile associated with this library item.")
    return profile


def _resolve_profile_for_environment(platform: EnvironmentItem, profile_id: int | None, db: Session) -> Profile:
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


def _build_spec_for_entity(
    entity: "LaunchableEntity",
    profile: Profile,
    platform: EnvironmentItem | None,
    drive: "Drive | None",
    effective_media_path: str,
) -> LaunchSpec:
    """Resolve all entity fields to plain values and construct a LaunchSpec."""
    from backend.constants_generated import BackendSlug
    from backend.constants import era_to_enum
    from backend.service.utils.backend_router import resolve_backend_name, get_executable_path

    era_enum = era_to_enum(entity.era)
    slug = resolve_backend_name(era_enum)

    # box86 and xemu resolve their own binary paths internally.
    executable_path: str | None = None
    if slug not in (BackendSlug.BOX86.value, BackendSlug.XEMU.value):
        path = get_executable_path(era_enum, slug)
        if not path:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"The emulator for era '{entity.era}' is not installed. "
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

    # Hydrated loose-file items run from the writable C: drive (their files were
    # copied there by drive_hydration), not the read-only D: source mount. This
    # mirrors the hydration copy condition so mount and hydration agree, but
    # omits `installed` — the files live on C: on every launch, not just the
    # first. c_run_command is the executable relative to the copied folder root.
    run_from_c = False
    c_run_command: str | None = None
    if (
        drive is not None
        and bool(profile.use_drive)
        and not entity.requires_install
        and entity.folder_path is not None
        and Path(entity.folder_path).is_dir()
    ):
        run_from_c = True
        folder = Path(entity.folder_path)
        exe_src = entity.executable_path or entity.media_path
        if exe_src:
            try:
                rel = Path(exe_src).resolve().relative_to(folder.resolve())
            except ValueError:
                rel = Path(Path(exe_src).name)
            raw_cmd = str(rel).replace("/", "\\")
            try:
                c_run_command = "\\".join(
                    _to_83_str(part) for part in raw_cmd.split("\\")
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Cannot launch: executable path has a component that cannot be represented in 8.3 format: {exc}",
                ) from exc

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
        era=entity.era,
        emulator_slug=profile.emulator_slug,
        media_path=Path(effective_media_path),
        executable_path=executable_path,
        enable_networking=bool(profile.enable_networking),
        enable_dgvoodoo2=bool(profile.enable_dgvoodoo2),
        launch_commands=list(entity.launch_commands or []),
        auto_run_media=entity.launch_commands is None,
        run_from_c=run_from_c,
        c_run_command=c_run_command,
        profile_id=profile.id,
        profile_launch_commands=list(profile.launch_commands or []),
        use_drive=bool(profile.use_drive),
        container_enabled=profile.container_enabled,
        user_id=profile.user_id,
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
        disc_paths=[Path(p) for p in entity.disc_paths],
        collection_id=entity.collection_id,
        launch_review_flagged=bool(entity.launch_review_flagged),
        source_type=entity.source_type,
    )


def _build_spec_for_environment(
    platform: EnvironmentItem,
    profile: Profile,
    resolved_install_path: str | None = None,
    resolved_rom_path: str | None = None,
) -> LaunchSpec:
    """Resolve all ORM fields to plain values and construct a LaunchSpec.

    resolved_install_path / resolved_rom_path are set only when this launch
    just ran provisioning (box86) — they let box86.launch reuse the binary
    and ROM paths provisioning already resolved instead of re-resolving them.
    """
    from backend.constants import era_to_enum
    from backend.service.utils.backend_router import resolve_backend_name

    slug = resolve_backend_name(era_to_enum(platform.era))

    config_path: Path | None = None
    vm_dir: Path | None = None
    if platform.config_path:
        config_path = Path(platform.config_path)
        vm_dir = config_path.parent.resolve()

    return LaunchSpec(
        slug=slug,
        era=platform.era,
        emulator_slug=profile.emulator_slug,
        media_path=None,
        executable_path=resolved_install_path,
        enable_networking=bool(profile.enable_networking),
        enable_dgvoodoo2=bool(profile.enable_dgvoodoo2),
        profile_id=profile.id,
        user_id=profile.user_id,
        vm_dir=vm_dir,
        config_path=config_path,
        working_image_path=Path(platform.working_image_path) if platform.working_image_path else None,
        base_image_path=Path(platform.base_image_path) if platform.base_image_path else None,
        hardware_profile=platform.hardware_profile or "standard",
        platform_name=platform.name,
        platform_slug=platform.slug,
        platform_id=platform.id,
        resolved_rom_path=Path(resolved_rom_path) if resolved_rom_path else None,
    )


async def launch(spec: LaunchSpec, db: Session) -> LaunchResult:
    """Execute a fully resolved LaunchSpec under Job Object isolation.

    ORM resolution must be complete before constructing the spec.
    Use launch_collection() or launch_environment() as convenience entry points
    that handle resolution and pre-launch gates.

    Args:
        spec: Fully resolved LaunchSpec with all plain-value fields set.
        db: Database session for history writes.

    Returns:
        LaunchResult with history_id and any warnings.
    """
    from backend.service.utils.backend_router import dispatch

    network_blocked = not spec.enable_networking
    # is_environment: a platform launch rather than a library collection.
    is_environment = spec.collection_id is None

    # Reserve both guard keys before any spawn work starts. The check and the
    # reservation happen atomically under process_registry's lock, so a
    # concurrent second request for the same profile or (emulator_slug,
    # user_id) cannot slip through the gap between "nothing's running" and
    # "this launch is now registered."
    reservation = process_registry.try_reserve(spec.profile_id, spec.emulator_slug, spec.user_id)
    if reservation is None:
        raise HTTPException(
            status_code=409,
            detail="Launch rejected: a launch for this profile or emulator is already active.",
        )
    is_app = spec.source_type == "app"
    try:
        history = LaunchHistory(
            game_item_bundle_id=spec.collection_id if not is_app else None,
            app_item_bundle_id=spec.collection_id if is_app else None,
            environment_item_id=spec.platform_id,
            profile_id=spec.profile_id,
            emulator_slug=spec.emulator_slug,
            started_at=datetime.now(timezone.utc),
            network_blocked=False,
            job_isolated=False,
        )
        db.add(history)
        db.commit()
        db.refresh(history)

        _LAUNCH_TIMEOUT = 30.0
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(dispatch, spec),
                timeout=_LAUNCH_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("Launch timed out after %.0fs for slug=%s", _LAUNCH_TIMEOUT, spec.slug)
            history.error_message = f"Launch timed out after {_LAUNCH_TIMEOUT:.0f}s."
            history.ended_at = datetime.now(timezone.utc)
            history.exit_code = -1
            db.commit()
            raise HTTPException(status_code=500, detail="Launch timed out. The emulator did not start within 30 seconds.")
        except XboxDvdRipDetected as exc:
            logger.info(
                "Launch blocked: raw Xbox DVD rip detected for collection_id=%s", spec.collection_id
            )
            history.error_message = str(exc)
            history.ended_at = datetime.now(timezone.utc)
            history.exit_code = -1
            db.commit()
            raise HTTPException(
                status_code=422,
                detail={
                    "error_type": "xbox_dvd_rip",
                    "message": str(exc),
                    "collection_id": spec.collection_id,
                    "media_path": str(spec.media_path) if spec.media_path else None,
                },
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
            collection_id=spec.collection_id if not is_app else None,
            app_collection_id=spec.collection_id if is_app else None,
            profile_id=spec.profile_id,
            emulator_slug=spec.emulator_slug,
            user_id=spec.user_id,
        )

        if proc is not None and not is_environment:
            launch_time = time.monotonic()
            exit_code = await _poll_for_immediate_exit(proc)
            if exit_code is not None and exit_code != 0:
                logger.error(
                    "Launch for collection_id=%s exited immediately (exit_code=%s) within %.2fs of spawn",
                    spec.collection_id, exit_code, _INLINE_CRASH_CHECK_TIMEOUT,
                )
                process_registry.terminate(proc.pid)
                history.error_message = (
                    f"Process exited immediately after launch (exit code {exit_code})."
                )
                history.ended_at = datetime.now(timezone.utc)
                history.exit_code = exit_code
                db.commit()
                raise HTTPException(
                    status_code=500,
                    detail=f"Launch failed: the emulator process exited immediately (exit code {exit_code}).",
                )
            # Every software collection launch gets the async 3s short-lived
            # crash-review window (keyed on collection_id) in addition to the
            # inline check above. Apps are excluded: the review-flag machinery
            # (monitor._flag_short_lived_item) writes to SoftwareCollection.
            # launch_review_flagged, a field AppCollection deliberately does
            # not have (see backend/models/app.py), and software_collection_id
            # / app_collection_id are separate id spaces that can collide on
            # the same integer -- keying off collection_id alone here would
            # risk flagging an unrelated SoftwareCollection row.
            if spec.collection_id is not None and not is_app:
                register_short_lived_check(spec.collection_id, proc, launch_time)

        return LaunchResult(
            history_id=history.id,
            warnings=[],
            launch_review_flagged=spec.launch_review_flagged,
        )
    finally:
        # Once registered, process_registry itself is the active-state source
        # of truth for these keys (try_reserve scans it too), so releasing the
        # now-redundant pending marker here -- on every exit path, success or
        # failure -- never reopens a window for a duplicate launch to slip in.
        process_registry.release(reservation)


def _resolve_environment_for_pc_entity(entity: "LaunchableEntity", db: Session) -> EnvironmentItem | None:
    """Resolve the Environment for a PC SoftwareCollection launch (doc 02 A5).

    Resolves directly via the collection's own environment_item_id FK instead of
    the old EnvironmentItem.profile_id reverse-lookup. Falls back to the
    era-matched system Environment only when environment_item_id is still null —
    a runtime fallback for the backfill transition window, not a migration.
    """
    if entity.environment_item_id is not None:
        return db.get(EnvironmentItem, entity.environment_item_id)
    from backend.service.utils.era_defaults import lookup_system_environment_by_era
    return lookup_system_environment_by_era(entity.era, db)


async def _launch_entity(entity: "LaunchableEntity", profile_id: int | None, db: Session) -> LaunchResult:
    """Internal shared entry point for collection launches.

    Expects the caller (launch_collection) to have already called
    process_registry.cleanup_exited() and write_session_ends.
    """
    profile = _resolve_profile_for_item(entity.profile_id, profile_id, db)

    # Environment is strictly PC (doc 02 A5): console entities never touch
    # Environment at all, not even to check for one.
    platform_record: EnvironmentItem | None = None
    if entity.item_type == "pc":
        platform_record = _resolve_environment_for_pc_entity(entity, db)
        if platform_record is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "error_type": "no_environment",
                    "message": (
                        "This PC item has no Environment configured. "
                        "Create an Environment for this era first."
                    ),
                    "collection_id": entity.collection_id,
                },
            )

    drive = hydrate_drive_for_entity(entity, db)

    effective_media_path = entity.executable_path if entity.executable_path else entity.media_path
    if Path(effective_media_path).is_dir() and drive is None:
        try:
            resolved = _resolve_media_file_from_directory(Path(effective_media_path), entity.era)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        effective_media_path = str(resolved)

    spec = _build_spec_for_entity(entity, profile, platform_record, drive, effective_media_path)
    return await launch(spec, db)


async def launch_collection(collection_id: int, profile_id: int | None, db: Session) -> LaunchResult:
    """Sole game entry point. Resolves the collection's launch disc and launches."""
    exited = process_registry.cleanup_exited()
    if exited:
        await asyncio.to_thread(write_session_ends, exited)

    from backend.service.launch.launchable_resolver import resolve_launchable
    try:
        entity = resolve_launchable(collection_id, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _launch_entity(entity, profile_id, db)


async def launch_app_collection(app_collection_id: int, profile_id: int | None, db: Session) -> LaunchResult:
    """App entry point. Mirrors launch_collection but resolves an AppCollection.

    Reuses _launch_entity unchanged: entity.item_type is always "pc" and
    entity.environment_item_id is always non-null for an App (see
    launchable_resolver.resolve_launchable_app), so _resolve_environment_for_pc_entity
    always takes its direct-lookup branch here -- there is no era-fallback
    path to reach, since Apps have no missing-environment state.
    """
    exited = process_registry.cleanup_exited()
    if exited:
        await asyncio.to_thread(write_session_ends, exited)

    from backend.service.launch.launchable_resolver import resolve_launchable_app
    try:
        entity = resolve_launchable_app(app_collection_id, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _launch_entity(entity, profile_id, db)


async def launch_environment(platform: EnvironmentItem, profile_id: int | None, db: Session) -> LaunchResult:
    logger.info("launch_environment entry: platform_id=%d era=%s profile_id=%s", platform.id, platform.era, profile_id)
    exited = process_registry.cleanup_exited()
    if exited:
        await asyncio.to_thread(write_session_ends, exited)

    profile = _resolve_profile_for_environment(platform, profile_id, db)

    resolved_install_path: str | None = None
    resolved_rom_path: str | None = None
    if platform.working_image_path is None and platform.era in ({"win95", "win98", "winxp"} | DOS_WIN_ERAS):
        try:
            from backend.service.utils.vm import provision_platform
            (
                _iso_path,
                working_path,
                config_path,
                resolved_install_path,
                resolved_rom_path,
            ) = await asyncio.to_thread(provision_platform, platform)
            if _iso_path and not platform.base_image_path:
                db.execute(
                    update(EnvironmentItem)
                    .where(EnvironmentItem.id == platform.id)
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

    try:
        spec = _build_spec_for_environment(
            platform, profile,
            resolved_install_path=resolved_install_path,
            resolved_rom_path=resolved_rom_path,
        )
    except Exception:
        logger.exception(
            "launch_environment failed to build LaunchSpec: platform_id=%d era=%s config_path=%r",
            platform.id, platform.era, platform.config_path,
        )
        raise
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
        by_collection = (
            record.game_item_bundle_id is not None
            and entry.software_collection_id == record.game_item_bundle_id
        )
        by_app_collection = (
            record.app_item_bundle_id is not None
            and entry.app_collection_id == record.app_item_bundle_id
        )
        if by_history or by_collection or by_app_collection:
            process_registry.terminate(pid)
            stopped = True
            break

    if stopped:
        record.ended_at = datetime.now(timezone.utc)
        record.exit_code = -15
        db.commit()

    return {"stopped": stopped}
