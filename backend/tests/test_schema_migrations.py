"""Tests for backend.core.startup_migrations._apply_schema_migrations.

Exercises the additive ALTER TABLE ADD COLUMN pattern in isolation against a
throwaway SQLite file, without touching the real configured database.
"""


def test_migrations_idempotent_against_already_migrated_db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel
    import backend.models  # noqa: F401, registers all table models with SQLModel.metadata

    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    # create_all() builds every table per the *current* model definitions, so
    # the new user_items.identity_token_secret / session_token_hash /
    # session_token_expires_at / session_token_ttl columns already exist —
    # exactly the "DB with the new columns already present" scenario.
    SQLModel.metadata.create_all(engine)

    import backend.core.database as database_mod
    monkeypatch.setattr(database_mod, "get_engine", lambda: engine)

    from backend.core.startup_migrations import _apply_schema_migrations

    _apply_schema_migrations()
    _apply_schema_migrations()  # second run must be a no-op, not raise


def test_migrations_add_missing_user_columns_to_legacy_db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, inspect as sa_inspect, text
    from sqlmodel import SQLModel
    import backend.models  # noqa: F401, registers all table models with SQLModel.metadata

    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")
    # Build every table in its current shape, then roll just `user_items` back to
    # a pre-migration shape, simulates upgrading a real, populated DB where
    # every other table is already current and only user_items lacks the new columns.
    SQLModel.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE user_items"))
        conn.execute(text(
            "CREATE TABLE user_items ("
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

    from backend.core.startup_migrations import _apply_schema_migrations

    _apply_schema_migrations()

    columns = {c["name"] for c in sa_inspect(engine).get_columns("user_items")}
    assert "identity_token_secret" in columns
    assert "session_token_hash" in columns
    assert "session_token_expires_at" in columns
    assert "session_token_ttl" in columns

    # Re-running against the now-migrated legacy DB must also be a no-op.
    _apply_schema_migrations()


def test_migrations_add_media_bundle_content_rating_and_its_index(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, inspect as sa_inspect, text
    from sqlmodel import SQLModel
    import backend.models  # noqa: F401, registers all table models with SQLModel.metadata

    engine = create_engine(f"sqlite:///{tmp_path / 'pre_rating.db'}")
    # Current shape minus media_item_bundles.content_rating and its index:
    # a DB provisioned before the media rating inheritance batch.
    SQLModel.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.execute(text("DROP INDEX ix_media_item_bundles_content_rating"))
        conn.execute(text("ALTER TABLE media_item_bundles DROP COLUMN content_rating"))
        conn.commit()

    import backend.core.database as database_mod
    monkeypatch.setattr(database_mod, "get_engine", lambda: engine)

    from backend.core.startup_migrations import _apply_schema_migrations

    _apply_schema_migrations()
    _apply_schema_migrations()  # idempotent: second run adds nothing and does not raise

    inspector = sa_inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("media_item_bundles")}
    assert "content_rating" in columns
    assert columns["content_rating"]["nullable"] is True
    index_names = {ix["name"] for ix in inspector.get_indexes("media_item_bundles")}
    assert "ix_media_item_bundles_content_rating" in index_names
    with engine.connect() as conn:
        count = conn.execute(text(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'index' "
            "AND name = 'ix_media_item_bundles_content_rating'"
        )).scalar()
    assert count == 1


def test_migrations_add_media_item_asset_columns_and_old_rows_stay_null(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, inspect as sa_inspect, text
    from sqlmodel import SQLModel
    import backend.models  # noqa: F401, registers all table models with SQLModel.metadata

    engine = create_engine(f"sqlite:///{tmp_path / 'pre_assets.db'}")
    # Current shape minus media_items.asset_type/source_url, with one row
    # written before the columns existed.
    SQLModel.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE media_items DROP COLUMN asset_type"))
        conn.execute(text("ALTER TABLE media_items DROP COLUMN source_url"))
        conn.execute(text(
            "INSERT INTO media_items (id, title, media_kind, file_path, sort_index) "
            "VALUES (1, 'Old', 'image', '/library/media/old.jpg', 0)"
        ))
        conn.commit()
    other_tables_before = {
        t: [c["name"] for c in sa_inspect(engine).get_columns(t)]
        for t in ("media_item_bundles", "game_items", "game_item_bundles")
    }

    import backend.core.database as database_mod
    monkeypatch.setattr(database_mod, "get_engine", lambda: engine)

    from backend.core.startup_migrations import _apply_schema_migrations

    _apply_schema_migrations()
    _apply_schema_migrations()  # idempotent: second run adds nothing and does not raise

    inspector = sa_inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("media_items")}
    assert columns["asset_type"]["nullable"] is True
    assert columns["source_url"]["nullable"] is True
    assert [c["name"] for c in inspector.get_columns("media_items")].count("source_url") == 1
    with engine.connect() as conn:
        row = conn.execute(text("SELECT asset_type, source_url FROM media_items WHERE id = 1")).one()
    assert tuple(row) == (None, None)
    for table, names in other_tables_before.items():
        assert [c["name"] for c in inspector.get_columns(table)] == names
