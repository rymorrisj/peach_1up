from backend.core.logger import get_logger

logger = get_logger(__name__)


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
        ("library_items", "executable_path", "TEXT"),
        ("library_items", "slug", "TEXT"),
        ("library_items", "folder_path", "TEXT"),
        ("library_items", "cover_path", "TEXT"),
        ("library_items", "installed", "INTEGER NOT NULL DEFAULT 0"),
        ("platforms", "installed_at", "DATETIME"),
        ("platforms", "hardware_profile", "TEXT DEFAULT 'standard'"),
        ("platforms", "machine_override", "TEXT"),
        ("profiles", "drive_slug", "TEXT"),
        ("profiles", "use_drive", "INTEGER NOT NULL DEFAULT 1"),
        ("profiles", "container_enabled", "INTEGER"),
        ("profiles", "enable_dgvoodoo2", "INTEGER NOT NULL DEFAULT 0"),
        ("library_items", "requires_install", "INTEGER NOT NULL DEFAULT 0"),
        ("library_items", "detection_reason", "TEXT"),
        ("library_items", "file_size_bytes", "INTEGER"),
        ("users", "identity_token_secret", "TEXT"),
        ("users", "session_token_hash", "TEXT"),
        ("users", "session_token_expires_at", "DATETIME"),
        ("users", "session_token_ttl", "INTEGER"),
        ("tags", "is_system", "INTEGER NOT NULL DEFAULT 0"),
    ]
    with engine.connect() as conn:
        inspector = sa_inspect(engine)
        for table, column, col_type in pending:
            existing = {c["name"] for c in inspector.get_columns(table)}
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                conn.commit()
                logger.info("Schema migration: added %s.%s (%s)", table, column, col_type)

        # Rebuild launch_history to add target_type/platform_id and make library_item_id nullable
        if "launch_history" in inspector.get_table_names():
            lh_cols = {c["name"] for c in inspector.get_columns("launch_history")}
            if "target_type" not in lh_cols:
                conn.execute(text("""
                    CREATE TABLE launch_history_new (
                        id INTEGER PRIMARY KEY,
                        target_type TEXT NOT NULL DEFAULT 'library_item',
                        library_item_id INTEGER REFERENCES library_items(id) ON DELETE CASCADE,
                        platform_id INTEGER REFERENCES platforms(id) ON DELETE CASCADE,
                        profile_id INTEGER REFERENCES profiles(id) ON DELETE SET NULL,
                        emulator_slug TEXT NOT NULL,
                        started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        ended_at DATETIME,
                        exit_code INTEGER,
                        error_message TEXT,
                        network_blocked BOOLEAN NOT NULL DEFAULT 1,
                        job_isolated BOOLEAN NOT NULL DEFAULT 0,
                        sandboxed BOOLEAN NOT NULL DEFAULT 0,
                        sandbox_memory_limit_mb INTEGER,
                        sandbox_cpu_limit_percent INTEGER
                    )
                """))
                conn.execute(text("""
                    INSERT INTO launch_history_new (
                        id, target_type, library_item_id, platform_id, profile_id, emulator_slug,
                        started_at, ended_at, exit_code, error_message,
                        network_blocked, job_isolated, sandboxed,
                        sandbox_memory_limit_mb, sandbox_cpu_limit_percent
                    )
                    SELECT id, 'library_item', library_item_id, NULL, profile_id, emulator_slug,
                        started_at, ended_at, exit_code, error_message,
                        network_blocked, job_isolated, sandboxed,
                        sandbox_memory_limit_mb, sandbox_cpu_limit_percent
                    FROM launch_history
                """))
                conn.execute(text("DROP TABLE launch_history"))
                conn.execute(text("ALTER TABLE launch_history_new RENAME TO launch_history"))
                conn.commit()
                logger.info("Schema migration: rebuilt launch_history with target_type and platform_id")

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

        # Dedupe any pre-existing duplicate slugs, then enforce uniqueness via index.
        # Required before creating a UNIQUE index — SQLite refuses to build one
        # over data that already violates it.
        existing_indexes = {ix["name"]: ix["unique"] for ix in inspector.get_indexes("library_items")}
        if not existing_indexes.get("ix_library_items_slug"):
            dupes = conn.execute(text(
                "SELECT slug FROM library_items WHERE slug IS NOT NULL "
                "GROUP BY slug HAVING COUNT(*) > 1"
            )).fetchall()
            for (slug,) in dupes:
                rows = conn.execute(
                    text("SELECT id FROM library_items WHERE slug = :s ORDER BY id"),
                    {"s": slug},
                ).fetchall()
                n = 2
                for (item_id,) in rows[1:]:  # keep the first row's slug as-is
                    new_slug = f"{slug}-{n}"
                    while conn.execute(
                        text("SELECT 1 FROM library_items WHERE slug = :s"), {"s": new_slug}
                    ).fetchone():
                        n += 1
                        new_slug = f"{slug}-{n}"
                    conn.execute(
                        text("UPDATE library_items SET slug = :s WHERE id = :id"),
                        {"s": new_slug, "id": item_id},
                    )
                    n += 1
            if dupes:
                conn.commit()
                logger.info("Schema migration: deduplicated %d colliding slug group(s)", len(dupes))

            if "ix_library_items_slug" in existing_indexes:
                conn.execute(text("DROP INDEX ix_library_items_slug"))
            conn.execute(text(
                "CREATE UNIQUE INDEX ix_library_items_slug ON library_items (slug)"
            ))
            conn.commit()
            logger.info("Schema migration: enforced unique index on library_items.slug")
