import sys
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlmodel import SQLModel

if getattr(sys, "frozen", False):
    _DB_PATH = Path("database") / "data" / "peach1up.db"
else:
    _DB_PATH = Path(__file__).resolve().parents[2] / "database" / "data" / "peach1up.db"
_ENGINE = None
_SESSION_FACTORY = None


def _enforce_foreign_keys(dbapi_conn, _connection_record) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def init_db() -> None:
    global _ENGINE, _SESSION_FACTORY

    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    _ENGINE = create_engine(
        f"sqlite:///{_DB_PATH}",
        connect_args={"check_same_thread": False},
    )
    event.listen(_ENGINE, "connect", _enforce_foreign_keys)

    _SESSION_FACTORY = sessionmaker(bind=_ENGINE, autocommit=False, autoflush=False)


def create_tables() -> None:
    if _ENGINE is None:
        raise RuntimeError("Database not initialised — call init_db() first.")
    SQLModel.metadata.create_all(bind=_ENGINE)


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
