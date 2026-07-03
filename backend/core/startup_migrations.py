from backend.core.logger import get_logger

logger = get_logger(__name__)


def _apply_schema_migrations() -> None:
    """Add columns and apply schema changes introduced after initial creation.

    Safe to run on every startup — all operations are idempotent.
    """
    from backend.core.database import get_engine
    from sqlalchemy import inspect as sa_inspect, text

    engine = get_engine()
    # Idempotent ADD COLUMN catch-ups for non-library tables. The library schema
    # (library_collections / library_items leaf / launch_history / media_restrictions)
    # is created directly by create_tables() in its consolidated shape — there is no
    # legacy library DB to migrate, so no library data-reshape steps live here.
    pending: list[tuple[str, str, str]] = [
        ("platforms", "installed_at", "DATETIME"),
        ("platforms", "hardware_profile", "TEXT DEFAULT 'standard'"),
        ("platforms", "machine_override", "TEXT"),
        ("profiles", "use_drive", "INTEGER NOT NULL DEFAULT 1"),
        ("profiles", "container_enabled", "INTEGER"),
        ("profiles", "enable_dgvoodoo2", "INTEGER NOT NULL DEFAULT 0"),
        ("users", "identity_token_secret", "TEXT"),
        ("users", "session_token_hash", "TEXT"),
        ("users", "session_token_expires_at", "DATETIME"),
        ("users", "session_token_ttl", "INTEGER"),
        ("tags", "is_system", "INTEGER NOT NULL DEFAULT 0"),
        ("users", "can_manage_users", "INTEGER NOT NULL DEFAULT 0"),
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
        users_indexes = {ix["name"] for ix in inspector.get_indexes("users")}
        if "idx_single_owner" not in users_indexes:
            owner_count = conn.execute(
                text("SELECT COUNT(*) FROM users WHERE is_owner = 1")
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
                "CREATE UNIQUE INDEX idx_single_owner ON users (is_owner) WHERE is_owner = 1"
            ))
            conn.commit()
            logger.info("Schema migration: enforced single-owner partial unique index on users")
