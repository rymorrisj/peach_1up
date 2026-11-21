"""Media content-rating inheritance (MED-8) and linked-title filtering (MED-7).

Covers backend/service/media/content_rating.py (media_rating_visible,
effective_content_rating, checked_media_rating_change), the media filter
queries in backend/core/dependencies.py, the media routes in
backend/api/routes/media.py, and Accept All leaving the bundle's own
rating null (backend/service/games/media_link.py).
"""

import pytest


# ---------------------------------------------------------------------------
# Fixtures and builders
# ---------------------------------------------------------------------------


def _owner():
    from backend.models.user import UserItem
    return UserItem(id=1, name="Owner", is_owner=True)


def _capped(**overrides):
    """Non-owner with a T ceiling and can_manage_media, the account shape
    every parental-control case here is judged against."""
    from backend.models.user import UserItem

    kwargs = dict(id=2, name="Kid", is_owner=False, can_manage_media=True, max_content_rating="T")
    kwargs.update(overrides)
    return UserItem(**kwargs)


@pytest.fixture
def mem_db_session():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine
    import backend.models  # noqa: F401, registers all table models

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def active_user_box():
    """Mutable holder so a test can switch the request's active user."""
    return {"user": _owner()}


@pytest.fixture
def client(mem_db_session, tmp_path, monkeypatch, active_user_box):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import backend.service.utils.settings as settings_mod
    from backend.api.routes import media
    from backend.core.database import get_db
    from backend.core.dependencies import get_active_user

    # Same LIBRARY_PATH patch as test_media.py's client fixture, for
    # _compute_media_url on every read model.
    monkeypatch.setattr(
        settings_mod, "get", lambda key, default=None: str(tmp_path) if key == "LIBRARY_PATH" else default,
    )

    app = FastAPI()
    app.include_router(media.router)
    app.dependency_overrides[get_active_user] = lambda: active_user_box["user"]
    app.dependency_overrides[get_db] = lambda: mem_db_session
    with TestClient(app) as c:
        yield c


def _game(db, slug, rating):
    from backend.models.game import GameItemBundle

    game = GameItemBundle(title=f"Game {slug}", file_path=f"/library/games/dos/{slug}", era="dos", slug=slug,
                          content_rating=rating)
    db.add(game)
    db.commit()
    db.refresh(game)
    return game


def _bundle(db, slug, rating=None):
    from backend.models.media import MediaItemBundle

    bundle = MediaItemBundle(title=f"Media {slug}", media_kind="image", slug=slug, content_rating=rating)
    db.add(bundle)
    db.commit()
    db.refresh(bundle)
    return bundle


def _link(db, bundle, *games):
    from backend.models.media import make_entity_link

    for game in games:
        db.add(make_entity_link("media_item_bundle", bundle.id, "game_item_bundle", game.id))
    db.commit()


def _visible_bundle_ids(db, user):
    from backend.core.dependencies import get_filtered_media_item_bundles

    return {b.id for b in get_filtered_media_item_bundles(user, db).all()}


# ---------------------------------------------------------------------------
# Effective-rating rule, evaluated through the real filter query
# ---------------------------------------------------------------------------


