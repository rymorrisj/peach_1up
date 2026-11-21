"""Route-level (TestClient/HTTP) tests for backend/api/routes/game_metadata.py.

Scoped to the routes themselves, the is_owner gate and the
rating_change_requires_confirmation wiring (backend/core/dependencies.py);
test_enrich.py drives enrich_entity() directly. Covers:

    - is_owner gating (403 for non-owner) on all four routes
      (/metadata-search, /metadata-details, /enrich, /{id}/accept-metadata-assets)
    - a content_rating change that lowers an already-set rating 409s without
      confirm_rating_change, and succeeds (rating actually updated) with it
    - a content_rating change that does not lower the rating (same value, or
      moving off an unset rating) needs no confirmation at all
    - the metadata_fetch_enabled owner toggle: all four routes refuse with
      403 and the stable "disabled" detail while it is off, the permission
      403 still wins for a non-owner, and the routes run normally when on

In-memory SQLModel SQLite + StaticPool + get_active_user/get_db dependency
overrides, as in the other *_routes test files. No settings stub is needed:
_load_rating_ordinals falls back to the built-in defaults on the RuntimeError
this app raises before init_settings() runs.
"""

import pytest


@pytest.fixture
def mem_db_session():
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


def _make_user(db, **overrides):
    from backend.models.user import UserItem

    kwargs = dict(name="UserItem", is_owner=False, is_admin=False)
    kwargs.update(overrides)
    user = UserItem(**kwargs)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_game_bundle(db, **overrides):
    from backend.models.game import GameItemBundle

    kwargs = dict(title="Doom", file_path="/library/games/dos/doom", era="dos", slug="doom")
    kwargs.update(overrides)
    bundle = GameItemBundle(**kwargs)
    db.add(bundle)
    db.commit()
    db.refresh(bundle)
    return bundle


@pytest.fixture
def http_client(mem_db_session):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import game_metadata
    from backend.core.database import get_db

    app = FastAPI()
    app.include_router(game_metadata.router)
    app.dependency_overrides[get_db] = lambda: mem_db_session

    with TestClient(app) as c:
        yield c, mem_db_session, app


def _set_active_user(app, user):
    from backend.core.dependencies import get_active_user

    app.dependency_overrides[get_active_user] = lambda: user


@pytest.fixture
def metadata_fetch_enabled(monkeypatch):
    """Turn the owner's metadata_fetch_enabled toggle on for one test. The
    routes resolve is_metadata_fetch_enabled from the package at call time."""
    import backend.service.metadata_providers as providers_mod

    monkeypatch.setattr(providers_mod, "is_metadata_fetch_enabled", lambda: True)


@pytest.fixture
def metadata_fetch_disabled(monkeypatch):
    import backend.service.metadata_providers as providers_mod

    monkeypatch.setattr(providers_mod, "is_metadata_fetch_enabled", lambda: False)


# ---------------------------------------------------------------------------
# is_owner gate
# ---------------------------------------------------------------------------


class TestIsOwnerGate:
    def test_metadata_search_403_for_non_owner(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db))

        resp = c.get("/api/v1/game-items/metadata-search", params={"name": "Doom"})

        assert resp.status_code == 403, resp.text

    def test_metadata_details_403_for_non_owner(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db))

        resp = c.get("/api/v1/game-items/metadata-details", params={"game_id": 1})

        assert resp.status_code == 403, resp.text

    def test_enrich_403_for_non_owner(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db)
        _set_active_user(app, _make_user(db))

        resp = c.post(
            "/api/v1/game-items/enrich",
            json={"entity_type": "game_item_bundle", "entity_id": bundle.id, "title": "New Title"},
        )

        assert resp.status_code == 403, resp.text

    def test_accept_metadata_assets_403_for_non_owner(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db)
        _set_active_user(app, _make_user(db))

        resp = c.post(
            f"/api/v1/game-items/{bundle.id}/accept-metadata-assets",
            json={"assets": []},
        )

        assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# rating_change_requires_confirmation wiring on POST /enrich
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("metadata_fetch_enabled")
class TestRatingChangeConfirmation:
    def test_lowering_rating_without_confirm_returns_409(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db, content_rating="M")
        _set_active_user(app, _make_user(db, is_owner=True))

        resp = c.post(
            "/api/v1/game-items/enrich",
            json={"entity_type": "game_item_bundle", "entity_id": bundle.id, "content_rating": "E"},
        )

        assert resp.status_code == 409, resp.text
        db.refresh(bundle)
        assert bundle.content_rating == "M"

    def test_lowering_rating_with_confirm_succeeds_and_persists(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db, content_rating="M")
        _set_active_user(app, _make_user(db, is_owner=True))

        resp = c.post(
            "/api/v1/game-items/enrich",
            json={
                "entity_type": "game_item_bundle",
                "entity_id": bundle.id,
                "content_rating": "E",
                "confirm_rating_change": True,
            },
        )

        assert resp.status_code == 200, resp.text
        db.refresh(bundle)
        assert bundle.content_rating == "E"

    def test_same_rating_needs_no_confirmation(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db, content_rating="M")
        _set_active_user(app, _make_user(db, is_owner=True))

        resp = c.post(
            "/api/v1/game-items/enrich",
            json={"entity_type": "game_item_bundle", "entity_id": bundle.id, "content_rating": "M"},
        )

        assert resp.status_code == 200, resp.text

    def test_setting_rating_from_unset_needs_no_confirmation(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db, content_rating=None)
        _set_active_user(app, _make_user(db, is_owner=True))

        resp = c.post(
            "/api/v1/game-items/enrich",
            json={"entity_type": "game_item_bundle", "entity_id": bundle.id, "content_rating": "M"},
        )

        assert resp.status_code == 200, resp.text
        db.refresh(bundle)
        assert bundle.content_rating == "M"


