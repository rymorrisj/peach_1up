import asyncio
import json
import logging
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI

from backend.core import install_registry, process_registry
from backend.core.database import create_tables, init_db
from backend.core.settings import init_settings
import backend.models.user  # noqa: F401 — registers User with SQLModel.metadata
import backend.models.media_restriction  # noqa: F401 — registers MediaRestriction with SQLModel.metadata

logger = logging.getLogger(__name__)

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
        "name": "VirtualBox",
        "slug": "virtualbox",
        "era": "win95",
        "emulator_slug": "virtualbox",
        "is_system": True,
        "supported_eras": json.dumps(["win95", "win98", "winxp"]),
        "download_url": "https://www.virtualbox.org",
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
        "name": "xemu",
        "slug": "xemu",
        "era": "xbox",
        "emulator_slug": "xemu",
        "is_system": True,
        "supported_eras": json.dumps(["xbox"]),
        "download_url": "https://xemu.app",
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
]

_DEFAULT_PROFILES = [
    {"name": "DOS Default",      "slug": "dos-default",    "era": "dos",   "emulator_slug": "dosbox-x",   "is_bundled": True, "is_accuracy_mode": False},
    {"name": "Win 3.1 Default",  "slug": "win31-default",  "era": "win31", "emulator_slug": "dosbox-x",   "is_bundled": True, "is_accuracy_mode": False},
    {"name": "Win 95 Compat",    "slug": "win95-compat",   "era": "win95", "emulator_slug": "virtualbox",  "is_bundled": True, "is_accuracy_mode": False},
    {"name": "Win 95 Accuracy",  "slug": "win95-accuracy", "era": "win95", "emulator_slug": "86box",       "is_bundled": True, "is_accuracy_mode": True},
    {"name": "Win 98 Compat",    "slug": "win98-compat",   "era": "win98", "emulator_slug": "virtualbox",  "is_bundled": True, "is_accuracy_mode": False},
    {"name": "Win 98 Accuracy",  "slug": "win98-accuracy", "era": "win98", "emulator_slug": "86box",       "is_bundled": True, "is_accuracy_mode": True},
    {"name": "Win XP Default",   "slug": "winxp-default",  "era": "winxp", "emulator_slug": "virtualbox",  "is_bundled": True, "is_accuracy_mode": False},
    {"name": "PS1 Default",      "slug": "ps1-default",    "era": "ps1",   "emulator_slug": "duckstation", "is_bundled": True, "is_accuracy_mode": False},
    {"name": "PS2 Default",      "slug": "ps2-default",    "era": "ps2",   "emulator_slug": "pcsx2",       "is_bundled": True, "is_accuracy_mode": False},
    {"name": "Xbox OG Default",  "slug": "xbox-default",   "era": "xbox",  "emulator_slug": "xemu",        "is_bundled": True, "is_accuracy_mode": False},
    {"name": "NES Default",      "slug": "nes-default",    "era": "nes",   "emulator_slug": "mesen",       "is_bundled": True, "is_accuracy_mode": False},
    {"name": "N64 Default",      "slug": "n64-default",    "era": "n64",   "emulator_slug": "project64",   "is_bundled": True, "is_accuracy_mode": False},
]


def _sync_first_run_from_db(db) -> None:
    from backend.models.settings import Settings as SettingsModel
    from backend.service.utils import settings as _settings_mod
    row = db.get(SettingsModel, "first_run_complete")
    if row and row.value == "true":
        state = _settings_mod._require_init()
        state["first_run_complete"] = True


def _seed_system_platforms(db) -> None:
    try:
        from backend.models import Platform
        if db.query(Platform).filter(Platform.is_system.is_(True)).count() > 0:
            return
        for data in _SYSTEM_PLATFORMS:
            db.add(Platform(**data))
        db.flush()
        logger.info("Seeded %d system platforms", len(_SYSTEM_PLATFORMS))
    except Exception as exc:
        db.rollback()
        logger.warning("System platform seeding skipped: %s", exc)


def _seed_default_profiles(db) -> None:
    try:
        from backend.models import Profile
        if db.query(Profile).filter(Profile.is_bundled.is_(True)).count() > 0:
            return
        for data in _DEFAULT_PROFILES:
            db.add(Profile(**data))
        db.flush()
        logger.info("Seeded %d default profiles", len(_DEFAULT_PROFILES))
    except Exception as exc:
        db.rollback()
        logger.warning("Default profile seeding skipped: %s", exc)


