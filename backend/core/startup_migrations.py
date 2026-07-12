from backend.core.logger import get_logger

logger = get_logger(__name__)


def _apply_schema_migrations() -> None:
    """Add columns and apply schema changes introduced after initial creation.

    Safe to run on every startup — all operations are idempotent.
    """
    from backend.core.database import get_engine
    from sqlalchemy import inspect as sa_inspect, text

    engine = get_engine()
    # Idempotent ADD COLUMN catch-ups for non-game tables. The game schema
    # (game_item_bundles / game_items leaf / launch_history / media_restrictions)
    # is created directly by create_tables() in its consolidated shape — there is no
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
        # freshly created DB — create_all() already made the same-named index —
        # and a real backfill on an existing DB that predates it.
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_game_items_file_path "
            "ON game_items (file_path)"
        ))
        conn.commit()
        logger.info("Schema migration: confirmed ix_game_items_file_path exists")
