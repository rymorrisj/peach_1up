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
from backend.models import EnvironmentItem, LaunchHistory, ProfileItem
from backend.service.launch.drive_hydration import hydrate_drive_for_entity
from backend.service.launch.history import write_session_ends
from backend.service.launch.launch_spec import LaunchSpec
from backend.service.launch.monitor import register_short_lived_check
from backend.service.utils.platform_defaults import PROVISIONABLE_PLATFORMS, evaluate_launch_readiness
from backend.service.utils.file_types import resolve_media_file_from_directory
from backend.service.utils.fat.directory import _to_83_str
from backend.service.utils.detection.xbox_image import XboxDvdRipDetected

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
# is returned. Bounded short on purpose, this adds to every launch's
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
    profile_item_id: int | None = None,
    emulator_slug: str | None = None,
    user_item_id: int | None = None,
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
            profile_item_id=profile_item_id,
            launch_history_id=history.id,
            emulator_slug=emulator_slug,
            user_item_id=user_item_id,
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
                    getattr(proc, "pid", "?"),
                    kill_exc,
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


def _resolve_profile_for_item(entity_profile_id: int | None, profile_item_id: int | None, db: Session) -> ProfileItem:
    profile: ProfileItem | None = None
    if profile_item_id:
        profile = db.get(ProfileItem, profile_item_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found.")
    if profile is None and entity_profile_id:
        profile = db.get(ProfileItem, entity_profile_id)
    if profile is None:
        raise HTTPException(status_code=422, detail="No profile associated with this library item.")
    return profile


def _resolve_profile_for_environment(
    environment: EnvironmentItem, profile_item_id: int | None, db: Session
) -> ProfileItem:
    profile: ProfileItem | None = None
    if profile_item_id:
        profile = db.get(ProfileItem, profile_item_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found.")
    if profile is None and environment.profile_item_id:
        profile = db.get(ProfileItem, environment.profile_item_id)
    if profile is None:
        profile = (
            db.query(ProfileItem)
            .filter(
                ProfileItem.platform == environment.platform,
                ProfileItem.is_bundled.is_(True),
            )
            .first()
        )
    if profile is None:
        raise HTTPException(status_code=422, detail="No profile found for this environment's platform.")
    return profile


def _backend_slug_for_platform(platform: str) -> str:
    """Resolve the backend slug for *platform*, turning an unresolvable platform into a
    422 instead of letting the ValueError from platform_to_enum / resolve_backend_name
    (a platform with no platforms.yaml backend, such as "unknown") surface as a 500."""
    from backend.constants import platform_to_enum
    from backend.service.utils.backend_router import resolve_backend_name

    try:
        return resolve_backend_name(platform_to_enum(platform))
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"No emulator is configured for platform '{platform}'. Set the item's platform on its detail page.",
        ) from exc


def _require_known_platform(entity: "LaunchableEntity") -> None:
    """Refuse to launch a game whose platform is still "unknown". Apps keep
    platform="unknown" legitimately (the upload finalizer never detects one), so
    they are not gated here."""
    if entity.source_type != "app" and entity.platform == "unknown":
        raise HTTPException(
            status_code=422,
            detail=(
                "Platform not set: this item's platform is unknown, so Peach 1UP cannot "
                "choose an emulator. Set its platform on the detail page, then launch again."
            ),
        )


def _build_spec_for_entity(
    entity: "LaunchableEntity",
    profile: ProfileItem,
    environment: EnvironmentItem | None,
    drive: "Drive | None",
    effective_media_path: str,
    resolved_install_path: str | None = None,
    resolved_rom_path: str | None = None,
) -> LaunchSpec:
    """Resolve all entity fields to plain values and construct a LaunchSpec.

    resolved_install_path / resolved_rom_path mirror _build_spec_for_environment's
    params of the same name: set only when this launch just ran auto-provisioning
    (via _ensure_environment_provisioned), so box86.launch can reuse the binary
    and ROM paths already resolved instead of re-resolving them from scratch.
    """
    from backend.constants_generated import BackendSlug
    from backend.constants import platform_to_enum
    from backend.service.utils.backend_router import get_executable_path

    slug = _backend_slug_for_platform(entity.platform)
    platform_enum = platform_to_enum(entity.platform)

    # box86 and xemu resolve their own binary paths internally.
    executable_path: str | None = None
    if slug not in (BackendSlug.BOX86.value, BackendSlug.XEMU.value):
        path = get_executable_path(platform_enum, slug)
        if not path:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"The emulator for platform '{entity.platform}' is not installed. "
                    "Install it via the Emulators page."
                ),
            )
        executable_path = path
    elif resolved_install_path:
        executable_path = resolved_install_path

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
    # omits `installed`, the files live on C: on every launch, not just the
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
                c_run_command = "\\".join(_to_83_str(part) for part in raw_cmd.split("\\"))
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
    environment_name: str | None = None
    environment_slug_val: str | None = None

    if environment is not None:
        if environment.config_path:
            config_path = Path(environment.config_path)
            vm_dir = config_path.parent.resolve()
        if environment.working_image_path:
            working_image_path = Path(environment.working_image_path)
        if environment.base_image_path:
            base_image_path = Path(environment.base_image_path)
        hardware_profile = environment.hardware_profile or "standard"
        environment_name = environment.name
        environment_slug_val = environment.slug

    return LaunchSpec(
        slug=slug,
        platform=entity.platform,
        emulator_slug=profile.emulator_slug,
        media_path=Path(effective_media_path),
        executable_path=executable_path,
        enable_networking=bool(profile.enable_networking),
        enable_dgvoodoo2=bool(profile.enable_dgvoodoo2),
        launch_commands=list(entity.launch_commands or []),
        auto_run_media=entity.launch_commands is None,
        run_from_c=run_from_c,
        c_run_command=c_run_command,
        profile_item_id=profile.id,
        profile_launch_commands=list(profile.launch_commands or []),
        use_drive=bool(profile.use_drive),
        container_enabled=profile.container_enabled,
        user_item_id=profile.user_item_id,
        drive_id=drive_id,
        drive_image_path=drive_image_path,
        drive_size_mb=drive_size_mb,
        vm_dir=vm_dir,
        config_path=config_path,
        working_image_path=working_image_path,
        base_image_path=base_image_path,
        hardware_profile=hardware_profile,
        environment_name=environment_name,
        environment_slug=environment_slug_val,
        disc_paths=[Path(p) for p in entity.disc_paths],
        collection_id=entity.collection_id,
        launch_review_flagged=bool(entity.launch_review_flagged),
        source_type=entity.source_type,
        resolved_rom_path=Path(resolved_rom_path) if resolved_rom_path else None,
    )


