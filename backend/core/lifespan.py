from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.core import process_registry
from backend.core.database import create_tables, init_db
from backend.core.settings import init_settings


def _sync_first_run_from_db(db) -> None:
    """Seed first_run_complete into in-memory settings from DB on startup.

    Handles the Docker case where config/ is read-only so settings.yaml
    can't be written, but the DB can record completion across restarts.
    """
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

    yield

    process_registry.cleanup_exited()
    for pid in list(process_registry.get_all().keys()):
        process_registry.terminate(pid)
