import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.core import process_registry
from backend.core.database import create_tables, init_db
from backend.core.logger import get_logger
from backend.core.process_monitor import _process_monitor_loop
from backend.core.settings import get_base_path, init_settings
from backend.core.startup_migrations import _apply_schema_migrations
from backend.core.startup_seed import (
    _seed_default_profiles,
    _seed_dosbox_environments,
    _seed_system_platforms,
)
from backend.core.startup_tasks import (
    _cleanup_stale_sessions,
    _ensure_default_paths,
    _ensure_owner_user,
    _flag_corrupt_platform_working_paths,
    _heal_interrupted_rom_pack_clones,
    _scan_installed_emulators,
    _sync_detected_emulator_paths,
    _sync_first_run_from_db,
)
from backend.service.launch.history import write_session_ends as _write_session_ends
import backend.models.user  # noqa: F401 — registers User with SQLModel.metadata
import backend.models.media_restriction  # noqa: F401 — registers MediaRestriction with SQLModel.metadata
import backend.models.tag  # noqa: F401 — registers Tag and EntityTag with SQLModel.metadata

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_settings()
    from backend.core.logger import setup_logging
    setup_logging()
    _ensure_default_paths()
    from backend.service.utils.settings import validate_configured_paths, get_path_warnings
    validate_configured_paths()
    app.state.path_warnings = get_path_warnings()
    # reset_db is a dev-only destructive flag in settings.yaml. Never true in production.
    # Cleared immediately after use so it cannot accidentally persist across restarts.
    from backend.service.utils import settings as _settings
    if _settings.get("reset_db", False):
        db_path = get_base_path() / "database" / "data" / "peach1up.db"
        if db_path.exists():
            db_path.unlink()
            logger.info("reset_db: deleted %s", db_path)
        _settings.set_flag("reset_db", False)
    init_db()
    create_tables()
    _apply_schema_migrations()
    _ensure_owner_user()

    from backend.core.database import get_engine
    from sqlalchemy.orm import sessionmaker
    session_factory = sessionmaker(bind=get_engine())
    with session_factory() as db:
        _sync_first_run_from_db(db)
        _platforms_seeded = _seed_system_platforms(db)
        _profiles_seeded = _seed_default_profiles(db)
        # Must follow profile seeding — links to the bundled dos/win31 profiles.
        _dosbox_envs_seeded = _seed_dosbox_environments(db)
        _cleanup_stale_sessions(db)
        _flag_corrupt_platform_working_paths(db)
        db.commit()

    app.state.seed_warnings = not (_platforms_seeded and _profiles_seeded and _dosbox_envs_seeded)
    if not _platforms_seeded or not _profiles_seeded or not _dosbox_envs_seeded:
        raise RuntimeError(
            "Startup aborted: required seed data could not be created — see logs above."
        )

    _heal_interrupted_rom_pack_clones()
    _scan_installed_emulators()
    _sync_detected_emulator_paths()

    from backend.service.utils.platform.windows.app_container import validate_descriptor_grant_surface as _validate_grants
    _validate_grants()
    logger.info("Startup: descriptor grant surface validated — all path_keys resolvable")

    try:
        from backend.service.utils.emulator_catalog import _get_eras_config as _warm_eras
        _warm_eras()
    except Exception as exc:
        logger.warning("Failed to preload eras.yaml at startup: %s", exc)

    _tray_stop_fn = None
    try:
        from backend.tray import start as _tray_start, stop as _tray_stop_fn
        _tray_start()
    except Exception as exc:
        logger.warning("Tray icon not started: %s", exc)

    monitor_task = asyncio.create_task(_process_monitor_loop())

    yield

    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass

    # Finalize any sessions that exited while the monitor was between poll intervals.
    exited = process_registry.cleanup_exited()
    if exited:
        _write_session_ends(exited)

    # Mark still-running sessions as killed by backend shutdown before terminating.
    still_running = list(process_registry.get_all().items())
    if still_running:
        _write_session_ends(still_running, exit_code_override=-15)

    for pid in list(process_registry.get_all().keys()):
        process_registry.terminate(pid)

    if _tray_stop_fn is not None:
        _tray_stop_fn()
