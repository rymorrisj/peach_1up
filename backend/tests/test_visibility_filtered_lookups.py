"""Visibility-filtered lookups on write routes, and linked-title filtering on
game and app reads.

Lookups: a hidden id must return exactly the same 404 as a missing id on
DELETE /media-item/{id}, DELETE /media-item-bundle/{id}, game confirm-delete
and DELETE, tag assignment, and both sides of an entity link, and must leave
the row untouched.

Reverse leak: game_item_bundle_to_read(_bulk) and app_item_bundle_to_read(_bulk)
must not name a linked media entity the viewer cannot see, the mirror of
MED-7 on the media read builders.
"""

import pytest

_MISSING_ID = 9999


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
def viewer(mem_db_session):
    """A non-owner holding every management flag, capped at T. Holding the
    flags proves the 404 comes from visibility, not from a permission check."""
    from backend.models.user import UserItem

    user = UserItem(
        id=2,
        name="Teen",
        is_owner=False,
        max_content_rating="T",
        can_manage_game=True,
        can_manage_media=True,
        can_manage_app=True,
    )
    mem_db_session.add(user)
    mem_db_session.commit()
    return user


@pytest.fixture
def client(mem_db_session, tmp_path, monkeypatch, viewer):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import backend.service.utils.settings as settings_mod
    from backend.api.routes import entity_links, game_item_bundles, media, tags
    from backend.core.database import get_db
    from backend.core.dependencies import get_active_user

    monkeypatch.setattr(
        settings_mod,
        "get",
        lambda key, default=None: str(tmp_path) if key == "LIBRARY_PATH" else default,
    )
    app = FastAPI()
    for module in (media, entity_links, game_item_bundles, tags):
        app.include_router(module.router)
    app.dependency_overrides[get_active_user] = lambda: viewer
    app.dependency_overrides[get_db] = lambda: mem_db_session
    with TestClient(app) as c:
        yield c


def _game(db, slug, rating):
    from backend.models.game import GameItemBundle

    game = GameItemBundle(title=f"Game {slug}", platform="ps1", slug=slug, content_rating=rating)
    db.add(game)
    db.commit()
    db.refresh(game)
    return game


def _game_leaf(db, game):
    from backend.models.game import GameItem

    leaf = GameItem(game_item_bundle_id=game.id, disc_number=1, file_path=f"/library/games/ps1/{game.slug}/disc.bin")
    db.add(leaf)
    db.commit()
    db.refresh(leaf)
    return leaf


def _bundle(db, slug, rating=None):
    from backend.models.media import MediaItemBundle

    bundle = MediaItemBundle(title=f"Media {slug}", media_kind="image", slug=slug, content_rating=rating)
    db.add(bundle)
    db.commit()
    db.refresh(bundle)
    return bundle


