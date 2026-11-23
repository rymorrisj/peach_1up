"""Route-level (TestClient/HTTP) tests for backend/api/routes/game_metadata.py.

Scoped to the routes themselves, the is_owner gate and the
rating_change_requires_confirmation wiring (backend/core/dependencies.py);
test_enrich.py drives enrich_game_bundle() directly. Covers:

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

    kwargs = dict(title="Doom", file_path="/library/games/dos/doom", platform="dos", slug="doom")
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
        detail = resp.json()["detail"]
        assert detail["error_type"] == "rating_change_requires_confirmation"
        assert detail["reason"] == "lowered"
        assert detail["current_rating"] == "M"
        assert detail["new_rating"] == "E"
        db.refresh(bundle)
        assert bundle.content_rating == "M"

    @pytest.mark.parametrize("sent,reason", [(None, "cleared"), ("PEGI 3", "scheme_changed")])
    def test_clearing_or_changing_scheme_reports_its_reason(self, http_client, sent, reason):
        c, db, app = http_client
        bundle = _make_game_bundle(db, content_rating="M")
        _set_active_user(app, _make_user(db, is_owner=True))

        resp = c.post(
            "/api/v1/game-items/enrich",
            json={"entity_type": "game_item_bundle", "entity_id": bundle.id, "content_rating": sent},
        )

        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"]["reason"] == reason

    def test_a_409_applies_nothing_but_leaving_the_rating_out_applies_the_rest(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db, content_rating="M", description="old")
        _set_active_user(app, _make_user(db, is_owner=True))
        base = {"entity_type": "game_item_bundle", "entity_id": bundle.id, "description": "new"}

        refused = c.post("/api/v1/game-items/enrich", json={**base, "content_rating": "E"})
        db.refresh(bundle)
        assert refused.status_code == 409
        assert bundle.description == "old"

        applied = c.post("/api/v1/game-items/enrich", json=base)
        db.refresh(bundle)
        assert applied.status_code == 200, applied.text
        assert (bundle.description, bundle.content_rating) == ("new", "M")

    def test_a_disc_entity_type_is_rejected_not_read_as_a_bundle_id(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db)
        _set_active_user(app, _make_user(db, is_owner=True))

        resp = c.post(
            "/api/v1/game-items/enrich",
            json={"entity_type": "game_item", "entity_id": bundle.id, "title": "Hijack"},
        )

        assert resp.status_code == 422, resp.text
        db.refresh(bundle)
        assert bundle.title == "Doom"

    def test_hidden_bundle_is_the_same_404_as_a_missing_one(self, http_client):
        c, db, app = http_client
        hidden = _make_game_bundle(db, content_rating="M", slug="hidden")
        owner = _make_user(db, is_owner=True)
        _set_active_user(app, owner)
        missing = c.post("/api/v1/game-items/enrich", json={"entity_id": 9999, "title": "x"})
        assert missing.status_code == 404

        # Only an owner can reach the route, and an owner sees everything, so
        # visibility is exercised through get_filtered_game_item_bundle itself.
        from fastapi import HTTPException
        from backend.core.dependencies import get_filtered_game_item_bundle

        capped = _make_user(db, max_content_rating="E", name="kid")
        with pytest.raises(HTTPException) as exc_info:
            get_filtered_game_item_bundle(hidden.id, capped, db)
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == missing.json()["detail"]

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
        monkeypatch.setattr(media_link_mod, "prepare_apply", lambda *a, **k: called.append(a))

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
        import tempfile
        from pathlib import Path

        import backend.core.settings as core_settings
        import backend.service.utils.asset_fetch as asset_fetch_mod
        import backend.service.utils.settings as utils_settings
        from backend.service.games.media_link import prepare_apply, run_apply
        from backend.service.metadata_providers import MetadataAsset

        class _S:
            def get_env_var(self, key):
                return str(tmp_path / "media") if key == "MEDIA_PATH" else ""

            def get(self, key, default=None):
                return default

        monkeypatch.setattr(core_settings, "get_settings", lambda: _S())
        monkeypatch.setattr(
            utils_settings, "get", lambda key, default=None: str(tmp_path) if key == "LIBRARY_PATH" else default,
        )

        def _fake_fetch(url, staging_dir, **kwargs):
            fd, raw = tempfile.mkstemp(dir=staging_dir)
            with open(fd, "wb") as fh:
                fh.write(b"\xff\xd8\xff" + url.encode())
            return Path(raw), ".jpg"

        monkeypatch.setattr(asset_fetch_mod, "fetch_image_to_temp", _fake_fetch)
        bundle = _make_game_bundle(mem_db_session)
        assets = [
            MetadataAsset(url=f"https://cdn.thegamesdb.net/images/original/s{i}.jpg", type="screenshot")
            for i in range(10)
        ]

        media = run_apply(prepare_apply(bundle.id, assets, mem_db_session), mem_db_session)

        stems = {Path(i.file_path).stem for i in media.items}
        assert len(stems) == 10


class TestTheGamesDBAssetTypeFilter:
    def test_label_outside_allowlist_is_not_offered(self):
        from backend.service.metadata_providers import ASSET_TYPES
        from backend.service.metadata_providers.thegamesdb_provider import _asset_type_label

        assert _asset_type_label({"type": "boxart", "side": "front"}) in ASSET_TYPES
        assert _asset_type_label({"type": "screenshot"}) in ASSET_TYPES
        assert _asset_type_label({"type": "../evil", "side": "x"}) not in ASSET_TYPES


class _FakeTgdb:
    """Stands in for thegamesdb_client: records get_genres calls."""

    def __init__(self, monkeypatch, genres, game_genres):
        import backend.service.thegamesdb_client as client

        self.genre_calls = 0
        self._genres = genres
        self.fail_rewarm_after = None
        details = {"data": {"games": [{"id": 5, "game_title": "Doom", "genres": game_genres}]}}
        images = {"data": {"base_url": {}, "images": {}}}
        monkeypatch.setattr(client, "get_game_details", lambda game_id: details)
        monkeypatch.setattr(client, "get_game_images", lambda game_id: images)
        monkeypatch.setattr(client, "get_genres", self._get_genres)

    def _get_genres(self):
        import httpx2

        self.genre_calls += 1
        if self.fail_rewarm_after is not None and self.genre_calls > self.fail_rewarm_after:
            raise httpx2.TimeoutException("timed out")
        return {"data": {"genres": {str(i): {"id": i, "name": n} for i, n in self._genres.items()}}}


class TestTheGamesDBGenreResolution:
    def _seed(self, db, genres):
        from backend.models.metadata_lookup import get_or_create_genre

        for gid, name in genres.items():
            get_or_create_genre(db, name, provider="thegamesdb", external_id=gid)
        db.commit()

    def _details(self, db):
        from backend.service.metadata_providers.thegamesdb_provider import TheGamesDBProvider

        return TheGamesDBProvider().get_game_details(5, db)

    def test_unknown_id_rewarms_the_cache_once_and_resolves(self, mem_db_session, monkeypatch):
        self._seed(mem_db_session, {1: "Action"})
        fake = _FakeTgdb(monkeypatch, {1: "Action", 2: "Puzzle"}, [1, 2])

        result = self._details(mem_db_session)

        assert result.genres == ["Action", "Puzzle"]
        assert result.unresolved_genre_ids == []
        assert fake.genre_calls == 1

    def test_id_unknown_after_rewarm_is_reported_not_fatal(self, mem_db_session, monkeypatch):
        self._seed(mem_db_session, {1: "Action"})
        fake = _FakeTgdb(monkeypatch, {1: "Action"}, [1, 99])

        result = self._details(mem_db_session)

        assert result.genres == ["Action"]
        assert result.unresolved_genre_ids == [99]
        assert fake.genre_calls == 1

    def test_failed_rewarm_leaves_the_fetch_working(self, mem_db_session, monkeypatch):
        self._seed(mem_db_session, {1: "Action"})
        fake = _FakeTgdb(monkeypatch, {1: "Action"}, [1, 99])
        fake.fail_rewarm_after = 0

        result = self._details(mem_db_session)

        assert result.genres == ["Action"]
        assert result.unresolved_genre_ids == [99]

    def test_name_cached_under_another_provider_still_resolves(self, mem_db_session, monkeypatch):
        from backend.models.metadata_lookup import get_or_create_genre

        get_or_create_genre(mem_db_session, "Puzzle", provider="igdb", external_id=7)
        self._seed(mem_db_session, {1: "Action"})
        _FakeTgdb(monkeypatch, {1: "Action", 2: "Puzzle"}, [2])

        result = self._details(mem_db_session)

        assert result.genres == ["Puzzle"]
        assert result.unresolved_genre_ids == []

    def test_all_ids_cached_makes_no_api_call(self, mem_db_session, monkeypatch):
        self._seed(mem_db_session, {1: "Action"})
        fake = _FakeTgdb(monkeypatch, {1: "Action"}, [1])

        assert self._details(mem_db_session).genres == ["Action"]
        assert fake.genre_calls == 0


class TestTheGamesDBSearchPlatform:
    def test_platform_name_comes_from_the_include_table(self, monkeypatch):
        import backend.service.thegamesdb_client as client
        from backend.service.metadata_providers.thegamesdb_provider import TheGamesDBProvider

        raw = {
            "data": {"games": [
                {"id": 1, "game_title": "Doom", "release_date": "1993-12-10", "platform": 1},
                {"id": 2, "game_title": "Doom", "release_date": "1994-01-01", "platform": 99},
                {"id": 3, "game_title": "Doom", "release_date": None},
            ]},
            "include": {"platform": {"data": {"1": {"id": 1, "name": "PC", "alias": "pc"}}}},
        }
        monkeypatch.setattr(client, "search_games", lambda name: raw)

        results = TheGamesDBProvider().search_games("Doom")

        assert [r.platform for r in results] == ["PC", None, None]

    def test_response_without_an_include_table_gives_no_label(self, monkeypatch):
        import backend.service.thegamesdb_client as client
        from backend.service.metadata_providers.thegamesdb_provider import TheGamesDBProvider

        raw = {"data": {"games": [{"id": 1, "game_title": "Doom", "platform": 1}]}}
        monkeypatch.setattr(client, "search_games", lambda name: raw)

        assert TheGamesDBProvider().search_games("Doom")[0].platform is None


class TestTheGamesDBClientFields:
    def test_details_request_asks_only_for_fields_the_provider_maps(self, monkeypatch):
        import backend.service.thegamesdb_client as client

        seen = {}

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {}

        def _get(url, params, timeout):
            seen.update(params)
            return _Resp()

        monkeypatch.setattr(client, "_api_key", lambda: "k")
        monkeypatch.setattr(client.httpx2, "get", _get)

        client.get_game_details(5)

        assert seen["fields"].split(",") == [
            "overview", "rating", "genres", "publishers", "developers", "platform", "youtube",
        ]


@pytest.mark.usefixtures("metadata_fetch_enabled")
class TestMatchedIdAndPlatformRoutes:
    def test_search_response_carries_the_platform_label(self, http_client, monkeypatch):
        import backend.service.metadata_providers as providers_mod
        from backend.service.metadata_providers import SearchResult

        class _Provider:
            def search_games(self, name):
                return [SearchResult(game_id=7, title=name, release_date=None, platform="PC")]

        c, db, app = http_client
        _set_active_user(app, _make_user(db, is_owner=True))
        monkeypatch.setattr(providers_mod, "get_active_provider", lambda: _Provider())

        resp = c.get("/api/v1/game-items/metadata-search", params={"name": "Doom"})

        assert resp.json()["results"][0]["platform"] == "PC"

    def test_details_response_lists_unresolved_genre_ids(self, http_client, monkeypatch):
        import backend.service.metadata_providers as providers_mod
        from backend.service.metadata_providers import GameDetails

        class _Provider:
            def get_game_details(self, game_id, db):
                return GameDetails(game_id=game_id, genres=["Action"], unresolved_genre_ids=[99])

        c, db, app = http_client
        _set_active_user(app, _make_user(db, is_owner=True))
        monkeypatch.setattr(providers_mod, "get_active_provider", lambda: _Provider())

        resp = c.get("/api/v1/game-items/metadata-details", params={"game_id": 5})

        assert resp.status_code == 200, resp.text
        assert resp.json()["unresolved_genre_ids"] == [99]

    def test_enrich_persists_the_matched_game_id(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db)
        _set_active_user(app, _make_user(db, is_owner=True))

        resp = c.post(
            "/api/v1/game-items/enrich",
            json={"entity_type": "game_item_bundle", "entity_id": bundle.id, "external_game_id": 1234},
        )

        assert resp.status_code == 200, resp.text
        db.refresh(bundle)
        assert bundle.external_game_id == 1234

    def test_enrich_without_a_game_id_leaves_the_stored_one(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db, external_game_id=55)
        _set_active_user(app, _make_user(db, is_owner=True))

        c.post(
            "/api/v1/game-items/enrich",
            json={"entity_type": "game_item_bundle", "entity_id": bundle.id, "title": "New"},
        )

        db.refresh(bundle)
        assert bundle.external_game_id == 55


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
        monkeypatch.setattr(enrich_mod, "enrich_game_bundle", lambda *a, **k: reached.append("enrich"))
        monkeypatch.setattr(media_link_mod, "prepare_apply", lambda *a, **k: reached.append("accept"))

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


#
# Provider failures map to specific responses and never leak a key or URL
#

_SECRET_URL = "https://api.thegamesdb.net/v1/Games/ByGameName?apikey=SECRET-KEY&name=Doom"


def _status_error(status):
    import httpx2

    request = httpx2.Request("GET", _SECRET_URL)
    return httpx2.HTTPStatusError(f"boom {_SECRET_URL}", request=request, response=httpx2.Response(status, request=request))


def _raising_provider(monkeypatch, exc):
    import backend.service.metadata_providers as providers_mod

    class _Provider:
        def search_games(self, name):
            raise exc

        def get_game_details(self, game_id, db):
            raise exc

    monkeypatch.setattr(providers_mod, "get_active_provider", lambda: _Provider())
    monkeypatch.setattr(providers_mod, "active_provider_label", lambda: "TheGamesDB")


def _provider_call(c, route):
    if route == "search":
        return c.get("/api/v1/game-items/metadata-search", params={"name": "Doom"})
    return c.get("/api/v1/game-items/metadata-details", params={"game_id": 5})


@pytest.mark.usefixtures("metadata_fetch_enabled")
@pytest.mark.parametrize("route", ["search", "details"])
class TestProviderErrorMapping:
    def _client(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, is_owner=True))
        return c

    def test_provider_error_response_is_502_naming_provider_and_status(self, http_client, monkeypatch, route):
        _raising_provider(monkeypatch, _status_error(503))

        resp = _provider_call(self._client(http_client), route)

        assert resp.status_code == 502
        assert resp.json()["detail"] == "TheGamesDB returned 503."

    def test_provider_timeout_is_504(self, http_client, monkeypatch, route):
        import httpx2

        _raising_provider(monkeypatch, httpx2.ReadTimeout(f"timed out {_SECRET_URL}"))

        resp = _provider_call(self._client(http_client), route)

        assert resp.status_code == 504
        assert resp.json()["detail"] == "TheGamesDB did not respond in time."

    def test_connection_failure_is_502(self, http_client, monkeypatch, route):
        import httpx2

        _raising_provider(monkeypatch, httpx2.ConnectError(f"refused {_SECRET_URL}"))

        resp = _provider_call(self._client(http_client), route)

        assert resp.status_code == 502
        assert resp.json()["detail"] == "Could not reach TheGamesDB."

    def test_unreadable_body_is_502(self, http_client, monkeypatch, route):
        import json

        _raising_provider(monkeypatch, json.JSONDecodeError("bad", "<html>", 0))

        resp = _provider_call(self._client(http_client), route)

        assert resp.status_code == 502
        assert resp.json()["detail"] == "TheGamesDB returned an unreadable response."

    @pytest.mark.parametrize("make_exc", [
        lambda: _status_error(500),
        lambda: __import__("httpx2").ReadTimeout(f"t {_SECRET_URL}"),
        lambda: __import__("httpx2").ConnectError(f"c {_SECRET_URL}"),
    ])
    def test_no_key_or_url_reaches_the_response(self, http_client, monkeypatch, route, make_exc):
        _raising_provider(monkeypatch, make_exc())

        resp = _provider_call(self._client(http_client), route)

        for leaked in ("SECRET-KEY", "apikey", "https://", "api.thegamesdb.net"):
            assert leaked not in resp.text

    def test_missing_credentials_keep_their_clear_503(self, http_client, monkeypatch, route):
        _raising_provider(monkeypatch, ValueError("THEGAMESDB_API_KEY is not configured."))

        resp = _provider_call(self._client(http_client), route)

        assert resp.status_code == 503
        assert resp.json()["detail"] == "THEGAMESDB_API_KEY is not configured."


@pytest.mark.usefixtures("metadata_fetch_enabled")
class TestDetailsExternalLinks:
    def test_details_offers_provider_links_and_trailers_http_only(self, http_client, monkeypatch):
        import backend.service.metadata_providers as providers_mod
        from backend.service.metadata_providers import GameDetails

        class _Provider:
            def get_game_details(self, game_id, db):
                return GameDetails(
                    game_id=game_id,
                    video_urls=["https://www.youtube.com/watch?v=abc"],
                    external_links=[
                        {"type": "official", "url": "https://example.com/doom", "source": "provider"},
                        {"type": "store", "url": "javascript:alert(1)", "source": "provider"},
                    ],
                )

        c, db, app = http_client
        _set_active_user(app, _make_user(db, is_owner=True))
        monkeypatch.setattr(providers_mod, "get_active_provider", lambda: _Provider())

        resp = c.get("/api/v1/game-items/metadata-details", params={"game_id": 5})

        assert resp.json()["external_links"] == [
            {"type": "official", "url": "https://example.com/doom", "source": "provider"},
            {"type": "trailer", "url": "https://www.youtube.com/watch?v=abc", "source": "provider"},
        ]


#
# The provider behind a stored external_game_id
#


@pytest.mark.usefixtures("metadata_fetch_enabled")
class TestStoredGameIdAndProvider:
    def test_enrich_stores_the_canonical_provider_name(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db)
        _set_active_user(app, _make_user(db, is_owner=True))

        resp = c.post(
            "/api/v1/game-items/enrich",
            json={"entity_id": bundle.id, "external_game_id": 525, "metadata_source": "igdb"},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["metadata_source"] == "IGDB"
        assert resp.json()["external_provider"] == "igdb"
        assert resp.json()["external_game_id"] == 525

    @pytest.mark.parametrize("source,provider", [
        ("TheGamesDB", "thegamesdb"), ("IGDB", "igdb"), ("igdb", "igdb"),
        (None, None), ("", None), ("Manual", None), ("TheGamesDB v2", None),
    ])
    def test_reader_tolerates_legacy_and_unknown_sources(self, mem_db_session, source, provider):
        from backend.models.game import game_item_bundle_to_read

        owner = _make_user(mem_db_session, is_owner=True)
        bundle = _make_game_bundle(mem_db_session, external_game_id=525, metadata_source=source)

        read = game_item_bundle_to_read(bundle, mem_db_session, viewer=owner)

        assert read.external_game_id == 525
        assert read.external_provider == provider
