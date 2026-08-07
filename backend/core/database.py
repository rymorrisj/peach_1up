from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlmodel import SQLModel

from backend.core.settings import get_db_path

_DB_PATH = get_db_path()
_ENGINE = None
_SESSION_FACTORY = None
_SETTINGS_TABLE_ENSURED = False


def _enforce_foreign_keys(dbapi_conn, _connection_record) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _ensure_engine() -> None:
    global _ENGINE, _SESSION_FACTORY
    if _ENGINE is not None:
        return

    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    _ENGINE = create_engine(
        f"sqlite:///{_DB_PATH}",
        connect_args={"check_same_thread": False},
    )
    event.listen(_ENGINE, "connect", _enforce_foreign_keys)

    _SESSION_FACTORY = sessionmaker(bind=_ENGINE, autocommit=False, autoflush=False)


def init_db() -> None:
    _ensure_engine()


def create_tables() -> None:
    if _ENGINE is None:
        raise RuntimeError("Database not initialised, call init_db() first.")
    SQLModel.metadata.create_all(bind=_ENGINE)


def get_engine():
    _ensure_engine()
    return _ENGINE


def ensure_settings_table() -> None:
    """Create only the settings table, safe to call at import time (T1)
    before the rest of backend.models.* has registered with SQLModel.metadata.

    Scoped to a single table via ``tables=[...]`` so it never touches (or
    depends on) any other model. The later lifespan-time create_tables() call
    still runs create_all() across the full metadata as before; create_all()
    no-ops on tables that already exist, so calling this first causes no
    conflict.
    """
    global _SETTINGS_TABLE_ENSURED
    if _SETTINGS_TABLE_ENSURED:
        return
    from backend.models.settings import Settings
    SQLModel.metadata.create_all(get_engine(), tables=[Settings.__table__])
    _SETTINGS_TABLE_ENSURED = True


def get_db() -> Generator[Session, None, None]:
    _ensure_engine()
    db = _SESSION_FACTORY()
    try:
        yield db
    finally:
        db.close()
