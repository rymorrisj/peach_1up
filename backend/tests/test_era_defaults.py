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
    def _make_db(self, platform_id=None, profile_id=None):
        platform = MagicMock()
        platform.id = platform_id

        profile = MagicMock()
        profile.id = profile_id

        db = MagicMock()
        db.query.return_value.filter.return_value.first.side_effect = [
            platform if platform_id is not None else None,
            profile if profile_id is not None else None,
        ]
        return db

    def test_returns_ids_when_both_found(self):
        db = self._make_db(platform_id=3, profile_id=7)
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
