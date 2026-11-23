import pytest

from backend.service.utils.platform_defaults import (
    defaults_for_platform,
    lookup_default_profile,
    rebind_for_platform_change,
    resolve_environment_for_launch_gate,
    resolve_environments_for_launch_gate_bulk,
    resolve_platform_defaults,
)


class TestDefaultsForPlatform:
    @pytest.mark.parametrize(
        "platform_slug,expected_emulator,expected_profile_platform",
        [
            ("dos", "dosbox-x", "dos"),
            ("win95", "86box", "win95"),
            ("win98", "86box", "win98"),
            ("winxp", "86box", "winxp"),
            ("ps1", "duckstation", "ps1"),
            ("ps2", "pcsx2", "ps2"),
            ("xbox", "xemu", "xbox"),
            ("nes", "mesen", "nes"),
            ("snes", "mesen", "snes"),
            ("n64", "project64", "n64"),
            ("dreamcast", "flycast", "dreamcast"),
        ],
    )
    def test_known_platforms(self, platform_slug, expected_emulator, expected_profile_platform):
        emulator, profile_platform = defaults_for_platform(platform_slug)
        assert emulator == expected_emulator
        assert profile_platform == expected_profile_platform

    def test_unknown_platform_returns_none_tuple(self):
        assert defaults_for_platform("unknown") == (None, None)

    def test_empty_slug_returns_none_tuple(self):
        assert defaults_for_platform("") == (None, None)

    def test_unrecognised_slug_returns_none_tuple(self):
        assert defaults_for_platform("atari2600") == (None, None)


@pytest.fixture
def db():
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


def _profile(db, platform, emulator_slug, *, bundled=True, slug=None):
    from backend.models.profile import ProfileItem

    slug = slug or f"{platform}-{'bundled' if bundled else 'user'}"
    profile = ProfileItem(
        name=slug,
        slug=slug,
        emulator_slug=emulator_slug,
        platform=platform,
        is_bundled=bundled,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def _environment(db, platform, emulator_slug, *, is_system=False, slug=None):
    from backend.models.environment import EnvironmentItem

    environment = EnvironmentItem(
        name=slug or f"{platform} env",
        slug=slug or f"{platform}-env",
        platform=platform,
        emulator_slug=emulator_slug,
        is_system=is_system,
    )
    db.add(environment)
    db.commit()
    db.refresh(environment)
    return environment


class TestLookupDefaultProfile:
    def test_returns_the_bundled_profile(self, db):
        profile = _profile(db, "dos", "dosbox-x")

        assert lookup_default_profile("dosbox-x", "dos", db) == profile.id

    def test_never_picks_a_user_profile(self, db):
        _profile(db, "dos", "dosbox-x", bundled=False)

        assert lookup_default_profile("dosbox-x", "dos", db) is None

    def test_prefers_bundled_over_an_earlier_user_profile(self, db):
        _profile(db, "dos", "dosbox-x", bundled=False)
        bundled = _profile(db, "dos", "dosbox-x")

        assert lookup_default_profile("dosbox-x", "dos", db) == bundled.id

    def test_requires_the_platform_backend_emulator(self, db):
        _profile(db, "dos", "86box")

        assert lookup_default_profile("dosbox-x", "dos", db) is None


class TestResolvePlatformDefaults:
    """resolve_platform_defaults suggests a profile only, never an Environment."""

    def test_unknown_platform_resolves_to_nothing(self, db):
        _profile(db, "ps2", "pcsx2")

        assert resolve_platform_defaults("unknown", db) is None

    def test_console_platform_gets_its_bundled_profile(self, db):
        profile = _profile(db, "ps2", "pcsx2")
        _environment(db, "ps2", "pcsx2", is_system=True)

        assert resolve_platform_defaults("ps2", db) == profile.id

    def test_pc_platform_gets_its_bundled_profile(self, db):
        profile = _profile(db, "win98", "86box")
        _environment(db, "win95", "86box", is_system=True, slug="86box")

        assert resolve_platform_defaults("win98", db) == profile.id


class TestRebindForPlatformChange:
    def test_refills_an_echoed_profile(self, db):
        old = _profile(db, "win95", "86box")
        new = _profile(db, "win98", "86box")
        fields = {"platform": "win98", "profile_item_id": old.id}

        rebind_for_platform_change(old.id, None, fields, "win98", db)

        assert fields["profile_item_id"] == new.id

    def test_keeps_an_explicitly_chosen_profile(self, db):
        old = _profile(db, "win95", "86box")
        chosen = _profile(db, "win98", "86box", bundled=False)
        _profile(db, "win98", "86box")
        fields = {"platform": "win98", "profile_item_id": chosen.id}

        rebind_for_platform_change(old.id, None, fields, "win98", db)

        assert fields["profile_item_id"] == chosen.id

    def test_pc_platform_keeps_the_environment(self, db):
        environment = _environment(db, "win95", "86box")
        fields = {"platform": "win98"}

        rebind_for_platform_change(None, environment.id, fields, "win98", db)

        assert "environment_item_id" not in fields

    def test_console_platform_clears_the_environment(self, db):
        environment = _environment(db, "win95", "86box")
        fields = {"platform": "ps1", "environment_item_id": environment.id}

        rebind_for_platform_change(None, environment.id, fields, "ps1", db)

        assert fields["environment_item_id"] is None

    def test_console_platform_clears_a_stored_environment_not_in_the_request(self, db):
        environment = _environment(db, "win95", "86box")
        fields = {"platform": "ps1"}

        rebind_for_platform_change(None, environment.id, fields, "ps1", db)

        assert fields["environment_item_id"] is None


class TestLaunchGateEnvironmentResolution:
    """No fallback: only the item's own environment_item_id ever resolves."""

    def test_no_id_resolves_to_none_even_with_a_matching_system_row(self, db):
        _environment(db, "dos", "dosbox-x", is_system=True, slug="dos")

        assert resolve_environment_for_launch_gate(None, db) is None

    def test_explicit_id_resolves_regardless_of_platform(self, db):
        environment = _environment(db, "win95", "86box")

        assert resolve_environment_for_launch_gate(environment.id, db).id == environment.id

    def test_bulk_resolves_explicit_ids_only(self, db):
        from types import SimpleNamespace

        _environment(db, "dos", "dosbox-x", is_system=True, slug="dos")
        environment = _environment(db, "win98", "86box")
        items = [
            SimpleNamespace(id=1, platform="dos", environment_item_id=None),
            SimpleNamespace(id=2, platform="win95", environment_item_id=environment.id),
        ]

        result = resolve_environments_for_launch_gate_bulk(items, db)

        assert result[1] is None
        assert result[2].id == environment.id
