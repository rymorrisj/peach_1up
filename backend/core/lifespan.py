import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI

from backend.core import install_registry, process_registry
from backend.core.database import create_tables, init_db
from backend.core.logger import get_logger
from backend.core.settings import get_base_path, init_settings
import backend.models.user  # noqa: F401 — registers User with SQLModel.metadata
import backend.models.media_restriction  # noqa: F401 — registers MediaRestriction with SQLModel.metadata
import backend.models.drive  # noqa: F401 — registers Drive with SQLModel.metadata
import backend.models.tag  # noqa: F401 — registers Tag and LibraryItemTag with SQLModel.metadata

logger = get_logger(__name__)

_SYSTEM_PLATFORMS = [
    {
        "name": "DOSBox-X",
        "slug": "dosbox-x",
        "era": "dos",
        "emulator_slug": "dosbox-x",
        "is_system": True,
        "supported_eras": json.dumps(["dos", "win31"]),
        "download_url": "https://dosbox-x.com",
        "status": "unknown",
    },
    {
        "name": "86Box",
        "slug": "86box",
        "era": "win95",
        "emulator_slug": "86box",
        "is_system": True,
        "supported_eras": json.dumps(["win95", "win98"]),
        "download_url": "https://86box.net",
        "status": "unknown",
    },
    {
        "name": "DuckStation",
        "slug": "duckstation",
        "era": "ps1",
        "emulator_slug": "duckstation",
        "is_system": True,
        "supported_eras": json.dumps(["ps1"]),
        "download_url": "https://www.duckstation.org",
        "status": "unknown",
    },
    {
        "name": "PCSX2",
        "slug": "pcsx2",
        "era": "ps2",
        "emulator_slug": "pcsx2",
        "is_system": True,
        "supported_eras": json.dumps(["ps2"]),
        "download_url": "https://pcsx2.net",
        "status": "unknown",
    },
    {
        "name": "Mesen",
        "slug": "mesen",
        "era": "nes",
        "emulator_slug": "mesen",
        "is_system": True,
        "supported_eras": json.dumps(["nes"]),
        "download_url": "https://www.mesen.ca",
        "status": "unknown",
    },
    {
        "name": "Project64",
        "slug": "project64",
        "era": "n64",
        "emulator_slug": "project64",
        "is_system": True,
        "supported_eras": json.dumps(["n64"]),
        "download_url": "https://www.pj64-emu.com",
        "status": "unknown",
    },
    {
        "name": "Flycast",
        "slug": "flycast",
        "era": "dreamcast",
        "emulator_slug": "flycast",
        "is_system": True,
        "supported_eras": json.dumps(["dreamcast"]),
        "download_url": "https://github.com/flyinghead/flycast",
        "status": "unknown",
    },
    {
        "name": "xemu",
        "slug": "xemu",
        "era": "xbox",
        "emulator_slug": "xemu",
        "is_system": True,
        "supported_eras": json.dumps(["xbox"]),
        "download_url": "https://xemu.app",
        "status": "unknown",
    },
]

_DEFAULT_PROFILES = [
    {"name": "DOS Default",     "slug": "dos-default",   "era": "dos",   "emulator_slug": "dosbox-x",   "is_bundled": True},
    {"name": "Win 3.1 Default", "slug": "win31-default", "era": "win31", "emulator_slug": "dosbox-x",   "is_bundled": True},
    {"name": "Win 95 Default",  "slug": "win95-compat",  "era": "win95", "emulator_slug": "86box",       "is_bundled": True},
    {"name": "Win 98 Default",  "slug": "win98-compat",  "era": "win98", "emulator_slug": "86box",       "is_bundled": True},
    {"name": "Win XP Default",  "slug": "winxp-default", "era": "winxp", "emulator_slug": "86box",       "is_bundled": True},
    {"name": "PS1 Default",     "slug": "ps1-default",   "era": "ps1",   "emulator_slug": "duckstation", "is_bundled": True},
    {"name": "PS2 Default",     "slug": "ps2-default",   "era": "ps2",   "emulator_slug": "pcsx2",       "is_bundled": True},
    {"name": "Xbox OG Default", "slug": "xbox-default",  "era": "xbox",  "emulator_slug": "xemu",        "is_bundled": True},
    {"name": "NES Default",     "slug": "nes-default",   "era": "nes",   "emulator_slug": "mesen",       "is_bundled": True},
    {"name": "N64 Default",        "slug": "n64-default",        "era": "n64",       "emulator_slug": "project64",   "is_bundled": True},
    {"name": "Dreamcast Default",  "slug": "dreamcast-default",  "era": "dreamcast", "emulator_slug": "flycast",     "is_bundled": True},
]


def _sync_first_run_from_db(db) -> None:
    from backend.models.settings import Settings as SettingsModel
    from backend.service.utils import settings as _settings_mod
    row = db.get(SettingsModel, "first_run_complete")
    if row and row.value == "true":
        state = _settings_mod._require_init()
        state["first_run_complete"] = True


