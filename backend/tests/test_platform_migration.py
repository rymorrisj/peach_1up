"""Tests for the era to platform startup migration in
backend/core/startup_migrations.py: column renames and the supported_eras
drop, the SQLite capability guard, and the Environment row cleanup.

A legacy DB is built by seeding rows through the current models, then
renaming the columns back to their old names, so the data is realistic.
"""

from types import SimpleNamespace

import pytest

_LEGACY_RENAMES = (
    ("game_item_bundles", "platform", "era"),
    ("game_item_bundles", "platform_confirmed", "era_confirmed"),
    ("app_item_bundles", "platform", "era"),
    ("environment_items", "platform", "era"),
    ("profile_items", "platform", "era"),
)


def _columns(engine, table):
    from sqlalchemy import inspect as sa_inspect

    return {c["name"] for c in sa_inspect(engine).get_columns(table)}


@pytest.fixture
def legacy_db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, text
    from sqlmodel import Session, SQLModel
    import backend.models  # noqa: F401, registers all table models with SQLModel.metadata
    from backend.models import EnvironmentItem, LaunchHistory, ProfileItem
    from backend.models.app import AppItemBundle
    from backend.models.game import GameItemBundle

    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    SQLModel.metadata.create_all(engine)

    ids = {}
    with Session(engine) as db:
        profile = ProfileItem(
            name="DOS Default",
            slug="dos-default",
            platform="dos",
            emulator_slug="dosbox-x",
            is_bundled=True,
        )
        db.add(profile)
        db.flush()
        envs = {
            "dos": EnvironmentItem(
                name="DOS",
                slug="dos",
                platform="dos",
                emulator_slug="dosbox-x",
                is_system=True,
                profile_item_id=profile.id,
            ),
            "86box": EnvironmentItem(
                name="86Box", slug="86box", platform="win95", emulator_slug="86box", is_system=True
            ),
            "duckstation": EnvironmentItem(
                name="DuckStation",
                slug="duckstation",
                platform="ps1",
                emulator_slug="duckstation",
                is_system=True,
            ),
            "pcsx2": EnvironmentItem(name="PCSX2", slug="pcsx2", platform="ps2", emulator_slug="pcsx2", is_system=True),
            "user": EnvironmentItem(name="My Win98", slug="my-win98", platform="win98", emulator_slug="86box"),
        }
        for env in envs.values():
            db.add(env)
        db.flush()
        ids.update({f"env_{k}": v.id for k, v in envs.items()})

        games = {
            "dos": GameItemBundle(title="Doom", slug="doom", platform="dos", environment_item_id=envs["dos"].id),
            "win98_86box": GameItemBundle(
                title="Myst",
                slug="myst",
                platform="win98",
                environment_item_id=envs["86box"].id,
            ),
            "ps1": GameItemBundle(title="Ico", slug="ico", platform="ps1", environment_item_id=envs["user"].id),
            "win98_user": GameItemBundle(
                title="Riven",
                slug="riven",
                platform="win98",
                platform_confirmed=True,
                environment_item_id=envs["user"].id,
            ),
        }
        for game in games.values():
            db.add(game)
        app_bundle = AppItemBundle(title="Tool", slug="tool", platform="ps1", environment_item_id=envs["user"].id)
        db.add(app_bundle)
        db.flush()
        ids.update({f"game_{k}": v.id for k, v in games.items()})
        ids["app"] = app_bundle.id
        db.add(LaunchHistory(environment_item_id=envs["pcsx2"].id, emulator_slug="pcsx2"))
        db.commit()

    with engine.connect() as conn:
        for table, new, old in _LEGACY_RENAMES:
            conn.execute(text(f"ALTER TABLE {table} RENAME COLUMN {new} TO {old}"))
        conn.execute(text("ALTER TABLE environment_items ADD COLUMN supported_eras TEXT"))
        conn.execute(text("UPDATE environment_items SET supported_eras = '[\"win95\"]' WHERE slug = '86box'"))
        conn.commit()

    import backend.core.database as database_mod

    monkeypatch.setattr(database_mod, "get_engine", lambda: engine)
    return engine, ids


def _snapshot(engine):
    from sqlalchemy import text

    with engine.connect() as conn:
        return {
            "games": conn.execute(
                text("SELECT id, platform, platform_confirmed, environment_item_id FROM game_item_bundles ORDER BY id")
            ).fetchall(),
            "apps": conn.execute(text("SELECT id, platform, environment_item_id FROM app_item_bundles")).fetchall(),
            "envs": conn.execute(
                text("SELECT id, slug, platform, is_system FROM environment_items ORDER BY id")
            ).fetchall(),
            "profiles": conn.execute(text("SELECT slug, platform FROM profile_items")).fetchall(),
            "launches": conn.execute(text("SELECT environment_item_id FROM launch_history")).fetchall(),
        }


