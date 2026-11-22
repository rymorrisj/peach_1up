import sqlite3

from backend.core.logger import get_logger

logger = get_logger(__name__)

# The "era" concept was renamed to "platform". Stored values (dos, win98,
# ps1, ...) are unchanged; only the column names move.
_PLATFORM_COLUMN_RENAMES: tuple[tuple[str, str, str], ...] = (
    ("game_item_bundles", "era", "platform"),
    ("game_item_bundles", "era_confirmed", "platform_confirmed"),
    ("app_item_bundles", "era", "platform"),
    ("environment_items", "era", "platform"),
    ("profile_items", "era", "platform"),
)
_PLATFORM_COLUMN_DROPS: tuple[tuple[str, str], ...] = (
    ("environment_items", "supported_eras"),
)
_SQLITE_RENAME_COLUMN_MIN = (3, 25, 0)
_SQLITE_DROP_COLUMN_MIN = (3, 35, 0)

# Catalog rows older builds seeded as is_system Environments. Deleted once
# nothing references them; the seeded DOS row is kept and made a normal row.
_RETIRED_SYSTEM_ENVIRONMENT_SLUGS: tuple[str, ...] = (
    "86box", "duckstation", "pcsx2", "mesen", "project64", "flycast", "xemu",
)


def _plan_platform_column_changes(engine) -> tuple[list[tuple[str, str, str]], list[tuple[str, str]]]:
    """Read-only: which renames and drops this DB still needs, from a fresh
    schema read per table."""
    from sqlalchemy import inspect as sa_inspect

    renames: list[tuple[str, str, str]] = []
    for table, old, new in _PLATFORM_COLUMN_RENAMES:
        inspector = sa_inspect(engine)
        if table not in inspector.get_table_names():
            continue
        columns = {c["name"] for c in inspector.get_columns(table)}
        if old in columns and new in columns:
            logger.error(
                "Schema migration: %s has both %s and %s; not renaming. Resolve manually.",
                table, old, new,
            )
        elif old in columns:
            renames.append((table, old, new))

    drops: list[tuple[str, str]] = []
    for table, column in _PLATFORM_COLUMN_DROPS:
        inspector = sa_inspect(engine)
        if table not in inspector.get_table_names():
            continue
        if column in {c["name"] for c in inspector.get_columns(table)}:
            drops.append((table, column))
    return renames, drops


def _require_sqlite_support(engine, renames: list, drops: list) -> None:
    """Fail before touching the DB when its SQLite cannot run the pending steps."""
    if engine.dialect.name != "sqlite" or not (renames or drops):
        return
    version = sqlite3.sqlite_version_info
    if renames and version < _SQLITE_RENAME_COLUMN_MIN:
        raise RuntimeError(
            f"SQLite {sqlite3.sqlite_version} cannot rename columns (needs 3.25 or newer). "
            "The database was not changed. Update Peach 1UP's bundled Python/SQLite and restart."
        )
    if drops and version < _SQLITE_DROP_COLUMN_MIN:
        raise RuntimeError(
            f"SQLite {sqlite3.sqlite_version} cannot drop columns (needs 3.35 or newer). "
            "The database was not changed. Update Peach 1UP's bundled Python/SQLite and restart."
        )