# ---------------------------------------------------------------------------
# Accept All asset type allowlist (META-3) and per-asset unique stems (META-1)
# ---------------------------------------------------------------------------


class TestAcceptMetadataAssetsTypeAllowlist:
    @pytest.mark.parametrize("asset_type", [
        "..\\..\\evil",
        "../../evil",
        "C:\\Windows\\evil",
        "\\\\attacker\\share\\evil",
        "boxart_front.html",
        "",
        "Cover",
    ])
    def test_unlisted_asset_type_is_422_and_nothing_is_downloaded(self, http_client, monkeypatch, asset_type):
        import backend.service.games.media_link as media_link_mod

        c, db, app = http_client
        bundle = _make_game_bundle(db)
        _set_active_user(app, _make_user(db, is_owner=True))
        called = []
        monkeypatch.setattr(
            media_link_mod, "create_linked_media_from_metadata", lambda *a, **k: called.append(a),
        )

        resp = c.post(
            f"/api/v1/game-items/{bundle.id}/accept-metadata-assets",
            json={"assets": [{"url": "https://cdn.thegamesdb.net/images/original/x.jpg", "type": asset_type}]},
        )

        assert resp.status_code == 422, resp.text
        assert called == []

    def test_route_literal_matches_provider_asset_types(self):
        """The route body's allowlist is derived from the provider package,
        not a second hand-maintained copy."""
        from typing import get_args

        from backend.api.routes.game_metadata import MetadataAssetBody
        from backend.service.metadata_providers import ASSET_TYPES

        assert set(get_args(MetadataAssetBody.model_fields["type"].annotation)) == ASSET_TYPES


class TestAssetFilenameStem:
    def test_stems_are_unique_per_index(self):
        from backend.service.games.media_link import asset_filename_stem

        stems = [asset_filename_stem("screenshot", i) for i in range(10)]
        assert len(set(stems)) == 10
        assert stems[0] == "screenshot-0"

    @pytest.mark.parametrize("asset_type,expected", [
        ("boxart_front", "boxart_front-3"),
        ("..\\..\\evil", "evil-3"),
        ("../../evil", "evil-3"),
        ("\\\\attacker\\share\\evil", "evil-3"),
        ("", "asset-3"),
    ])
    def test_stem_is_a_safe_basename(self, asset_type, expected):
        from backend.service.games.media_link import asset_filename_stem

        stem = asset_filename_stem(asset_type, 3)
        assert stem == expected
        assert "/" not in stem and "\\" not in stem and ".." not in stem

    def test_accept_all_passes_distinct_stems(self, mem_db_session, tmp_path, monkeypatch):
        """Ten same-type assets produce ten distinct download stems (no
        overwrite of one screenshot.jpg)."""
        import backend.core.settings as core_settings
        import backend.service.utils.asset_fetch as asset_fetch_mod
        from backend.service.games.media_link import create_linked_media_from_metadata
        from backend.service.metadata_providers import MetadataAsset

        class _S:
            def get_env_var(self, key):
                return str(tmp_path / "media") if key == "MEDIA_PATH" else ""

        monkeypatch.setattr(core_settings, "get_settings", lambda: _S())
        seen: list[str] = []

        def _fake_download(url, dest_dir, *, filename_stem, **kwargs):
            seen.append(filename_stem)
            return dest_dir / f"{filename_stem}.jpg"

        monkeypatch.setattr(asset_fetch_mod, "download_remote_image", _fake_download)
        bundle = _make_game_bundle(mem_db_session)
        assets = [
            MetadataAsset(url=f"https://cdn.thegamesdb.net/images/original/s{i}.jpg", type="screenshot")
            for i in range(10)
        ]

        create_linked_media_from_metadata(bundle.id, assets, mem_db_session)

        assert len(set(seen)) == 10


class TestTheGamesDBAssetTypeFilter:
    def test_label_outside_allowlist_is_not_offered(self):
        from backend.service.metadata_providers import ASSET_TYPES
        from backend.service.metadata_providers.thegamesdb_provider import _asset_type_label

        assert _asset_type_label({"type": "boxart", "side": "front"}) in ASSET_TYPES
        assert _asset_type_label({"type": "screenshot"}) in ASSET_TYPES
        assert _asset_type_label({"type": "../evil", "side": "x"}) not in ASSET_TYPES


# ---------------------------------------------------------------------------
# metadata_fetch_enabled owner toggle, enforced server-side on all four routes
# ---------------------------------------------------------------------------

