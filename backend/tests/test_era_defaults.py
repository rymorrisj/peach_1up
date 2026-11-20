from unittest.mock import MagicMock

import pytest

from backend.service.utils.era_defaults import defaults_for_era, lookup_environment_and_profile


class TestDefaultsForEra:
    @pytest.mark.parametrize("era_slug,expected_emulator,expected_profile_era", [
        ("dos",       "dosbox-x",    "dos"),
        ("win95",     "86box",       "win95"),
        ("win98",     "86box",       "win98"),
        ("winxp",     "86box",       "winxp"),
        ("ps1",       "duckstation", "ps1"),
        ("ps2",       "pcsx2",       "ps2"),
        ("xbox",      "xemu",        "xbox"),
        ("nes",       "mesen",       "nes"),
        ("snes",      "mesen",       "snes"),
        ("n64",       "project64",   "n64"),
        ("dreamcast", "flycast",     "dreamcast"),
    ])
    def test_known_eras(self, era_slug, expected_emulator, expected_profile_era):
        emulator, profile_era = defaults_for_era(era_slug)
        assert emulator == expected_emulator
        assert profile_era == expected_profile_era

    def test_unknown_era_returns_none_tuple(self):
        assert defaults_for_era("unknown") == (None, None)

    def test_empty_slug_returns_none_tuple(self):
        assert defaults_for_era("") == (None, None)

    def test_unrecognised_slug_returns_none_tuple(self):
        assert defaults_for_era("atari2600") == (None, None)


class TestLookupPlatformAndProfile:
    def _make_db(self, platform_id=None, profile_item_id=None):
        platform = MagicMock()
        platform.id = platform_id

        profile = MagicMock()
        profile.id = profile_item_id

        db = MagicMock()
        db.query.return_value.filter.return_value.first.side_effect = [
            platform if platform_id is not None else None,
            profile if profile_item_id is not None else None,
        ]
        return db

    def test_returns_ids_when_both_found(self):
        db = self._make_db(platform_id=3, profile_item_id=7)
        pid, rid = lookup_environment_and_profile("dosbox-x", "dos", db)
        assert pid == 3
        assert rid == 7

    def test_returns_none_when_platform_missing(self):
        platform = None
        profile = MagicMock()
        profile.id = 7
        db = MagicMock()
        db.query.return_value.filter.return_value.first.side_effect = [platform, profile]
        pid, rid = lookup_environment_and_profile("dosbox-x", "dos", db)
        assert pid is None
        assert rid == 7

    def test_returns_none_when_profile_missing(self):
        platform = MagicMock()
        platform.id = 3
        db = MagicMock()
        db.query.return_value.filter.return_value.first.side_effect = [platform, None]
        pid, rid = lookup_environment_and_profile("dosbox-x", "dos", db)
        assert pid == 3
        assert rid is None

    def test_returns_none_tuple_when_both_missing(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.side_effect = [None, None]
        pid, rid = lookup_environment_and_profile("dosbox-x", "dos", db)
        assert pid is None
        assert rid is None


class TestResolveEraDefaults:
    """resolve_era_defaults against a real in-memory DB, the refill used when an
    existing bundle's era is corrected."""

    @pytest.fixture
    def db(self):
        from sqlalchemy.pool import StaticPool
        from sqlmodel import SQLModel, Session, create_engine
        import backend.models  # noqa: F401, registers all table models with SQLModel.metadata

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            yield session

    def _profile(self, db, era, emulator_slug):
        from backend.models.profile import ProfileItem

        profile = ProfileItem(
            name=f"{era} profile", slug=f"{era}-profile", emulator_slug=emulator_slug, era=era,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile

    def _system_environment(self, db, era, emulator_slug):
        from backend.models.environment import EnvironmentItem

        environment = EnvironmentItem(
            name=f"{era} env", slug=f"{era}-env", era=era, emulator_slug=emulator_slug, is_system=True,
        )
        db.add(environment)
        db.commit()
        db.refresh(environment)
        return environment

    def test_unknown_era_resolves_to_nothing(self, db):
        from backend.service.utils.era_defaults import resolve_era_defaults

        self._profile(db, "ps2", "pcsx2")

        assert resolve_era_defaults("unknown", db) == (None, None)

    def test_console_era_gets_profile_and_never_an_environment(self, db):
        from backend.service.utils.era_defaults import resolve_era_defaults

        profile = self._profile(db, "ps2", "pcsx2")
        # A seeded system Environment for the console's emulator must not leak in.
        self._system_environment(db, "ps2", "pcsx2")

        assert resolve_era_defaults("ps2", db) == (None, profile.id)

    def test_pc_era_gets_era_matched_environment_and_profile(self, db):
        from backend.service.utils.era_defaults import resolve_era_defaults

        profile = self._profile(db, "dos", "dosbox-x")
        environment = self._system_environment(db, "dos", "dosbox-x")

        assert resolve_era_defaults("dos", db) == (environment.id, profile.id)

    def test_86box_era_never_binds_another_eras_environment(self, db):
        from backend.service.utils.era_defaults import resolve_era_defaults

        # Mirrors the seed: a single 86Box system row with era win95.
        self._system_environment(db, "win95", "86box")
        profile = self._profile(db, "win98", "86box")

        assert resolve_era_defaults("win98", db) == (None, profile.id)