class TestEffectiveRatingFilter:
    def test_single_link_inherits_the_games_rating(self, mem_db_session):
        db = mem_db_session
        hidden = _bundle(db, "m-art")
        shown = _bundle(db, "e-art")
        _link(db, hidden, _game(db, "m", "M"))
        _link(db, shown, _game(db, "e", "E"))

        assert _visible_bundle_ids(db, _capped()) == {shown.id}

    def test_multiple_links_need_every_game_to_pass(self, mem_db_session):
        db = mem_db_session
        mixed = _bundle(db, "mixed")
        all_ok = _bundle(db, "all-ok")
        e, t, m = _game(db, "e", "E"), _game(db, "t", "T"), _game(db, "m", "M")
        _link(db, mixed, e, m)
        _link(db, all_ok, e, t)

        assert _visible_bundle_ids(db, _capped()) == {all_ok.id}

    def test_unrated_linked_game_hides_from_block_unrated_accounts(self, mem_db_session):
        db = mem_db_session
        bundle = _bundle(db, "art")
        _link(db, bundle, _game(db, "e", "E"), _game(db, "unrated", None))

        assert _visible_bundle_ids(db, _capped(block_unrated_media=True)) == set()
        assert _visible_bundle_ids(db, _capped(block_unrated_media=False)) == {bundle.id}

    def test_linked_bundles_own_rating_is_ignored(self, mem_db_session):
        """A leftover own rating on a linked bundle neither hides nor shows
        it; only the linked games count."""
        db = mem_db_session
        bundle = _bundle(db, "art", rating="AO")
        _link(db, bundle, _game(db, "e", "E"))

        assert _visible_bundle_ids(db, _capped()) == {bundle.id}

    def test_no_links_uses_own_rating(self, mem_db_session):
        db = mem_db_session
        e = _bundle(db, "own-e", rating="E")
        m = _bundle(db, "own-m", rating="M")
        unrated = _bundle(db, "own-none")

        assert _visible_bundle_ids(db, _capped()) == {e.id, unrated.id}
        assert _visible_bundle_ids(db, _capped(block_unrated_media=True)) == {e.id}
        assert m.id not in _visible_bundle_ids(db, _capped())

    def test_unknown_own_rating_fails_closed(self, mem_db_session):
        db = mem_db_session
        _bundle(db, "weird", rating="NOT-A-RATING")

        assert _visible_bundle_ids(db, _capped()) == set()

    def test_unresolvable_ceiling_fails_closed(self, mem_db_session, monkeypatch):
        import backend.core.dependencies as deps

        db = mem_db_session
        linked = _bundle(db, "linked")
        _link(db, linked, _game(db, "e", "E"))
        _bundle(db, "own-e", rating="E")
        user = _capped()
        # Simulate a rating_ordinals change orphaning the stored ceiling.
        monkeypatch.setattr(deps, "_load_rating_ordinals", lambda: {"E": 0})
        user.max_content_rating = "T"

        assert _visible_bundle_ids(db, user) == set()

    def test_link_to_a_deleted_game_falls_back_to_own_rating(self, mem_db_session):
        from backend.models.media import make_entity_link

        db = mem_db_session
        bundle = _bundle(db, "stale", rating="M")
        db.add(make_entity_link("media_item_bundle", bundle.id, "game_item_bundle", 9999))
        db.commit()

        assert _visible_bundle_ids(db, _capped()) == set()

    def test_owner_sees_everything(self, mem_db_session):
        db = mem_db_session
        bundle = _bundle(db, "art")
        _link(db, bundle, _game(db, "ao", "AO"))

        assert _visible_bundle_ids(db, _owner()) == {bundle.id}

    def test_items_follow_their_bundle(self, mem_db_session):
        from backend.core.dependencies import get_filtered_media_items
        from backend.models.media import MediaItem

        db = mem_db_session
        hidden = _bundle(db, "m-art")
        _link(db, hidden, _game(db, "m", "M"))
        shown = _bundle(db, "e-art", rating="E")
        db.add_all([
            MediaItem(title="a", media_kind="image", file_path="/a.png", media_item_bundle_id=hidden.id),
            MediaItem(title="b", media_kind="image", file_path="/b.png", media_item_bundle_id=shown.id),
        ])
        db.commit()

        titles = {i.title for i in get_filtered_media_items(_capped(), db).all()}
        assert titles == {"b"}

    def test_standalone_item_is_treated_as_unrated(self, mem_db_session):
        from backend.core.dependencies import get_filtered_media_items
        from backend.models.media import MediaItem

        db = mem_db_session
        db.add(MediaItem(title="loose", media_kind="image", file_path="/x.png"))
        db.commit()

        assert get_filtered_media_items(_capped(block_unrated_media=True), db).count() == 0
        assert get_filtered_media_items(_capped(), db).count() == 1


class TestEffectiveRatingDisplay:
    @pytest.mark.parametrize(
        "own, linked, expected",
        [
            ("E", None, ("E", False)),
            (None, None, (None, False)),
            (None, ["M"], ("M", True)),
            ("E", ["T", "M"], ("M", True)),
            (None, [None, "T"], ("T", True)),
            (None, [None], (None, True)),
            (None, ["T", "NOT-A-RATING"], ("NOT-A-RATING", True)),
        ],
    )
    def test_effective_content_rating(self, own, linked, expected):
        from backend.service.media.content_rating import effective_content_rating

        assert effective_content_rating(own, linked) == expected