def _seed_system_platforms(db) -> bool:
    try:
        from backend.models import Platform
        if db.query(Platform).filter(Platform.is_system.is_(True)).count() > 0:
            return True
        for data in _SYSTEM_PLATFORMS:
            db.add(Platform(**data))
        db.flush()
        logger.info("Seeded %d system platforms", len(_SYSTEM_PLATFORMS))
        return True
    except Exception as exc:
        db.rollback()
        logger.error("System platform seeding failed: %s", exc)
        return False


def _seed_default_profiles(db) -> bool:
    try:
        from backend.models import Profile
        if db.query(Profile).filter(Profile.is_bundled.is_(True)).count() > 0:
            return True
        for data in _DEFAULT_PROFILES:
            db.add(Profile(**data))
        db.flush()
        logger.info("Seeded %d default profiles", len(_DEFAULT_PROFILES))
        return True
    except Exception as exc:
        db.rollback()
        logger.error("Default profile seeding failed: %s", exc)
        return False



def _cleanup_stale_sessions(db) -> None:
    try:
        from backend.models import LaunchHistory
        stale = db.query(LaunchHistory).filter(LaunchHistory.ended_at.is_(None)).all()
        for session in stale:
            session.ended_at = datetime.now(timezone.utc)
            session.exit_code = -1
        db.flush()
        if stale:
            logger.info("Startup: closed %d stale launch session(s)", len(stale))
    except Exception as exc:
        db.rollback()
        logger.warning("Startup session cleanup failed: %s", exc)


from backend.service.launch.history import write_session_ends as _write_session_ends


async def _process_monitor_loop() -> None:
    from backend.service.launch.monitor import poll_short_lived
    while True:
        try:
            await asyncio.sleep(5)
            exited = process_registry.cleanup_exited()
            if exited:
                await asyncio.to_thread(_write_session_ends, exited)
            await asyncio.to_thread(poll_short_lived)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Process monitor iteration failed (will retry): %s", exc)


def _ensure_owner_user() -> None:
    """Log a warning if no owner account exists; first-run web flow handles creation."""
    from backend.core.database import get_engine
    from backend.models.user import User
    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(bind=get_engine())
    with session_factory() as db:
        has_owner = db.query(User).filter(User.is_owner.is_(True)).count() > 0

    if not has_owner:
        logger.warning(
            "No owner account found. Complete the first-run setup in the web interface."
        )


def _apply_schema_migrations() -> None:
    """Add columns and apply schema changes introduced after initial creation.

    Safe to run on every startup — all operations are idempotent.
    """
    import re
    from backend.core.database import get_engine
    from sqlalchemy import inspect as sa_inspect, text

    engine = get_engine()
    pending: list[tuple[str, str, str]] = [
        ("library_items", "content_rating", "TEXT"),
        ("library_items", "executable_path", "TEXT"),
        ("library_items", "slug", "TEXT"),
        ("library_items", "folder_path", "TEXT"),
        ("library_items", "cover_path", "TEXT"),
        ("library_items", "installed", "INTEGER NOT NULL DEFAULT 0"),
        ("platforms", "installed_at", "DATETIME"),
        ("platforms", "hardware_profile", "TEXT DEFAULT 'standard'"),
        ("platforms", "machine_override", "TEXT"),
        ("profiles", "drive_slug", "TEXT"),
        ("profiles", "use_drive", "INTEGER NOT NULL DEFAULT 1"),
        ("profiles", "container_enabled", "INTEGER"),
        ("library_items", "requires_install", "INTEGER NOT NULL DEFAULT 0"),
        ("library_items", "detection_reason", "TEXT"),
    ]
    with engine.connect() as conn:
        inspector = sa_inspect(engine)
        for table, column, col_type in pending:
            existing = {c["name"] for c in inspector.get_columns(table)}
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                conn.commit()
                logger.info("Schema migration: added %s.%s (%s)", table, column, col_type)

        # Rebuild launch_history to add target_type/platform_id and make library_item_id nullable
        if "launch_history" in inspector.get_table_names():
            lh_cols = {c["name"] for c in inspector.get_columns("launch_history")}
            if "target_type" not in lh_cols:
                conn.execute(text("""
                    CREATE TABLE launch_history_new (
                        id INTEGER PRIMARY KEY,
                        target_type TEXT NOT NULL DEFAULT 'library_item',
                        library_item_id INTEGER REFERENCES library_items(id) ON DELETE CASCADE,
                        platform_id INTEGER REFERENCES platforms(id) ON DELETE CASCADE,
                        profile_id INTEGER REFERENCES profiles(id) ON DELETE SET NULL,
                        emulator_slug TEXT NOT NULL,
                        started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        ended_at DATETIME,
                        exit_code INTEGER,
                        error_message TEXT,
                        network_blocked BOOLEAN NOT NULL DEFAULT 1,
                        job_isolated BOOLEAN NOT NULL DEFAULT 0,
                        sandboxed BOOLEAN NOT NULL DEFAULT 0,
                        sandbox_memory_limit_mb INTEGER,
                        sandbox_cpu_limit_percent INTEGER
                    )
                """))
                conn.execute(text("""
                    INSERT INTO launch_history_new (
                        id, target_type, library_item_id, platform_id, profile_id, emulator_slug,
                        started_at, ended_at, exit_code, error_message,
                        network_blocked, job_isolated, sandboxed,
                        sandbox_memory_limit_mb, sandbox_cpu_limit_percent
                    )
                    SELECT id, 'library_item', library_item_id, NULL, profile_id, emulator_slug,
                        started_at, ended_at, exit_code, error_message,
                        network_blocked, job_isolated, sandboxed,
                        sandbox_memory_limit_mb, sandbox_cpu_limit_percent
                    FROM launch_history
                """))
                conn.execute(text("DROP TABLE launch_history"))
                conn.execute(text("ALTER TABLE launch_history_new RENAME TO launch_history"))
                conn.commit()
                logger.info("Schema migration: rebuilt launch_history with target_type and platform_id")

        # Drop legacy user_restrictions table
        if "user_restrictions" in sa_inspect(engine).get_table_names():
            conn.execute(text("DROP TABLE user_restrictions"))
            conn.commit()
            logger.info("Schema migration: dropped user_restrictions table")

        # Backfill slugs for existing library items
        items = conn.execute(
            text("SELECT id, title FROM library_items WHERE slug IS NULL")
        ).fetchall()
        if items:
            for item_id, title in items:
                base = re.sub(
                    r'[^a-z0-9-]', '',
                    re.sub(r'\s+', '-', (title or '').lower())
                ).strip('-') or 'item'
                candidate = base
                n = 2
                while True:
                    exists = conn.execute(
                        text("SELECT 1 FROM library_items WHERE slug = :s"), {"s": candidate}
                    ).fetchone()
                    if not exists:
                        break
                    candidate = f"{base}-{n}"
                    n += 1
                conn.execute(
                    text("UPDATE library_items SET slug = :s WHERE id = :id"),
                    {"s": candidate, "id": item_id},
                )
            conn.commit()
            logger.info("Schema migration: backfilled slugs for %d library item(s)", len(items))


