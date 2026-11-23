"""Effective-rating confirmation guard (backend/service/media/rating_change_guard.py)
on the four actions that change which games a media unit inherits from:

    - POST   /api/v1/entity-links/{type}/{id}      (link create)
    - DELETE /api/v1/entity-links/{type}/{id}      (link delete)
    - DELETE /api/v1/game-item-bundle/{id}         (game delete)
    - PATCH  /api/v1/media-item/{id}               (move between bundles / to standalone)

Each is covered loosening and tightening, unconfirmed and confirmed, plus the
409 body naming no title.
"""

import pytest

_ERROR_TYPE = "rating_change_requires_confirmation"


def _owner():
    from backend.models.user import UserItem

    return UserItem(id=1, name="Owner", is_owner=True)


@pytest.fixture
def mem_db_session():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine
    import backend.models  # noqa: F401, registers all table models

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def active_user_box():
    return {"user": _owner()}


@pytest.fixture
def client(mem_db_session, tmp_path, monkeypatch, active_user_box):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import backend.service.games.items as game_items_svc
    import backend.service.utils.settings as settings_mod
    from backend.api.routes import entity_links, game_item_bundles, media
    from backend.core.database import get_db
    from backend.core.dependencies import get_active_user

    monkeypatch.setattr(
        settings_mod,
        "get",
        lambda key, default=None: str(tmp_path) if key == "LIBRARY_PATH" else default,
    )
    # Game delete reads delete_media_on_removal from settings; never delete
    # files from these tests.
    monkeypatch.setattr(game_items_svc, "_should_delete_media", lambda collection: False)

    app = FastAPI()
    app.include_router(media.router)
    app.include_router(entity_links.router)
    app.include_router(game_item_bundles.router)
    app.dependency_overrides[get_active_user] = lambda: active_user_box["user"]
    app.dependency_overrides[get_db] = lambda: mem_db_session
    with TestClient(app) as c:
        yield c


def _game(db, slug, rating):
    from backend.models.game import GameItemBundle

    game = GameItemBundle(
        title=f"Game {slug}", file_path=f"/library/games/ps1/{slug}", platform="ps1", slug=slug, content_rating=rating
    )
    db.add(game)
    db.commit()
    db.refresh(game)
    return game


def _bundle(db, slug, rating=None, title=None):
    from backend.models.media import MediaItemBundle

    bundle = MediaItemBundle(title=title or f"Media {slug}", media_kind="image", slug=slug, content_rating=rating)
    db.add(bundle)
    db.commit()
    db.refresh(bundle)
    return bundle


