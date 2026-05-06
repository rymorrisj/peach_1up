from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

_DB_PATH = Path("peach1up.db")
_ENGINE = None
_SESSION_FACTORY = None


def _enforce_foreign_keys(dbapi_conn, _connection_record) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def init_db() -> None:
    global _ENGINE, _SESSION_FACTORY

    _ENGINE = create_engine(
        f"sqlite:///{_DB_PATH}",
        connect_args={"check_same_thread": False},
    )
    event.listen(_ENGINE, "connect", _enforce_foreign_keys)

    _SESSION_FACTORY = sessionmaker(bind=_ENGINE, autocommit=False, autoflush=False)


def create_tables() -> None:
    from backend.models import Base
    if _ENGINE is None:
        raise RuntimeError("Database not initialised — call init_db() first.")
    Base.metadata.create_all(bind=_ENGINE)


def get_engine():
    if _ENGINE is None:
        raise RuntimeError("Database not initialised — call init_db() first.")
    return _ENGINE


def get_db() -> Generator[Session, None, None]:
    if _SESSION_FACTORY is None:
        raise RuntimeError("Database not initialised — call init_db() first.")
    db = _SESSION_FACTORY()
    try:
        yield db
    finally:
        db.close()