def _flag_corrupt_platform_working_paths(db) -> None:
    try:
        from backend.models import Platform
        corrupt = (
            db.query(Platform)
            .filter(Platform.working_image_path.like("%.cfg"))
            .all()
        )
        for p in corrupt:
            logger.warning(
                "Platform %s (%s) has a .cfg file as working_image_path — "
                "this record was created by the broken provisioner and must be re-registered",
                p.id,
                p.name,
            )
            if p.status != "degraded":
                p.status = "degraded"
        db.flush()
    except Exception as exc:
        db.rollback()
        logger.warning("Corrupt working_image_path check failed: %s", exc)


def _ensure_default_paths() -> None:
    base = get_base_path()
    lib = base / "library"
    for d in [
        lib / "media",
        lib / "system",
        lib / "system" / "bios",
        lib / "system" / "roms",
        lib / "system" / "os",
        lib / "system" / "roms" / "86box",
        lib / "system" / "profiles",
    ]:
        d.mkdir(parents=True, exist_ok=True)


def _sync_detected_emulator_paths() -> None:
    try:
        from backend.service.utils.emulator_catalog import detect_and_sync_all
        detect_and_sync_all()
        logger.info("Startup: detected emulator paths synced to settings")
    except Exception as exc:
        logger.warning("Startup emulator path sync failed: %s", exc)


def _scan_installed_emulators() -> None:
    try:
        from backend.service.utils.emulator_catalog import load_catalog
        from backend.service.utils.emulator_installer import detect_binary
        catalog = load_catalog()
        detected = 0
        for entry in catalog:
            slug = entry["slug"]
            path = detect_binary(slug)
            if path is not None:
                install_registry.set_status(slug, "complete", install_path=str(path))
                logger.info("Startup: %s detected at %s", slug, path)
                detected += 1
            else:
                logger.info("Startup: %s not detected", slug)
        logger.info("Startup: %d/%d emulators detected", detected, len(catalog))
    except Exception as exc:
        logger.warning("Startup emulator scan failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_settings()
    _ensure_default_paths()
    if os.environ.get("RESET_DB", "").lower() == "true":
        db_path = get_base_path() / "database" / "data" / "peach1up.db"
        if db_path.exists():
            db_path.unlink()
            logger.info("RESET_DB: deleted %s", db_path)
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
        _cleanup_stale_sessions(db)
        _flag_corrupt_platform_working_paths(db)
        db.commit()

    app.state.seed_warnings = not (_platforms_seeded and _profiles_seeded)
    if not _platforms_seeded or not _profiles_seeded:
        raise RuntimeError(
            "Startup aborted: required seed data could not be created — see logs above."
        )

    _scan_installed_emulators()
    _sync_detected_emulator_paths()

    from backend.service.utils.app_container import validate_descriptor_grant_surface as _validate_grants
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