def _item(db, slug, bundle=None):
    from backend.models.media import MediaItem

    item = MediaItem(
        title=f"Item {slug}",
        media_kind="image",
        file_path=f"/m/{slug}.png",
        slug=slug,
        media_item_bundle_id=bundle.id if bundle else None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _link(db, media_type, media_id, *games):
    from backend.models.media import make_entity_link

    for game in games:
        db.add(make_entity_link(media_type, media_id, "game_item_bundle", game.id))
    db.commit()


def _link_count(db):
    from backend.models.media import MediaLink

    return db.query(MediaLink).count()


def _create_link(client, game, media_type, media_id, *, confirm=False):
    params = {"confirm_rating_change": "true"} if confirm else {}
    return client.post(
        f"/api/v1/entity-links/game_item_bundle/{game.id}",
        json={"target_entity_type": media_type, "target_entity_id": media_id},
        params=params,
    )


def _delete_link(client, game, media_type, media_id, *, confirm=False):
    params = {"target_entity_type": media_type, "target_entity_id": media_id}
    if confirm:
        params["confirm_rating_change"] = "true"
    return client.delete(f"/api/v1/entity-links/game_item_bundle/{game.id}", params=params)


def _assert_guard_409(resp, affected_count):
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["error_type"] == _ERROR_TYPE
    assert detail["affected_count"] == affected_count
    assert "confirm_rating_change=true" in detail["message"]


# ---------------------------------------------------------------------------
# Link create
# ---------------------------------------------------------------------------


class TestLinkCreateGuard:
    def test_lower_rated_game_on_rated_bundle_needs_confirm(self, client, mem_db_session):
        db = mem_db_session
        bundle = _bundle(db, "art", rating="M")
        game = _game(db, "e", "E")

        _assert_guard_409(_create_link(client, game, "media_item_bundle", bundle.id), 1)
        assert _link_count(db) == 0

        assert _create_link(client, game, "media_item_bundle", bundle.id, confirm=True).status_code == 201
        assert _link_count(db) == 1

    def test_unrated_game_on_rated_bundle_needs_confirm(self, client, mem_db_session):
        """Linking makes the bundle inherit "unrated", which clears M."""
        db = mem_db_session
        bundle = _bundle(db, "art", rating="M")
        game = _game(db, "unrated", None)

        _assert_guard_409(_create_link(client, game, "media_item_bundle", bundle.id), 1)

    def test_scheme_change_needs_confirm(self, client, mem_db_session):
        db = mem_db_session
        bundle = _bundle(db, "art", rating="M")
        game = _game(db, "pegi", "PEGI 18")

        _assert_guard_409(_create_link(client, game, "media_item_bundle", bundle.id), 1)

    def test_tightening_needs_no_confirm(self, client, mem_db_session):
        db = mem_db_session
        unrated = _bundle(db, "unrated-art")
        already_e = _bundle(db, "e-art")
        _link(db, "media_item_bundle", already_e.id, _game(db, "e", "E"))
        m = _game(db, "m", "M")

        assert _create_link(client, m, "media_item_bundle", unrated.id).status_code == 201
        assert _create_link(client, m, "media_item_bundle", already_e.id).status_code == 201

    def test_existing_link_returns_without_guard(self, client, mem_db_session):
        db = mem_db_session
        bundle = _bundle(db, "art", rating="M")
        game = _game(db, "e", "E")
        _link(db, "media_item_bundle", bundle.id, game)

        assert _create_link(client, game, "media_item_bundle", bundle.id).status_code == 201
        assert _link_count(db) == 1

    def test_link_on_item_inside_a_bundle_never_needs_confirm(self, client, mem_db_session):
        """An item in a bundle is judged by its bundle only, so its own links
        never change who can see it."""
        db = mem_db_session
        bundle = _bundle(db, "art", rating="M")
        item = _item(db, "inside", bundle)

        assert _create_link(client, _game(db, "unrated", None), "media_item", item.id).status_code == 201

    def test_standalone_item_link_is_tightening(self, client, mem_db_session):
        db = mem_db_session
        item = _item(db, "loose")

        assert _create_link(client, _game(db, "m", "M"), "media_item", item.id).status_code == 201


# ---------------------------------------------------------------------------
# Link delete
# ---------------------------------------------------------------------------


class TestLinkDeleteGuard:
    def test_removing_only_rated_link_needs_confirm(self, client, mem_db_session):
        db = mem_db_session
        bundle = _bundle(db, "art")
        game = _game(db, "m", "M")
        _link(db, "media_item_bundle", bundle.id, game)

        _assert_guard_409(_delete_link(client, game, "media_item_bundle", bundle.id), 1)
        assert _link_count(db) == 1

        assert _delete_link(client, game, "media_item_bundle", bundle.id, confirm=True).status_code == 204
        assert _link_count(db) == 0

    def test_removing_strictest_link_needs_confirm(self, client, mem_db_session):
        db = mem_db_session
        bundle = _bundle(db, "art")
        e, m = _game(db, "e", "E"), _game(db, "m", "M")
        _link(db, "media_item_bundle", bundle.id, e, m)

        _assert_guard_409(_delete_link(client, m, "media_item_bundle", bundle.id), 1)

    def test_removing_a_less_strict_link_needs_no_confirm(self, client, mem_db_session):
        db = mem_db_session
        bundle = _bundle(db, "art")
        e, m = _game(db, "e", "E"), _game(db, "m", "M")
        _link(db, "media_item_bundle", bundle.id, e, m)

        assert _delete_link(client, e, "media_item_bundle", bundle.id).status_code == 204

    def test_falling_back_to_a_stricter_own_rating_needs_no_confirm(self, client, mem_db_session):
        db = mem_db_session
        bundle = _bundle(db, "art", rating="AO")
        game = _game(db, "m", "M")
        _link(db, "media_item_bundle", bundle.id, game)

        assert _delete_link(client, game, "media_item_bundle", bundle.id).status_code == 204

    def test_standalone_item_becoming_unrated_needs_confirm(self, client, mem_db_session):
        db = mem_db_session
        item = _item(db, "loose")
        game = _game(db, "m", "M")
        _link(db, "media_item", item.id, game)

        _assert_guard_409(_delete_link(client, game, "media_item", item.id), 1)
        assert _delete_link(client, game, "media_item", item.id, confirm=True).status_code == 204


# ---------------------------------------------------------------------------
# Game delete
# ---------------------------------------------------------------------------


def _delete_game(client, game_id, *, token=None, confirm=False):
    if token is None:
        token = client.post(f"/api/v1/game-item-bundle/{game_id}/confirm-delete").json()["confirmation_token"]
    params = {"confirmation_token": token}
    if confirm:
        params["confirm_rating_change"] = "true"
    return client.delete(f"/api/v1/game-item-bundle/{game_id}", params=params), token


class TestGameDeleteGuard:
    def test_loosening_every_linked_unit_needs_confirm_and_keeps_the_token(self, client, mem_db_session):
        from backend.models.game import GameItemBundle

        db = mem_db_session
        game = _game(db, "m", "M")
        bundle = _bundle(db, "art")
        item = _item(db, "loose")
        _link(db, "media_item_bundle", bundle.id, game)
        _link(db, "media_item", item.id, game)

        resp, token = _delete_game(client, game.id)
        _assert_guard_409(resp, 2)
        assert db.get(GameItemBundle, game.id) is not None
        assert _link_count(db) == 2

        # The 409 fired before the service consumed the token, so the same
        # token works for the confirmed retry.
        resp, _ = _delete_game(client, game.id, token=token, confirm=True)
        assert resp.status_code == 204, resp.text
        db.expire_all()
        assert db.get(GameItemBundle, game.id) is None
        assert _link_count(db) == 0

    def test_no_loosening_needs_no_confirm(self, client, mem_db_session):
        db = mem_db_session
        e, m = _game(db, "e", "E"), _game(db, "m", "M")
        bundle = _bundle(db, "art")
        _link(db, "media_item_bundle", bundle.id, e, m)

        resp, _ = _delete_game(client, e.id)
        assert resp.status_code == 204, resp.text

    def test_fallback_to_stricter_own_rating_needs_no_confirm(self, client, mem_db_session):
        db = mem_db_session
        game = _game(db, "e", "E")
        bundle = _bundle(db, "art", rating="M")
        _link(db, "media_item_bundle", bundle.id, game)

        resp, _ = _delete_game(client, game.id)
        assert resp.status_code == 204, resp.text

    def test_game_with_no_links_needs_no_confirm(self, client, mem_db_session):
        resp, _ = _delete_game(client, _game(mem_db_session, "solo", "M").id)
        assert resp.status_code == 204, resp.text


# ---------------------------------------------------------------------------
# Media item move
# ---------------------------------------------------------------------------


def _move(client, item, bundle_id, *, confirm=False):
    params = {"confirm_rating_change": "true"} if confirm else {}
    return client.patch(f"/api/v1/media-item/{item.id}", json={"media_item_bundle_id": bundle_id}, params=params)


class TestMediaItemMoveGuard:
    def test_into_lower_rated_bundle_needs_confirm(self, client, mem_db_session):
        from backend.models.media import MediaItem

        db = mem_db_session
        strict, lenient = _bundle(db, "strict", rating="M"), _bundle(db, "lenient", rating="E")
        item = _item(db, "x", strict)

        _assert_guard_409(_move(client, item, lenient.id), 1)
        db.expire_all()
        assert db.get(MediaItem, item.id).media_item_bundle_id == strict.id

        resp = _move(client, item, lenient.id, confirm=True)
        assert resp.status_code == 200, resp.text
        assert resp.json()["media_item_bundle_id"] == lenient.id

    def test_out_to_standalone_becoming_unrated_needs_confirm(self, client, mem_db_session):
        db = mem_db_session
        item = _item(db, "x", _bundle(db, "strict", rating="M"))

        _assert_guard_409(_move(client, item, None), 1)
        assert _move(client, item, None, confirm=True).status_code == 200

    def test_into_inherited_lower_rating_needs_confirm(self, client, mem_db_session):
        db = mem_db_session
        target = _bundle(db, "linked")
        _link(db, "media_item_bundle", target.id, _game(db, "e", "E"))
        item = _item(db, "x", _bundle(db, "strict", rating="M"))

        _assert_guard_409(_move(client, item, target.id), 1)

    def test_into_stricter_bundle_needs_no_confirm(self, client, mem_db_session):
        db = mem_db_session
        item = _item(db, "x", _bundle(db, "lenient", rating="E"))

        assert _move(client, item, _bundle(db, "strict", rating="M").id).status_code == 200

    def test_standalone_into_rated_bundle_needs_no_confirm(self, client, mem_db_session):
        db = mem_db_session
        item = _item(db, "x")

        assert _move(client, item, _bundle(db, "strict", rating="M").id).status_code == 200

    def test_same_bundle_and_title_only_patch_need_no_confirm(self, client, mem_db_session):
        db = mem_db_session
        bundle = _bundle(db, "strict", rating="M")
        item = _item(db, "x", bundle)

        assert _move(client, item, bundle.id).status_code == 200
        assert client.patch(f"/api/v1/media-item/{item.id}", json={"title": "Renamed"}).status_code == 200


# ---------------------------------------------------------------------------
# 409 body
# ---------------------------------------------------------------------------


class TestConflictBodyLeaksNoTitles:
    def test_game_delete_409_counts_hidden_media_without_naming_it(
        self,
        client,
        mem_db_session,
        active_user_box,
    ):
        from backend.models.media_restriction import MediaRestriction
        from backend.models.user import UserItem

        db = mem_db_session
        caller = UserItem(
            id=2, name="Parent", is_owner=False, can_manage_game=True, can_manage_media=True, max_content_rating="T"
        )
        db.add(caller)
        db.commit()
        game = _game(db, "t", "T")
        visible = _bundle(db, "visible-art", title="Visible Art")
        hidden = _bundle(db, "secret-art", title="Secret Art")
        _link(db, "media_item_bundle", visible.id, game)
        _link(db, "media_item_bundle", hidden.id, game)
        db.add(MediaRestriction(user_item_id=caller.id, media_item_bundle_id=hidden.id))
        db.commit()
        active_user_box["user"] = caller

        resp, _ = _delete_game(client, game.id)

        _assert_guard_409(resp, 2)
        for leaked in ("Secret Art", "secret-art", "Visible Art", "visible-art"):
            assert leaked not in resp.text