def _build_spec_for_environment(
    environment: EnvironmentItem,
    profile: ProfileItem,
    resolved_install_path: str | None = None,
    resolved_rom_path: str | None = None,
) -> LaunchSpec:
    """Resolve all ORM fields to plain values and construct a LaunchSpec.

    resolved_install_path / resolved_rom_path are set only when this launch
    just ran provisioning (box86), they let box86.launch reuse the binary
    and ROM paths provisioning already resolved instead of re-resolving them.
    """
    slug = _backend_slug_for_platform(environment.platform)

    config_path: Path | None = None
    vm_dir: Path | None = None
    if environment.config_path:
        config_path = Path(environment.config_path)
        vm_dir = config_path.parent.resolve()

    return LaunchSpec(
        slug=slug,
        platform=environment.platform,
        emulator_slug=profile.emulator_slug,
        media_path=None,
        executable_path=resolved_install_path,
        enable_networking=bool(profile.enable_networking),
        enable_dgvoodoo2=bool(profile.enable_dgvoodoo2),
        profile_item_id=profile.id,
        user_item_id=profile.user_item_id,
        vm_dir=vm_dir,
        config_path=config_path,
        working_image_path=Path(environment.working_image_path) if environment.working_image_path else None,
        base_image_path=Path(environment.base_image_path) if environment.base_image_path else None,
        hardware_profile=environment.hardware_profile or "standard",
        environment_name=environment.name,
        environment_slug=environment.slug,
        environment_id=environment.id,
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
    # is_environment: an environment launch rather than a library collection.
    is_environment = spec.collection_id is None

    # Reserve both guard keys before any spawn work starts. The check and the
    # reservation happen atomically under process_registry's lock, so a
    # concurrent second request for the same profile or (emulator_slug,
    # user_item_id) cannot slip through the gap between "nothing's running" and
    # "this launch is now registered."
    reservation = process_registry.try_reserve(spec.profile_item_id, spec.emulator_slug, spec.user_item_id)
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
            environment_item_id=spec.environment_id,
            profile_item_id=spec.profile_item_id,
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
            raise HTTPException(
                status_code=500, detail="Launch timed out. The emulator did not start within 30 seconds."
            )
        except XboxDvdRipDetected as exc:
            logger.info("Launch blocked: raw Xbox DVD rip detected for collection_id=%s", spec.collection_id)
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
            history,
            result,
            db,
            network_blocked=network_blocked,
            collection_id=spec.collection_id if not is_app else None,
            app_collection_id=spec.collection_id if is_app else None,
            profile_item_id=spec.profile_item_id,
            emulator_slug=spec.emulator_slug,
            user_item_id=spec.user_item_id,
        )

        if proc is not None and not is_environment:
            launch_time = time.monotonic()
            exit_code = await _poll_for_immediate_exit(proc)
            if exit_code is not None and exit_code != 0:
                logger.error(
                    "Launch for collection_id=%s exited immediately (exit_code=%s) within %.2fs of spawn",
                    spec.collection_id,
                    exit_code,
                    _INLINE_CRASH_CHECK_TIMEOUT,
                )
                process_registry.terminate(proc.pid)
                history.error_message = f"Process exited immediately after launch (exit code {exit_code})."
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
            # the same integer, keying off collection_id alone here would
            # risk flagging an unrelated SoftwareCollection row.
            if spec.collection_id is not None and not is_app:
                register_short_lived_check(spec.collection_id, proc, launch_time, spec.platform)

        return LaunchResult(
            history_id=history.id,
            warnings=[],
            launch_review_flagged=spec.launch_review_flagged,
        )
    finally:
        # Once registered, process_registry itself is the active-state source
        # of truth for these keys (try_reserve scans it too), so releasing the
        # now-redundant pending marker here, on every exit path, success or
        # failure, never reopens a window for a duplicate launch to slip in.
        process_registry.release(reservation)