# ---------------------------------------------------------------------------
# Routes: list, detail, read model, MED-7
# ---------------------------------------------------------------------------


class TestReadPaths:
    def test_list_and_detail_apply_the_filter(self, client, mem_db_session, active_user_box):
        db = mem_db_session
        hidden = _bundle(db, "m-art")
        _link(db, hidden, _game(db, "m", "M"))
        shown = _bundle(db, "e-art", rating="E")
        active_user_box["user"] = _capped()

        listed = client.get("/api/v1/media-item-bundles").json()
        assert [b["id"] for b in listed["items"]] == [shown.id]
        assert listed["total"] == 1
        assert client.get(f"/api/v1/media-item-bundle/{hidden.id}").status_code == 404
        assert client.get(f"/api/v1/media-item-bundle/{shown.id}").status_code == 200

    def test_item_detail_applies_the_filter(self, client, mem_db_session, active_user_box):
        from backend.models.media import MediaItem

        db = mem_db_session
        hidden = _bundle(db, "m-art")
        _link(db, hidden, _game(db, "m", "M"))
        item = MediaItem(title="a", media_kind="image", file_path="/a.png", media_item_bundle_id=hidden.id)
        db.add(item)
        db.commit()
        active_user_box["user"] = _capped()

        assert client.get(f"/api/v1/media-item/{item.id}").status_code == 404
        assert client.get("/api/v1/media-items").json()["total"] == 0

    def test_read_model_reports_inherited_rating(self, client, mem_db_session):
        db = mem_db_session
        bundle = _bundle(db, "art")
        _link(db, bundle, _game(db, "e", "E"), _game(db, "t", "T"))

        body = client.get(f"/api/v1/media-item-bundle/{bundle.id}").json()
        assert body["content_rating"] is None
        assert body["effective_content_rating"] == "T"
        assert body["is_inherited"] is True

    def test_read_model_reports_own_rating_when_standalone(self, client, mem_db_session):
        bundle = _bundle(mem_db_session, "art", rating="E")

        body = client.get(f"/api/v1/media-item-bundle/{bundle.id}").json()
        assert body["content_rating"] == "E"
        assert body["effective_content_rating"] == "E"
        assert body["is_inherited"] is False

    def test_hidden_game_title_is_not_returned(self, client, mem_db_session, active_user_box):
        """MED-7: a game the viewer cannot see (blocklisted here, so its
        rating still lets the bundle through) is not named in linked_items."""
        from backend.models.media_restriction import MediaRestriction

        db = mem_db_session
        user = _capped()
        db.add(user)
        db.commit()
        bundle = _bundle(db, "art")
        secret, public = _game(db, "secret", "E"), _game(db, "public", "E")
        _link(db, bundle, secret, public)
        db.add(MediaRestriction(user_item_id=user.id, game_item_bundle_id=secret.id))
        db.commit()
        active_user_box["user"] = user

        body = client.get(f"/api/v1/media-item-bundle/{bundle.id}").json()
        titles = {ref["title"] for ref in body["linked_items"]}
        assert titles == {"Game public"}
        assert "Game secret" not in str(body)


# ---------------------------------------------------------------------------
# Writes: create, PATCH, 422 when linked, confirm guard when standalone
# ---------------------------------------------------------------------------