def _cleanup_stale_sessions(db) -> None:
    try:
        from backend.models import LaunchHistory
        stale = db.query(LaunchHistory).filter(LaunchHistory.ended_at.is_(None)).all()
        for session in stale:
            session.ended_at = datetime.utcnow()
            session.exit_code = -1
        db.flush()
        if stale:
            logger.info("Startup: closed %d stale launch session(s)", len(stale))
    except Exception as exc:
        db.rollback()
        logger.warning("Startup session cleanup failed: %s", exc)


def _write_session_ends(exited: list, exit_code_override: int | None = None) -> None:
    if not exited:
        return
    from backend.core.database import get_engine
    from backend.models import LaunchHistory
    from sqlalchemy.orm import sessionmaker
    session_factory = sessionmaker(bind=get_engine())
    with session_factory() as db:
        for _pid, entry in exited:
            if entry.launch_history_id is None:
                continue
            history = db.get(LaunchHistory, entry.launch_history_id)
            if history and history.ended_at is None:
                history.ended_at = datetime.utcnow()
                if exit_code_override is not None:
                    history.exit_code = exit_code_override
                else:
                    rc = getattr(entry.process_handle, "returncode", None) if entry.process_handle else None
                    history.exit_code = rc if rc is not None else -1
        db.commit()


async def _process_monitor_loop() -> None:
    while True:
        try:
            await asyncio.sleep(5)
            exited = process_registry.cleanup_exited()
            if exited:
                await asyncio.to_thread(_write_session_ends, exited)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Process monitor iteration failed (will retry): %s", exc)


_SETUP_ADMIN_SCRIPT = (
    Path(__file__).resolve().parent.parent.parent / "scripts" / "setup_admin_user.py"
)


def _ensure_owner_user() -> None:
    """Prompt for owner account creation on first run if no owner record exists.

    Calls setup_admin_user.py interactively. Aborts startup (raises RuntimeError)
    if the script exits non-zero.
    """
    from backend.core.database import get_engine
    from backend.models.user import User
    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(bind=get_engine())
    with session_factory() as db:
        has_owner = db.query(User).filter(User.is_owner.is_(True)).count() > 0

    if has_owner:
        return

    if not _SETUP_ADMIN_SCRIPT.exists():
        raise RuntimeError(
            f"Admin setup script not found: {_SETUP_ADMIN_SCRIPT}\n"
            "Re-clone the repository or restore scripts/setup_admin_user.py."
        )

    result = subprocess.run([sys.executable, str(_SETUP_ADMIN_SCRIPT)])

    if result.returncode != 0:
        raise RuntimeError(
            f"Owner account setup failed (exit {result.returncode}). "
            "Restart the application to try again."
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
        ("library_items", "slug", "TEXT"),
        ("library_items", "folder_path", "TEXT"),
        ("library_items", "cover_path", "TEXT"),
    ]
    with engine.connect() as conn:
        inspector = sa_inspect(engine)
        for table, column, col_type in pending:
            existing = {c["name"] for c in inspector.get_columns(table)}
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                conn.commit()
                logger.info("Schema migration: added %s.%s (%s)", table, column, col_type)

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


def _export_openapi_spec(app: FastAPI) -> None:
    try:
        import json
        from pathlib import Path as _Path
        output = _Path(__file__).resolve().parent.parent.parent / "shared" / "openapi.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
        logger.info("OpenAPI spec exported to %s", output)
    except Exception as exc:
        logger.warning("OpenAPI spec export failed (non-fatal): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_settings()
    init_db()
    create_tables()
    _apply_schema_migrations()
    _ensure_owner_user()

    from backend.core.database import get_engine
    from sqlalchemy.orm import sessionmaker
    session_factory = sessionmaker(bind=get_engine())
    with session_factory() as db:
        _sync_first_run_from_db(db)
        _seed_system_platforms(db)
        _seed_default_profiles(db)
        _cleanup_stale_sessions(db)
        db.commit()

    _scan_installed_emulators()
    _export_openapi_spec(app)

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
