import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.core import install_registry, process_registry
from backend.core.database import create_tables, init_db
from backend.core.settings import init_settings

logger = logging.getLogger(__name__)


def _sync_first_run_from_db(db) -> None:
    """Seed first_run_complete into in-memory settings from DB on startup."""
    from backend.models.settings import Settings as SettingsModel
    from backend.service.utils import settings as _settings_mod
    row = db.get(SettingsModel, "first_run_complete")
    if row and row.value == "true":
        state = _settings_mod._require_init()
        state["first_run_complete"] = True


def _seed_bundled_profiles(db) -> None:
    from backend.models import Profile
    if db.query(Profile).count() == 0:
        pass  # seed logic deferred to P3.5-3 when bundled profiles are defined


def _scan_installed_emulators() -> None:
    try:
        from backend.service.utils.emulator_catalog import get_all_statuses
        statuses = get_all_statuses()
        installed_count = 0
        for s in statuses:
            if s["is_installed"]:
                install_registry.set_status(s["slug"], "complete", install_path=s["install_path"])
                installed_count += 1
        logger.info("Startup: detected %d/%d emulators installed", installed_count, len(statuses))
    except Exception as exc:
        logger.warning("Startup emulator scan failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_settings()
    init_db()
    create_tables()

    from backend.core.database import get_engine
    from sqlalchemy.orm import sessionmaker
    session_factory = sessionmaker(bind=get_engine())
    with session_factory() as db:
        _seed_bundled_profiles(db)
        _sync_first_run_from_db(db)
        db.commit()

    _scan_installed_emulators()

    yield

    process_registry.cleanup_exited()
    for pid in list(process_registry.get_all().keys()):
        process_registry.terminate(pid)
