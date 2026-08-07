"""Route-level (TestClient/HTTP) tests for backend/api/routes/game_metadata.py.

Per dev_docs/P1_AUDIT.md TST-11, game_metadata.py had zero route-level
coverage; test_enrich.py exercises enrich_entity() directly, never
POST /enrich, so the route's is_owner gate and its
rating_change_requires_confirmation wiring (backend/core/dependencies.py)
were never exercised at HTTP. Covers:

    - is_owner gating (403 for non-owner) on all four routes
      (/metadata-search, /metadata-details, /enrich, /{id}/accept-metadata-assets)
    - a content_rating change that lowers an already-set rating 409s without
      confirm_rating_change, and succeeds (rating actually updated) with it
    - a content_rating change that does not lower the rating (same value, or
      moving off an unset rating) needs no confirmation at all

Uses the same in-memory SQLModel SQLite DB + StaticPool +
get_active_user/get_db dependency-override pattern as the other *_routes
test files. rating_change_requires_confirmation's settings-backed ordinal
override (_load_rating_ordinals) falls back to the built-in defaults on the
RuntimeError this in-memory app raises before init_settings() ever runs —
no settings stub is needed here, unlike the emulators.py route tests.
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
