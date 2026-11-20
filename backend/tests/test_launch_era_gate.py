"""Tests for the era guards in service/launch/coordinator.py.

A game whose era is still "unknown" is refused with a 422 "platform not set"
before any profile is resolved, and an era with no emulator backend resolves to
a 422 instead of a bare ValueError (a 500). Apps keep era "unknown"
legitimately, so the unknown-era gate never applies to them.

Async calls are driven through asyncio.run(), no pytest-asyncio is configured.
"""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def mem_session():
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


class _FakeSettings:
    def get(self, key, default=None):
        return default

    def get_env_var(self, key):
        return ""


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch):
    import backend.core.settings as settings_mod
    monkeypatch.setattr(settings_mod, "get_settings", lambda: _FakeSettings())


def _make_unknown_era_game(db, *, with_profile):
    from backend.models.game import GameItem, GameItemBundle
    from backend.models.profile import ProfileItem

    profile_id = None
    if with_profile:
        profile = ProfileItem(name="PS2 Default", slug="ps2-default", emulator_slug="pcsx2", era="ps2")
        db.add(profile)
        db.commit()
        db.refresh(profile)
        profile_id = profile.id

    bundle = GameItemBundle(title="Ico", era="unknown", slug="ico", profile_item_id=profile_id)
    db.add(bundle)
    db.flush()
    leaf = GameItem(game_item_bundle_id=bundle.id, disc_number=1, file_path="/tmp/ico.chd")
    db.add(leaf)
    db.flush()
    bundle.launch_disk_id = leaf.id
    db.add(bundle)
    db.commit()
    db.refresh(bundle)
    return bundle, profile_id


class TestUnknownEraGameLaunch:
    def test_unknown_era_game_with_profile_is_422_platform_not_set(self, mem_session):
        from backend.service.launch.coordinator import launch_collection

        bundle, _ = _make_unknown_era_game(mem_session, with_profile=True)

        with pytest.raises(HTTPException) as exc_info:
            _run(launch_collection(bundle.id, None, mem_session))

        assert exc_info.value.status_code == 422
        assert "Platform not set" in exc_info.value.detail

    def test_unknown_era_game_with_client_chosen_profile_is_still_422(self, mem_session):
        from backend.service.launch.coordinator import launch_collection

        bundle, profile_id = _make_unknown_era_game(mem_session, with_profile=True)

        with pytest.raises(HTTPException) as exc_info:
            _run(launch_collection(bundle.id, profile_id, mem_session))

        assert exc_info.value.status_code == 422
        assert "Platform not set" in exc_info.value.detail

    def test_unknown_era_game_without_profile_reports_platform_not_set_first(self, mem_session):
        from backend.service.launch.coordinator import launch_collection

        bundle, _ = _make_unknown_era_game(mem_session, with_profile=False)

        with pytest.raises(HTTPException) as exc_info:
            _run(launch_collection(bundle.id, None, mem_session))

        assert exc_info.value.status_code == 422
        assert "Platform not set" in exc_info.value.detail


class TestRequireKnownEra:
    def test_game_with_unknown_era_is_refused(self):
        from backend.service.launch.coordinator import _require_known_era

        with pytest.raises(HTTPException) as exc_info:
            _require_known_era(SimpleNamespace(source_type="game", era="unknown"))

        assert exc_info.value.status_code == 422

    def test_app_with_unknown_era_is_not_gated(self):
        from backend.service.launch.coordinator import _require_known_era

        _require_known_era(SimpleNamespace(source_type="app", era="unknown"))

    def test_game_with_known_era_passes(self):
        from backend.service.launch.coordinator import _require_known_era

        _require_known_era(SimpleNamespace(source_type="game", era="ps2"))


class TestBackendSlugForEra:
    def test_era_without_a_backend_is_422_not_value_error(self):
        from backend.service.launch.coordinator import _backend_slug_for_era

        with pytest.raises(HTTPException) as exc_info:
            _backend_slug_for_era("unknown")

        assert exc_info.value.status_code == 422

    def test_known_era_resolves_its_backend(self):
        from backend.service.launch.coordinator import _backend_slug_for_era

        assert _backend_slug_for_era("ps2") == "pcsx2"
