#!/usr/bin/env python3
"""Load smart_media_detector's hash_index.json into the hash_index_entries DB table.

Standalone, run manually after regenerating hash_index.json via
smart_media_detector's build_index.py. Not wired into any startup/lifespan
hook. Upserts by sha1: existing rows are updated in place, new rows are
added, nothing already in the table is wiped.

Usage:
    python -m scripts.ingest_hash_index [--index <path>]
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_DEFAULT_INDEX = (
    PROJECT_ROOT
    / "backend/service/utils/smart_media_detector/hashing/hash_index.json"
)


def _get_db_path() -> Path:
    from backend.core.settings import get_db_path
    return get_db_path()


def _session_factory(db_path: Path):
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    def _enforce_fk(conn, _rec) -> None:
        conn.cursor().execute("PRAGMA foreign_keys=ON")

    event.listen(engine, "connect", _enforce_fk)

    from backend.models.hash_index import HashIndexEntry
    from sqlmodel import SQLModel
    # Scoped to this table only, mirrors database.py's ensure_settings_table():
    # safe to call standalone without depending on the backend having started
    # (and thus having already run the full create_tables() pass) first.
    SQLModel.metadata.create_all(engine, tables=[HashIndexEntry.__table__])

    return sessionmaker(bind=engine)


def load_index(index_path: Path) -> dict:
    if not index_path.exists():
        raise FileNotFoundError(
            f"Hash index not found at {index_path}. "
            "Run smart_media_detector's build_index.py to generate it first."
        )
    with index_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def upsert_entries(session, entries: dict) -> tuple[int, int]:
    """Upsert every sha1 -> record pair. Returns (added, updated)."""
    from backend.models.hash_index import HashIndexEntry
    from sqlalchemy import select
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    if not entries:
        return 0, 0

    table = HashIndexEntry.__table__
    rows = [
        {
            "sha1": sha1,
            "title": record.get("title"),
            "platform": record.get("platform"),
            "era": record.get("era"),
            "md5": record.get("md5"),
            "crc32": record.get("crc32"),
        }
        for sha1, record in entries.items()
    ]

    existing = {row[0] for row in session.execute(select(table.c.sha1)).all()}
    added = sum(1 for row in rows if row["sha1"] not in existing)
    updated = len(rows) - added

    stmt = sqlite_insert(table)
    stmt = stmt.on_conflict_do_update(
        index_elements=["sha1"],
        set_={
            "title": stmt.excluded.title,
            "platform": stmt.excluded.platform,
            "era": stmt.excluded.era,
            "md5": stmt.excluded.md5,
            "crc32": stmt.excluded.crc32,
        },
    )
    session.execute(stmt, rows)
    session.commit()

    return added, updated


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load smart_media_detector's hash_index.json into the hash_index_entries DB table."
    )
    parser.add_argument(
        "--index",
        type=Path,
        default=_DEFAULT_INDEX,
        metavar="PATH",
        help=f"Path to hash_index.json (default: {_DEFAULT_INDEX})",
    )
    args = parser.parse_args()

    try:
        entries = load_index(args.index)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    session_factory = _session_factory(_get_db_path())
    with session_factory() as session:
        added, updated = upsert_entries(session, entries)

    print(f"Entries in hash_index.json: {len(entries)}")
    print(f"Added:   {added}")
    print(f"Updated: {updated}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