def _verify_media_path_containment(path_str: str, source_type: str) -> None:
    """Re-verify *path_str* stays within its domain's allowed roots immediately
    before it reaches a backend's launch().

    Ingest-time containment checks (games/items.py's directory branch,
    apps/items.py's create_app_item_bundle) are not the only way
    executable_path/media_path can end up set on a leaf row, they can also be
    overwritten later via PATCH /game-item/{id} or /app-item/{id}. Those routes
    now reject an out-of-bounds executable_path themselves, but this is a
    second, independent gate, not a replacement for it, so a bad value
    reaching the column by any other means still cannot result in a launch
    outside the permitted directories. Raises rather than swallowing, a launch
    that would escape containment must fail loudly, not silently narrow to
    some other path.
    """
    resolved = Path(path_str).resolve()
    if source_type == "app":
        from backend.service.utils.path_utils import allowed_browse_roots, is_within_roots

        if not is_within_roots(resolved, allowed_browse_roots()):
            raise HTTPException(
                status_code=422,
                detail=f"Launch target '{resolved}' is outside the permitted directories.",
            )
        return
    from backend.core.settings import get_settings

    games_root_str = get_settings().get("SOFTWARE_PATH", "") or ""
    if not games_root_str:
        return
    from backend.service.utils.path_utils import library_domain_root

    media_root = library_domain_root("games")
    if not (resolved == media_root or resolved.is_relative_to(media_root)):
        raise HTTPException(
            status_code=422,
            detail=f"Launch target '{resolved}' is outside the games library (library/software/games/).",
        )


def _resolve_environment_for_pc_entity(entity: "LaunchableEntity", db: Session) -> EnvironmentItem | None:
    """The Environment the user chose for a PC item (environment_item_id), or None.

    There is no fallback and no platform compatibility rule: the user creates
    and chooses the Environment, and evaluate_launch_readiness reports a
    missing one as no_environment.
    """
    if entity.environment_item_id is None:
        return None
    return db.get(EnvironmentItem, entity.environment_item_id)