_DISABLED_DETAIL = "Metadata fetching is disabled in Settings"


def _call_route(c, route, bundle_id):
    if route == "search":
        return c.get("/api/v1/game-items/metadata-search", params={"name": "Doom"})
    if route == "details":
        return c.get("/api/v1/game-items/metadata-details", params={"game_id": 1})
    if route == "enrich":
        return c.post(
            "/api/v1/game-items/enrich",
            json={"entity_type": "game_item_bundle", "entity_id": bundle_id, "title": "New Title"},
        )
    return c.post(f"/api/v1/game-items/{bundle_id}/accept-metadata-assets", json={"assets": []})


_ROUTES = ["search", "details", "enrich", "accept"]


class TestMetadataFetchToggle:
    def test_is_metadata_fetch_enabled_fails_closed_before_settings_init(self, monkeypatch):
        import backend.service.utils.settings as settings_mod
        from backend.service.metadata_providers import is_metadata_fetch_enabled

        monkeypatch.setattr(settings_mod, "_state", None)

        assert is_metadata_fetch_enabled() is False

    def test_is_metadata_fetch_enabled_defaults_to_false(self, monkeypatch):
        import backend.service.utils.settings as settings_mod
        from backend.service.metadata_providers import is_metadata_fetch_enabled

        assert settings_mod._DEFAULTS["metadata_fetch_enabled"] is False
        monkeypatch.setattr(settings_mod, "_state", dict(settings_mod._DEFAULTS))

        assert is_metadata_fetch_enabled() is False

    def test_is_metadata_fetch_enabled_true_for_stored_true(self, monkeypatch):
        import backend.service.utils.settings as settings_mod
        from backend.service.metadata_providers import is_metadata_fetch_enabled

        monkeypatch.setattr(settings_mod, "_state", {"metadata_fetch_enabled": True})

        assert is_metadata_fetch_enabled() is True

    @pytest.mark.parametrize("stored", ["true", 1, "1", None])
    def test_is_metadata_fetch_enabled_rejects_non_bool_values(self, monkeypatch, stored):
        import backend.service.utils.settings as settings_mod
        from backend.service.metadata_providers import is_metadata_fetch_enabled

        monkeypatch.setattr(settings_mod, "_state", {"metadata_fetch_enabled": stored})

        assert is_metadata_fetch_enabled() is False

    @pytest.mark.usefixtures("metadata_fetch_disabled")
    @pytest.mark.parametrize("route", _ROUTES)
    def test_route_refuses_when_disabled(self, http_client, monkeypatch, route):
        import backend.service.games.enrich as enrich_mod
        import backend.service.games.media_link as media_link_mod
        import backend.service.metadata_providers as providers_mod

        c, db, app = http_client
        bundle = _make_game_bundle(db, content_rating="M")
        _set_active_user(app, _make_user(db, is_owner=True))
        reached = []
        monkeypatch.setattr(providers_mod, "get_active_provider", lambda: reached.append("provider"))
        monkeypatch.setattr(enrich_mod, "enrich_entity", lambda *a, **k: reached.append("enrich"))
        monkeypatch.setattr(
            media_link_mod, "create_linked_media_from_metadata", lambda *a, **k: reached.append("accept"),
        )

        resp = _call_route(c, route, bundle.id)

        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == _DISABLED_DETAIL
        assert reached == []
        db.refresh(bundle)
        assert bundle.title == "Doom"

    @pytest.mark.usefixtures("metadata_fetch_disabled")
    @pytest.mark.parametrize("route", _ROUTES)
    def test_permission_check_runs_before_disabled_check(self, http_client, route):
        c, db, app = http_client
        bundle = _make_game_bundle(db)
        _set_active_user(app, _make_user(db, can_manage_game=True, can_manage_settings=True))

        resp = _call_route(c, route, bundle.id)

        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] != _DISABLED_DETAIL

    @pytest.mark.usefixtures("metadata_fetch_enabled")
    def test_search_runs_when_enabled(self, http_client, monkeypatch):
        import backend.service.metadata_providers as providers_mod
        from backend.service.metadata_providers import SearchResult

        class _Provider:
            def search_games(self, name):
                return [SearchResult(game_id=7, title=name, release_date=None)]

        c, db, app = http_client
        _set_active_user(app, _make_user(db, is_owner=True))
        monkeypatch.setattr(providers_mod, "get_active_provider", lambda: _Provider())

        resp = c.get("/api/v1/game-items/metadata-search", params={"name": "Doom"})

        assert resp.status_code == 200, resp.text
        assert resp.json()["results"][0]["game_id"] == 7

    @pytest.mark.usefixtures("metadata_fetch_enabled")
    def test_enrich_runs_when_enabled(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db)
        _set_active_user(app, _make_user(db, is_owner=True))

        resp = c.post(
            "/api/v1/game-items/enrich",
            json={"entity_type": "game_item_bundle", "entity_id": bundle.id, "title": "New Title"},
        )

        assert resp.status_code == 200, resp.text
        db.refresh(bundle)
        assert bundle.title == "New Title"