def test_renames_columns_and_drops_supported_eras(legacy_db):
    from backend.core.startup_migrations import _apply_schema_migrations

    engine, _ = legacy_db
    _apply_schema_migrations()

    for table, new, old in _LEGACY_RENAMES:
        columns = _columns(engine, table)
        assert new in columns
        assert old not in columns
    assert "supported_eras" not in _columns(engine, "environment_items")


def test_stored_values_are_preserved(legacy_db):
    from backend.core.startup_migrations import _apply_schema_migrations

    engine, ids = legacy_db
    _apply_schema_migrations()
    snap = _snapshot(engine)

    platforms = {row.id: row.platform for row in snap["games"]}
    assert platforms == {
        ids["game_dos"]: "dos",
        ids["game_win98_86box"]: "win98",
        ids["game_ps1"]: "ps1",
        ids["game_win98_user"]: "win98",
    }
    confirmed = {row.id: bool(row.platform_confirmed) for row in snap["games"]}
    assert confirmed[ids["game_win98_user"]] is True
    assert confirmed[ids["game_dos"]] is False
    assert snap["profiles"] == [("dos-default", "dos")]
    assert snap["apps"][0].platform == "ps1"


def test_environment_links_and_retired_rows(legacy_db):
    from backend.core.startup_migrations import _apply_schema_migrations

    engine, ids = legacy_db
    _apply_schema_migrations()
    snap = _snapshot(engine)

    links = {row.id: row.environment_item_id for row in snap["games"]}
    assert links[ids["game_dos"]] == ids["env_dos"]
    assert links[ids["game_win98_86box"]] is None
    assert links[ids["game_ps1"]] is None
    assert links[ids["game_win98_user"]] == ids["env_user"]
    assert snap["apps"][0].environment_item_id is None

    envs = {row.slug: row for row in snap["envs"]}
    assert envs["dos"].is_system == 0
    assert envs["dos"].platform == "dos"
    assert "86box" not in envs
    assert "duckstation" not in envs
    # Still referenced by launch history: kept, and its history survives.
    assert "pcsx2" in envs
    assert snap["launches"] == [(ids["env_pcsx2"],)]
    assert "my-win98" in envs


def test_migration_is_idempotent(legacy_db):
    from backend.core.startup_migrations import _apply_schema_migrations

    engine, _ = legacy_db
    _apply_schema_migrations()
    first = _snapshot(engine)
    _apply_schema_migrations()

    assert _snapshot(engine) == first


def test_fresh_db_is_a_no_op(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel
    import backend.models  # noqa: F401
    import backend.core.database as database_mod
    from backend.core.startup_migrations import _apply_schema_migrations

    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database_mod, "get_engine", lambda: engine)

    _apply_schema_migrations()
    _apply_schema_migrations()

    assert "platform" in _columns(engine, "game_item_bundles")


@pytest.mark.parametrize("version,expected", [((3, 24, 0), "rename"), ((3, 30, 0), "drop")])
def test_old_sqlite_fails_loudly_without_touching_the_db(legacy_db, monkeypatch, version, expected):
    import backend.core.startup_migrations as migrations_mod

    engine, _ = legacy_db
    fake = SimpleNamespace(sqlite_version_info=version, sqlite_version=".".join(map(str, version)))
    monkeypatch.setattr(migrations_mod, "sqlite3", fake)

    with pytest.raises(RuntimeError, match=expected):
        migrations_mod._apply_schema_migrations()

    assert "era" in _columns(engine, "game_item_bundles")
    assert "supported_eras" in _columns(engine, "environment_items")


def test_both_columns_present_is_logged_and_left_alone(legacy_db, caplog):
    from sqlalchemy import text
    from backend.core.startup_migrations import _apply_schema_migrations

    engine, _ = legacy_db
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE profile_items ADD COLUMN platform VARCHAR"))
        conn.commit()

    _apply_schema_migrations()

    columns = _columns(engine, "profile_items")
    assert {"era", "platform"} <= columns
    assert any("both era and platform" in r.getMessage() for r in caplog.records)


class TestRemoveStaleErasConfig:
    def _paths(self, tmp_path, monkeypatch):
        import backend.service.utils.platforms_config as config_mod

        platforms = tmp_path / "platforms.yaml"
        eras = tmp_path / "eras.yaml"
        monkeypatch.setattr(config_mod, "_PLATFORMS_PATH", platforms)
        monkeypatch.setattr(config_mod, "_STALE_ERAS_PATH", eras)
        return config_mod, platforms, eras

    def test_deletes_eras_yaml_when_platforms_yaml_exists(self, tmp_path, monkeypatch):
        config_mod, platforms, eras = self._paths(tmp_path, monkeypatch)
        platforms.write_text("dos: {}\n")
        eras.write_text("dos: {}\n")

        config_mod.remove_stale_eras_config()

        assert not eras.exists()
        assert platforms.exists()

    def test_keeps_eras_yaml_when_platforms_yaml_is_missing(self, tmp_path, monkeypatch):
        config_mod, _, eras = self._paths(tmp_path, monkeypatch)
        eras.write_text("dos: {}\n")

        config_mod.remove_stale_eras_config()

        assert eras.exists()