async def _launch_entity(entity: "LaunchableEntity", profile_item_id: int | None, db: Session) -> LaunchResult:
    """Internal shared entry point for collection launches.

    Expects the caller (launch_collection) to have already called
    process_registry.cleanup_exited() and write_session_ends.
    """
    _require_known_platform(entity)
    profile = _resolve_profile_for_item(entity.profile_item_id, profile_item_id, db)

    # Environment is strictly PC (doc 02 A5): console entities never touch
    # Environment at all, not even to check for one.
    environment_record: EnvironmentItem | None = None
    resolved_install_path: str | None = None
    resolved_rom_path: str | None = None
    if entity.item_type == "pc":
        environment_record = _resolve_environment_for_pc_entity(entity, db)

        # Single source of truth for the PC pre-launch gates (evaluate_launch_readiness,
        # backend/service/utils/platform_defaults.py), shared with the read-time
        # launch_blocked_reason signal in models/game.py / models/app.py.
        blocked = evaluate_launch_readiness(
            call_site="item",
            environment=environment_record,
            is_pc=True,
            profile_item_id=profile.id,
        )
        if blocked == "no_environment":
            raise HTTPException(
                status_code=422,
                detail={
                    "error_type": "no_environment",
                    "message": (
                        "This PC item has no Environment chosen. Create one on the "
                        "Environments page, then choose it in the item's Environment field."
                    ),
                    "collection_id": entity.collection_id,
                },
            )
        if blocked == "environment_not_provisioned":
            raise HTTPException(
                status_code=422,
                detail="Environment has no working image. Provisioning is not available for this platform.",
            )
        if blocked == "environment_not_installed":
            raise HTTPException(
                status_code=422,
                detail={
                    "error_type": "environment_not_installed",
                    "message": (
                        "This item's Environment has not had its OS installed yet. "
                        "Launch the Environment directly and complete the installer first."
                    ),
                    "collection_id": entity.collection_id,
                },
            )

        resolved_install_path, resolved_rom_path = await _ensure_environment_provisioned(environment_record, db)

    drive = hydrate_drive_for_entity(entity, db)

    effective_media_path = entity.executable_path if entity.executable_path else entity.media_path
    if Path(effective_media_path).is_dir() and drive is None:
        try:
            effective_media_path = str(_resolve_media_file_from_directory(Path(effective_media_path), entity.platform))
        except ValueError as exc:
            if entity.platform != "ps3":
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            # ps3's supported_media is .iso/.pkg only (config/platforms.yaml), so this
            # resolver always raises for an extracted disc folder: there is no
            # single top-level file to resolve to, the folder itself is the
            # correct launch target (matches rpcs3.launch()'s own is_dir()
            # handling and the equivalent catch in games/items.py's ingest
            # path). Leave effective_media_path pointing at the folder rather
            # than surfacing this as a 422.

    _verify_media_path_containment(effective_media_path, entity.source_type)

    spec = _build_spec_for_entity(
        entity,
        profile,
        environment_record,
        drive,
        effective_media_path,
        resolved_install_path=resolved_install_path,
        resolved_rom_path=resolved_rom_path,
    )
    return await launch(spec, db)