def _apply_platform_column_changes(conn, renames: list, drops: list) -> None:
    from sqlalchemy import text

    for table, old, new in renames:
        conn.execute(text(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}"))
        conn.commit()
        logger.info("Schema migration: renamed %s.%s to %s", table, old, new)
    for table, column in drops:
        conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
        conn.commit()
        logger.info("Schema migration: dropped %s.%s", table, column)


def _migrate_platform_environment_rows(engine) -> None:
    """Data side of the era to platform change, idempotent:

    1. The seeded DOS Environment becomes a normal row (is_system false).
    2. environment_item_id is cleared on console bundles and on PC bundles
       linked to the retired 86Box system row. Links to the DOS row stay.
    3. Retired system rows are deleted only when nothing references them
       (bundles, launch history, tags or any other foreign key).
    """
    from sqlalchemy import inspect as sa_inspect, text

    from backend.constants_generated import PC_PLATFORMS

    inspector = sa_inspect(engine)
    tables = set(inspector.get_table_names())
    if "environment_items" not in tables:
        return

    with engine.connect() as conn:
        flipped = conn.execute(text(
            "UPDATE environment_items SET is_system = 0 "
            "WHERE slug = 'dos' AND emulator_slug = 'dosbox-x' AND is_system = 1"
        )).rowcount
        conn.commit()
        if flipped:
            logger.info("Schema migration: DOS Environment is now a normal Environment row")

        pc_platforms = sorted(PC_PLATFORMS)
        pc_params = {f"pc{i}": p for i, p in enumerate(pc_platforms)}
        pc_list = ", ".join(f":pc{i}" for i in range(len(pc_platforms)))
        cleared = 0
        for table in ("game_item_bundles", "app_item_bundles"):
            if table not in tables:
                continue
            columns = {c["name"] for c in inspector.get_columns(table)}
            if not {"platform", "environment_item_id"} <= columns:
                continue
            cleared += conn.execute(text(
                f"UPDATE {table} SET environment_item_id = NULL "
                "WHERE environment_item_id IS NOT NULL AND ("
                f"platform NOT IN ({pc_list}) "
                "OR environment_item_id IN (SELECT id FROM environment_items "
                "WHERE slug = '86box' AND emulator_slug = '86box' AND is_system = 1))"
            ), pc_params).rowcount
        conn.commit()
        if cleared:
            logger.info(
                "Schema migration: cleared environment_item_id on %d bundle(s) "
                "(console bundles and PC bundles linked to the retired 86Box row)",
                cleared,
            )

        references: set[tuple[str, str]] = set()
        for table in tables:
            for fk in inspector.get_foreign_keys(table):
                if fk.get("referred_table") == "environment_items":
                    for column in fk.get("constrained_columns") or []:
                        references.add((table, column))
        for table, column in (
            ("game_item_bundles", "environment_item_id"),
            ("app_item_bundles", "environment_item_id"),
            ("launch_history", "environment_item_id"),
        ):
            if table in tables and column in {c["name"] for c in inspector.get_columns(table)}:
                references.add((table, column))

        rows = conn.execute(
            text(
                "SELECT id, slug FROM environment_items WHERE is_system = 1 "
                "AND slug = emulator_slug AND slug IN ("
                + ", ".join(f":s{i}" for i in range(len(_RETIRED_SYSTEM_ENVIRONMENT_SLUGS)))
                + ")"
            ),
            {f"s{i}": slug for i, slug in enumerate(_RETIRED_SYSTEM_ENVIRONMENT_SLUGS)},
        ).fetchall()
        deleted: list[str] = []
        kept: list[str] = []
        for env_id, slug in rows:
            in_use = any(
                conn.execute(
                    text(f"SELECT 1 FROM {table} WHERE {column} = :id LIMIT 1"), {"id": env_id}
                ).first()
                for table, column in sorted(references)
            )
            if not in_use and "entity_tags" in tables:
                in_use = conn.execute(text(
                    "SELECT 1 FROM entity_tags WHERE entity_type = 'environment_item' "
                    "AND entity_id = :id LIMIT 1"
                ), {"id": env_id}).first() is not None
            if in_use:
                kept.append(slug)
                continue
            conn.execute(text("DELETE FROM environment_items WHERE id = :id"), {"id": env_id})
            deleted.append(slug)
        conn.commit()
        if deleted:
            logger.info("Schema migration: deleted retired system Environment row(s): %s", ", ".join(deleted))
        if kept:
            logger.info(
                "Schema migration: kept retired system Environment row(s) still referenced: %s",
                ", ".join(kept),
            )


def _apply_schema_migrations() -> None:
    """Add columns and apply schema changes introduced after initial creation.

    Safe to run on every startup, all operations are idempotent.
    """
    from backend.core.database import get_engine
    from sqlalchemy import inspect as sa_inspect, text

    engine = get_engine()

    # Renames and drops run first, after a SQLite capability check that
    # raises before anything is written.
    renames, drops = _plan_platform_column_changes(engine)
    _require_sqlite_support(engine, renames, drops)
    if renames or drops:
        with engine.connect() as conn:
            _apply_platform_column_changes(conn, renames, drops)

    # Idempotent ADD COLUMN catch-ups for non-game tables. The game schema
    # (game_item_bundles / game_items leaf / launch_history / restrictions)
    # is created directly by create_tables() in its consolidated shape, there is no
    # legacy game DB to migrate, so no game data-reshape steps live here.
    # Exception: game_items.original_name was added after that consolidated
    # shape was set, so it still needs the same additive catch-up as any other
    # post-creation column on an existing DB.
    pending: list[tuple[str, str, str]] = [
        ("environment_items", "installed_at", "DATETIME"),
        ("environment_items", "hardware_profile", "TEXT DEFAULT 'standard'"),
        ("environment_items", "machine_override", "TEXT"),
        ("profile_items", "use_drive", "INTEGER NOT NULL DEFAULT 1"),
        ("profile_items", "container_enabled", "INTEGER"),
        ("profile_items", "enable_dgvoodoo2", "INTEGER NOT NULL DEFAULT 0"),
        ("user_items", "identity_token_secret", "TEXT"),
        ("user_items", "session_token_hash", "TEXT"),
        ("user_items", "session_token_expires_at", "DATETIME"),
        ("user_items", "session_token_ttl", "INTEGER"),
        ("tags", "is_system", "INTEGER NOT NULL DEFAULT 0"),
        ("user_items", "can_manage_users", "INTEGER NOT NULL DEFAULT 0"),
        ("game_items", "original_name", "VARCHAR"),
        ("game_items", "folder_owned", "INTEGER"),
        ("media_item_bundles", "content_rating", "VARCHAR"),
    ]
    with engine.connect() as conn:
        inspector = sa_inspect(engine)
        for table, column, col_type in pending:
            if table not in inspector.get_table_names():
                continue
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

        # Enforce at most one owner account via a partial unique index. This is
        # the real backstop behind POST /auth/setup-owner's has_owner pre-check:
        # without it, two concurrent setup-owner requests can both pass the
        # SELECT COUNT and both INSERT an owner row (TOCTOU). The pre-check stays
        # for clean error messages; this index is the guarantee.
        users_indexes = {ix["name"] for ix in inspector.get_indexes("user_items")}
        if "idx_single_owner" not in users_indexes:
            owner_count = conn.execute(
                text("SELECT COUNT(*) FROM user_items WHERE is_owner = 1")
            ).scalar()
            if owner_count and owner_count > 1:
                # Fail loud: the DB already holds multiple owner rows (a prior
                # race or manual tampering). We refuse to silently demote one —
                # picking which owner survives is a security decision for an
                # operator, not something a startup migration should guess.
                raise RuntimeError(
                    f"Cannot enforce single-owner constraint: {owner_count} owner "
                    "accounts already exist. Resolve the extra owner row(s) "
                    "manually, then restart."
                )
            conn.execute(text(
                "CREATE UNIQUE INDEX idx_single_owner ON user_items (is_owner) WHERE is_owner = 1"
            ))
            conn.commit()
            logger.info("Schema migration: enforced single-owner partial unique index on user_items")

        # Backfill the index on game_items.file_path for DBs provisioned before
        # index=True was added to the model. Name matches SQLAlchemy's own naming
        # convention for this column (ix_<table>_<column>) so this is a no-op on a
        # freshly created DB, create_all() already made the same-named index —
        # and a real backfill on an existing DB that predates it.
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_game_items_file_path "
            "ON game_items (file_path)"
        ))
        conn.commit()
        logger.info("Schema migration: confirmed ix_game_items_file_path exists")

        # Same backfill for media_item_bundles.content_rating (index=True on
        # the model). ADD COLUMN above never creates an index, so a DB that
        # gained the column through it needs this; on a fresh DB create_all()
        # already made the same-named index and this is a no-op.
        if "media_item_bundles" in inspector.get_table_names():
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_media_item_bundles_content_rating "
                "ON media_item_bundles (content_rating)"
            ))
            conn.commit()
            logger.info("Schema migration: confirmed ix_media_item_bundles_content_rating exists")

    _migrate_platform_environment_rows(engine)