class TestRatingWrites:
    def test_create_normalizes_rating(self, client):
        resp = client.post(
            "/api/v1/media-item-bundles",
            json={"title": "OST", "media_kind": "audio", "content_rating": "M - Mature 17+"},
        )
        assert resp.status_code == 201
        assert resp.json()["content_rating"] == "M"

    def test_patch_rating_on_linked_bundle_is_422(self, client, mem_db_session):
        db = mem_db_session
        bundle = _bundle(db, "art")
        _link(db, bundle, _game(db, "m", "M"))

        resp = client.patch(f"/api/v1/media-item-bundle/{bundle.id}", json={"content_rating": "E"})
        assert resp.status_code == 422
        assert "inherited from the linked software" in resp.json()["detail"]
        db.refresh(bundle)
        assert bundle.content_rating is None

    def test_patch_without_rating_on_linked_bundle_still_works(self, client, mem_db_session):
        db = mem_db_session
        bundle = _bundle(db, "art")
        _link(db, bundle, _game(db, "m", "M"))

        resp = client.patch(f"/api/v1/media-item-bundle/{bundle.id}", json={"title": "Renamed"})
        assert resp.status_code == 200

    def test_standalone_lowering_without_confirm_is_409(self, client, mem_db_session):
        db = mem_db_session
        bundle = _bundle(db, "art", rating="M")

        resp = client.patch(f"/api/v1/media-item-bundle/{bundle.id}", json={"content_rating": "E"})
        assert resp.status_code == 409
        db.refresh(bundle)
        assert bundle.content_rating == "M"

    @pytest.mark.parametrize("new", [None, "PEGI 18"])
    def test_standalone_clearing_or_scheme_change_without_confirm_is_409(self, client, mem_db_session, new):
        bundle = _bundle(mem_db_session, "art", rating="M")

        resp = client.patch(f"/api/v1/media-item-bundle/{bundle.id}", json={"content_rating": new})
        assert resp.status_code == 409

    def test_standalone_lowering_with_confirm_succeeds(self, client, mem_db_session):
        db = mem_db_session
        bundle = _bundle(db, "art", rating="M")

        resp = client.patch(
            f"/api/v1/media-item-bundle/{bundle.id}?confirm_rating_change=true", json={"content_rating": "E"},
        )
        assert resp.status_code == 200
        db.refresh(bundle)
        assert bundle.content_rating == "E"

    def test_null_to_rated_needs_no_confirmation(self, client, mem_db_session):
        bundle = _bundle(mem_db_session, "art")

        resp = client.patch(f"/api/v1/media-item-bundle/{bundle.id}", json={"content_rating": "T"})
        assert resp.status_code == 200
        assert resp.json()["content_rating"] == "T"

    def test_raising_needs_no_confirmation(self, client, mem_db_session):
        bundle = _bundle(mem_db_session, "art", rating="E")

        resp = client.patch(f"/api/v1/media-item-bundle/{bundle.id}", json={"content_rating": "M"})
        assert resp.status_code == 200

    def test_hidden_bundle_patch_is_404(self, client, mem_db_session, active_user_box):
        db = mem_db_session
        bundle = _bundle(db, "art", rating="M")
        active_user_box["user"] = _capped()

        resp = client.patch(
            f"/api/v1/media-item-bundle/{bundle.id}?confirm_rating_change=true", json={"content_rating": None},
        )
        assert resp.status_code == 404
        db.refresh(bundle)
        assert bundle.content_rating == "M"

    def test_patch_requires_can_manage_media(self, client, mem_db_session, active_user_box):
        bundle = _bundle(mem_db_session, "art")
        active_user_box["user"] = _capped(can_manage_media=False)

        resp = client.patch(f"/api/v1/media-item-bundle/{bundle.id}", json={"content_rating": "E"})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Accept All leaves the new bundle's own rating null
# ---------------------------------------------------------------------------


class TestAcceptAllLeavesRatingNull:
    def test_new_linked_bundle_has_no_own_rating(self, mem_db_session, tmp_path, monkeypatch):
        import backend.core.settings as core_settings
        import backend.service.utils.asset_fetch as asset_fetch_mod
        from backend.service.games.media_link import create_linked_media_from_metadata
        from backend.service.metadata_providers import MetadataAsset

        class _S:
            def get_env_var(self, key):
                return str(tmp_path / "media") if key == "MEDIA_PATH" else ""

            def get(self, key, default=None):
                # _load_rating_ordinals reads get("rating_ordinals") when the
                # visibility filter runs below; None means "use the defaults".
                return default

        monkeypatch.setattr(core_settings, "get_settings", lambda: _S())
        monkeypatch.setattr(
            asset_fetch_mod,
            "download_remote_image",
            lambda url, dest_dir, *, filename_stem, **kwargs: dest_dir / f"{filename_stem}.jpg",
        )
        game = _game(mem_db_session, "m", "M")

        bundle = create_linked_media_from_metadata(
            game.id,
            [MetadataAsset(url="https://cdn.thegamesdb.net/images/original/b.jpg", type="boxart_front")],
            mem_db_session,
        )

        assert bundle.content_rating is None
        assert _visible_bundle_ids(mem_db_session, _capped()) == set()
