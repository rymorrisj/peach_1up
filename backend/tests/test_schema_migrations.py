"""Tests for backend.core.lifespan._apply_schema_migrations.

Exercises the additive ALTER TABLE ADD COLUMN pattern in isolation against a
throwaway SQLite file, without touching the real configured database.
"""


def test_migrations_idempotent_against_already_migrated_db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel
    import backend.models  # noqa: F401 — registers all table models with SQLModel.metadata

    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    # create_all() builds every table per the *current* model definitions, so
    # the new users.identity_token_secret / session_token_hash /
    # session_token_expires_at / session_token_ttl columns already exist —
    # exactly the "DB with the new columns already present" scenario.
    SQLModel.metadata.create_all(engine)

    import backend.core.database as database_mod
    monkeypatch.setattr(database_mod, "get_engine", lambda: engine)

    from backend.core.lifespan import _apply_schema_migrations

    _apply_schema_migrations()
    _apply_schema_migrations()  # second run must be a no-op, not raise


def test_migrations_add_missing_user_columns_to_legacy_db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, inspect as sa_inspect, text
    from sqlmodel import SQLModel
    import backend.models  # noqa: F401 — registers all table models with SQLModel.metadata

    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")
    # Build every table in its current shape, then roll just `users` back to
    # a pre-migration shape — simulates upgrading a real, populated DB where
    # every other table is already current and only users lacks the new columns.
    SQLModel.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE users"))
        conn.execute(text(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, is_owner BOOLEAN, "
            "pin_required BOOLEAN, can_launch_media BOOLEAN, can_edit_platforms BOOLEAN, "
            "can_edit_library BOOLEAN, can_manage_profiles BOOLEAN, can_edit_settings BOOLEAN, "
            "is_admin BOOLEAN, max_content_rating TEXT, block_unrated_media BOOLEAN, "
            "is_locked BOOLEAN, failed_pin_attempts INTEGER, pin_hash TEXT, "
            "created_at DATETIME, updated_at DATETIME"
            ")"
        ))
        conn.commit()

    import backend.core.database as database_mod
    monkeypatch.setattr(database_mod, "get_engine", lambda: engine)

    from backend.core.lifespan import _apply_schema_migrations

    _apply_schema_migrations()

    columns = {c["name"] for c in sa_inspect(engine).get_columns("users")}
    assert "identity_token_secret" in columns
    assert "session_token_hash" in columns
    assert "session_token_expires_at" in columns
    assert "session_token_ttl" in columns

    # Re-running against the now-migrated legacy DB must also be a no-op.
    _apply_schema_migrations()