async def launch_collection(collection_id: int, profile_item_id: int | None, db: Session) -> LaunchResult:
    """Sole game entry point. Resolves the collection's launch disc and launches."""
    exited = process_registry.cleanup_exited()
    if exited:
        await asyncio.to_thread(write_session_ends, exited)

    from backend.service.launch.launchable_resolver import resolve_launchable

    try:
        entity = resolve_launchable(collection_id, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _launch_entity(entity, profile_item_id, db)


async def launch_app_collection(app_collection_id: int, profile_item_id: int | None, db: Session) -> LaunchResult:
    """App entry point. Mirrors launch_collection but resolves an AppCollection.

    Reuses _launch_entity unchanged: entity.item_type is now platform-derived
    (pc/console, see AppItemBundle.is_pc and resolve_launchable_app) exactly
    like GameItemBundle, so console apps skip Environment resolution entirely
    and PC apps go through the same _resolve_environment_for_pc_entity /
    missing-environment 422 gate that PC Games already use.
    """
    exited = process_registry.cleanup_exited()
    if exited:
        await asyncio.to_thread(write_session_ends, exited)

    from backend.service.launch.launchable_resolver import resolve_launchable_app

    try:
        entity = resolve_launchable_app(app_collection_id, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _launch_entity(entity, profile_item_id, db)


async def _ensure_environment_provisioned(environment: EnvironmentItem, db: Session) -> tuple[str | None, str | None]:
    """Auto-provision environment's working image if missing, then guarantee one exists.

    Extracted from launch_environment's former inline block so launch_collection
    / launch_app_collection (via _launch_entity) get the identical provisioning
    attempt and the identical clean 422s on failure, not the generic 500 that
    resulted previously from a PC game/app pointed at an unprovisioned Environment
    bypassing this logic entirely. Mutates environment in place (working_image_path,
    config_path, base_image_path) exactly as the inline block did.

    Returns (resolved_install_path, resolved_rom_path), set only when
    provisioning just ran (box86), for the caller to thread into LaunchSpec so
    box86.launch reuses the binary/ROM paths already resolved here instead of
    re-resolving them from scratch (see _build_spec_for_environment /
    _build_spec_for_entity).
    """
    resolved_install_path: str | None = None
    resolved_rom_path: str | None = None
    if environment.working_image_path is None and environment.platform in PROVISIONABLE_PLATFORMS:
        try:
            from backend.service.utils.vm import provision_environment

            (
                _iso_path,
                working_path,
                config_path,
                resolved_install_path,
                resolved_rom_path,
            ) = await asyncio.to_thread(provision_environment, environment)
            if _iso_path and not environment.base_image_path:
                db.execute(
                    update(EnvironmentItem)
                    .where(EnvironmentItem.id == environment.id)
                    .values(base_image_path=str(_iso_path))
                )
                db.flush()
            if working_path:
                environment.working_image_path = working_path
            if config_path:
                environment.config_path = config_path
            db.commit()
            db.refresh(environment)
        except Exception as exc:
            logger.exception("On-launch provisioning failed for environment %d", environment.id)
            raise HTTPException(
                status_code=422,
                detail=f"Environment has no working image and automatic provisioning failed: {exc}",
            )

    if environment.working_image_path is None:
        raise HTTPException(
            status_code=422,
            detail="Environment has no working image. Provisioning is not available for this platform.",
        )

    return resolved_install_path, resolved_rom_path


async def launch_environment(environment: EnvironmentItem, profile_item_id: int | None, db: Session) -> LaunchResult:
    logger.info(
        "launch_environment entry: environment_id=%d platform=%s profile_item_id=%s",
        environment.id,
        environment.platform,
        profile_item_id,
    )
    exited = process_registry.cleanup_exited()
    if exited:
        await asyncio.to_thread(write_session_ends, exited)

    profile = _resolve_profile_for_environment(environment, profile_item_id, db)

    # call_site="environment": this is a direct Environment launch, how a user
    # boots in to run the OS installer in the first place, so
    # evaluate_launch_readiness structurally never checks environment_not_installed
    # on this call site. Only environment_not_provisioned applies (no working
    # image and this platform can never get one auto-provisioned). Do not widen this
    # to the item-launch gate set here.
    blocked = evaluate_launch_readiness(call_site="environment", environment=environment)
    if blocked == "environment_not_provisioned":
        raise HTTPException(
            status_code=422,
            detail="Environment has no working image. Provisioning is not available for this platform.",
        )

    resolved_install_path, resolved_rom_path = await _ensure_environment_provisioned(environment, db)

    try:
        spec = _build_spec_for_environment(
            environment,
            profile,
            resolved_install_path=resolved_install_path,
            resolved_rom_path=resolved_rom_path,
        )
    except Exception:
        logger.exception(
            "launch_environment failed to build LaunchSpec: environment_id=%d platform=%s config_path=%r",
            environment.id,
            environment.platform,
            environment.config_path,
        )
        raise
    return await launch(spec, db)


def stop_launch(history_id: int, active_user, db: Session) -> dict:
    record = db.get(LaunchHistory, history_id)
    if not record:
        raise HTTPException(status_code=404, detail="Launch record not found.")

    if not active_user.is_owner and not active_user.is_admin:
        if record.profile_item_id is not None:
            from backend.models.profile import ProfileItem as _ProfileItem

            prof = db.get(_ProfileItem, record.profile_item_id)
            if prof is not None and prof.user_item_id is not None and prof.user_item_id != active_user.id:
                raise HTTPException(
                    status_code=403,
                    detail="Permission denied: you can only stop your own launches.",
                )

    stopped = False
    for pid, entry in process_registry.get_all().items():
        by_history = entry.launch_history_id == history_id
        by_collection = (
            record.game_item_bundle_id is not None and entry.software_collection_id == record.game_item_bundle_id
        )
        by_app_collection = (
            record.app_item_bundle_id is not None and entry.app_collection_id == record.app_item_bundle_id
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