def _item(db, slug, bundle):
    from backend.models.media import MediaItem

    item = MediaItem(
        title=f"Item {slug}", media_kind="image", file_path=f"/m/{slug}.png", slug=slug, media_item_bundle_id=bundle.id
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _app(db, slug):
    from backend.models.app import AppItemBundle

    app = AppItemBundle(title=f"App {slug}", platform="ps1", slug=slug)
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


def _link(db, a_type, a_id, b_type, b_id):
    from backend.models.media import make_entity_link

    db.add(make_entity_link(a_type, a_id, b_type, b_id))
    db.commit()


def _tag(db):
    from backend.models.tag import Tag

    tag = Tag(name="Favourites")
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


def _same_404(hidden_resp, missing_resp):
    assert hidden_resp.status_code == 404, hidden_resp.text
    assert missing_resp.status_code == 404, missing_resp.text
    assert hidden_resp.json() == missing_resp.json()


# ---------------------------------------------------------------------------
# Filtered lookups on write routes
# ---------------------------------------------------------------------------


class TestHiddenIdsReturnTheMissingIdResponse:
    def test_delete_media_item(self, client, mem_db_session):
        from backend.models.media import MediaItem

        db = mem_db_session
        hidden = _item(db, "x", _bundle(db, "m-art", rating="M"))

        _same_404(client.delete(f"/api/v1/media-item/{hidden.id}"), client.delete(f"/api/v1/media-item/{_MISSING_ID}"))
        assert db.get(MediaItem, hidden.id) is not None

    def test_delete_media_item_bundle(self, client, mem_db_session):
        from backend.models.media import MediaItemBundle

        db = mem_db_session
        hidden = _bundle(db, "m-art", rating="M")

        _same_404(
            client.delete(f"/api/v1/media-item-bundle/{hidden.id}"),
            client.delete(f"/api/v1/media-item-bundle/{_MISSING_ID}"),
        )
        assert db.get(MediaItemBundle, hidden.id) is not None

    def test_game_confirm_delete(self, client, mem_db_session):
        hidden = _game(mem_db_session, "m", "M")

        _same_404(
            client.post(f"/api/v1/game-item-bundle/{hidden.id}/confirm-delete"),
            client.post(f"/api/v1/game-item-bundle/{_MISSING_ID}/confirm-delete"),
        )

    def test_game_delete_even_with_a_valid_token(self, client, mem_db_session):
        from backend.models.game import GameItemBundle
        from backend.service.utils import confirmation_tokens

        db = mem_db_session
        hidden = _game(db, "m", "M")
        hidden_token = confirmation_tokens.issue("game", hidden.id)
        missing_token = confirmation_tokens.issue("game", _MISSING_ID)

        _same_404(
            client.delete(f"/api/v1/game-item-bundle/{hidden.id}", params={"confirmation_token": hidden_token}),
            client.delete(f"/api/v1/game-item-bundle/{_MISSING_ID}", params={"confirmation_token": missing_token}),
        )
        assert db.get(GameItemBundle, hidden.id) is not None

    @pytest.mark.parametrize("method", ["POST", "DELETE"])
    def test_tag_assignment_on_hidden_bundles(self, client, mem_db_session, method):
        db = mem_db_session
        tag = _tag(db)
        hidden_game = _game(db, "m", "M")
        hidden_media = _bundle(db, "m-art", rating="M")

        for entity_type, hidden_id in (("game_item_bundle", hidden_game.id), ("media_item_bundle", hidden_media.id)):
            hidden = client.request(
                method, f"/api/v1/tags/{tag.id}/assignments", json={"entity_type": entity_type, "entity_id": hidden_id}
            )
            missing = client.request(
                method,
                f"/api/v1/tags/{tag.id}/assignments",
                json={"entity_type": entity_type, "entity_id": _MISSING_ID},
            )
            _same_404(hidden, missing)

    def test_tag_assignment_on_a_leaf_of_a_hidden_game(self, client, mem_db_session):
        from backend.models.tag import EntityTag

        db = mem_db_session
        tag = _tag(db)
        leaf = _game_leaf(db, _game(db, "m", "M"))

        _same_404(
            client.post(f"/api/v1/tags/{tag.id}/assignments", json={"entity_type": "game_item", "entity_id": leaf.id}),
            client.post(
                f"/api/v1/tags/{tag.id}/assignments", json={"entity_type": "game_item", "entity_id": _MISSING_ID}
            ),
        )
        assert db.query(EntityTag).count() == 0

    def test_tag_assignment_on_visible_entity_still_works(self, client, mem_db_session):
        db = mem_db_session
        tag = _tag(db)
        visible = _game(db, "t", "T")

        resp = client.post(
            f"/api/v1/tags/{tag.id}/assignments", json={"entity_type": "game_item_bundle", "entity_id": visible.id}
        )
        assert resp.status_code == 204, resp.text

    def test_entity_link_hidden_target_on_create_and_delete(self, client, mem_db_session):
        from backend.models.media import MediaLink

        db = mem_db_session
        # An item inside a visible bundle: its own links never change its
        # visibility, so it stays visible after the M link below exists.
        visible = _item(db, "x", _bundle(db, "t-art", rating="T"))
        hidden_game = _game(db, "m", "M")

        def _create(target_id):
            return client.post(
                f"/api/v1/entity-links/media_item/{visible.id}",
                json={"target_entity_type": "game_item_bundle", "target_entity_id": target_id},
            )

        def _delete(target_id):
            return client.delete(
                f"/api/v1/entity-links/media_item/{visible.id}",
                params={"target_entity_type": "game_item_bundle", "target_entity_id": target_id},
            )

        _same_404(_create(hidden_game.id), _create(_MISSING_ID))
        assert db.query(MediaLink).count() == 0

        _link(db, "media_item", visible.id, "game_item_bundle", hidden_game.id)
        hidden_resp = _delete(hidden_game.id)
        _same_404(hidden_resp, _delete(_MISSING_ID))
        assert hidden_resp.json()["detail"] == "game_item_bundle not found."
        assert db.query(MediaLink).count() == 1

    def test_entity_link_hidden_source(self, client, mem_db_session):
        db = mem_db_session
        hidden = _bundle(db, "m-art", rating="M")
        visible_game = _game(db, "t", "T")

        body = {"target_entity_type": "game_item_bundle", "target_entity_id": visible_game.id}
        _same_404(
            client.post(f"/api/v1/entity-links/media_item_bundle/{hidden.id}", json=body),
            client.post(f"/api/v1/entity-links/media_item_bundle/{_MISSING_ID}", json=body),
        )


# ---------------------------------------------------------------------------
# Reverse leak: linked media titles on game and app reads
# ---------------------------------------------------------------------------


def _titles(read):
    return {ref.title for ref in read.linked_items}


@pytest.fixture
def lib_settings(tmp_path, monkeypatch):
    import backend.service.utils.settings as settings_mod

    monkeypatch.setattr(
        settings_mod,
        "get",
        lambda key, default=None: str(tmp_path) if key == "LIBRARY_PATH" else default,
    )


class TestGameAndAppReadsFilterLinkedMedia:
    def _hidden_and_visible_media(self, db, viewer):
        from backend.models.media_restriction import MediaRestriction

        visible = _bundle(db, "visible-art", rating="T")
        restricted = _bundle(db, "restricted-art", rating="T")
        db.add(MediaRestriction(user_item_id=viewer.id, media_item_bundle_id=restricted.id))
        db.commit()
        return visible, restricted

    def test_game_reads(self, mem_db_session, viewer, lib_settings):
        from backend.models.game import game_item_bundle_to_read, game_item_bundles_to_read_bulk

        db = mem_db_session
        game = _game(db, "t", "T")
        visible, restricted = self._hidden_and_visible_media(db, viewer)
        _link(db, "game_item_bundle", game.id, "media_item_bundle", visible.id)
        _link(db, "game_item_bundle", game.id, "media_item_bundle", restricted.id)

        assert _titles(game_item_bundle_to_read(game, db, viewer=viewer)) == {visible.title}
        assert _titles(game_item_bundles_to_read_bulk([game], db, viewer=viewer)[0]) == {visible.title}

    def test_app_reads(self, mem_db_session, viewer, lib_settings):
        from backend.models.app import app_item_bundle_to_read, app_item_bundles_to_read_bulk

        db = mem_db_session
        app = _app(db, "tool")
        visible, restricted = self._hidden_and_visible_media(db, viewer)
        _link(db, "app_item_bundle", app.id, "media_item_bundle", visible.id)
        _link(db, "app_item_bundle", app.id, "media_item_bundle", restricted.id)

        assert _titles(app_item_bundle_to_read(app, db, viewer=viewer)) == {visible.title}
        assert _titles(app_item_bundles_to_read_bulk([app], db, viewer=viewer)[0]) == {visible.title}

    def test_rating_hidden_media_item_is_not_named_on_a_game_read(self, mem_db_session, viewer, lib_settings):
        from backend.models.game import game_item_bundle_to_read

        db = mem_db_session
        game = _game(db, "t", "T")
        hidden_item = _item(db, "x", _bundle(db, "m-art", rating="M"))
        _link(db, "game_item_bundle", game.id, "media_item", hidden_item.id)

        assert _titles(game_item_bundle_to_read(game, db, viewer=viewer)) == set()

    def test_owner_sees_every_linked_title(self, mem_db_session, viewer, lib_settings):
        from backend.models.game import game_item_bundle_to_read
        from backend.models.user import UserItem

        db = mem_db_session
        game = _game(db, "t", "T")
        visible, restricted = self._hidden_and_visible_media(db, viewer)
        _link(db, "game_item_bundle", game.id, "media_item_bundle", visible.id)
        _link(db, "game_item_bundle", game.id, "media_item_bundle", restricted.id)

        owner = UserItem(id=1, name="Owner", is_owner=True)
        assert _titles(game_item_bundle_to_read(game, db, viewer=owner)) == {visible.title, restricted.title}
