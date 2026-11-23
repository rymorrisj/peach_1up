"""GET/PUT /game-item-bundle/{id}/cover-candidates and /cover-art.

A linked Media image can become a game's cover only if the caller may see
both the game and the image. Hidden, unlinked, non-image and missing media
ids must all answer with the same 404.
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


@pytest.fixture
def env(mem_db_session, tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import game_item_bundles
    from backend.core.database import get_db
    import backend.service.utils.settings as settings_mod

    monkeypatch.setattr(
        settings_mod, "get", lambda key, default=None: str(tmp_path) if key == "LIBRARY_PATH" else default,
    )
    app = FastAPI()
    app.include_router(game_item_bundles.router)
    app.dependency_overrides[get_db] = lambda: mem_db_session
    with TestClient(app) as c:
        yield c, mem_db_session, app, tmp_path


def _user(db, **overrides):
    from backend.models.user import UserItem

    kwargs = dict(name="u", is_owner=False, is_admin=False, can_manage_game=True)
    kwargs.update(overrides)
    user = UserItem(**kwargs)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _act_as(app, user):
    from backend.core.dependencies import get_active_user

    app.dependency_overrides[get_active_user] = lambda: user


def _game(db, slug="doom", discs=1, **overrides):
    from backend.models.game import GameItem, GameItemBundle

    game = GameItemBundle(title=slug, platform="dos", slug=slug, **overrides)
    db.add(game)
    db.flush()
    leaves = []
    for n in range(1, discs + 1):
        leaf = GameItem(game_item_bundle_id=game.id, disc_number=n, file_path=f"/library/games/{slug}{n}.img")
        db.add(leaf)
        leaves.append(leaf)
    db.commit()
    db.refresh(game)
    return game, leaves


def _image(path, body=b"\x89PNG\r\n\x1a\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


def _media_bundle(db, title, files, kind="image", game=None, **overrides):
    from backend.models.media import MediaItem, MediaItemBundle, make_entity_link

    bundle = MediaItemBundle(title=title, media_kind=kind, slug=title.lower().replace(" ", "-"), **overrides)
    db.add(bundle)
    db.flush()
    items = []
    for i, f in enumerate(files):
        item = MediaItem(title=f"{title} {i}", media_kind=kind, file_path=str(f), media_item_bundle_id=bundle.id)
        db.add(item)
        items.append(item)
    if game is not None:
        db.add(make_entity_link("media_item_bundle", bundle.id, "game_item_bundle", game.id))
    db.commit()
    for item in items:
        db.refresh(item)
    return bundle, items


def _candidates(c, game):
    return c.get(f"/api/v1/game-item-bundle/{game.id}/cover-candidates")


def _set(c, game, media_item_id):
    return c.put(f"/api/v1/game-item-bundle/{game.id}/cover-art", json={"media_item_id": media_item_id})


class TestCandidates:
    def test_lists_only_linked_visible_image_files_with_a_url(self, env):
        c, db, app, lib = env
        _act_as(app, _user(db))
        game, _ = _game(db)
        _, items = _media_bundle(db, "Art", [_image(lib / "media" / "a.png"), lib / "media" / "gone.png"], game=game)
        _media_bundle(db, "Soundtrack", [_image(lib / "media" / "ost.mp3", b"x")], kind="audio", game=game)
        _media_bundle(db, "Unlinked", [_image(lib / "media" / "other.png")])

        resp = _candidates(c, game)

        assert resp.status_code == 200, resp.text
        assert [row["media_item_id"] for row in resp.json()] == [items[0].id]
        assert resp.json()[0]["file_url"] == "/media/media/a.png"

    def test_marks_the_file_that_is_the_current_cover(self, env):
        c, db, app, lib = env
        _act_as(app, _user(db))
        game, leaves = _game(db)
        art = _image(lib / "media" / "a.png")
        _media_bundle(db, "Art", [art, _image(lib / "media" / "b.png")], game=game)
        leaves[0].cover_art_path = str(art).replace("\\", "/")
        db.commit()

        rows = _candidates(c, game).json()

        assert [row["is_current"] for row in rows] == [True, False]

    def test_a_blocklisted_media_bundle_is_not_listed(self, env):
        from backend.models.media_restriction import MediaRestriction

        c, db, app, lib = env
        user = _user(db)
        _act_as(app, user)
        game, _ = _game(db)
        bundle, _ = _media_bundle(db, "Art", [_image(lib / "media" / "a.png")], game=game)
        db.add(MediaRestriction(user_item_id=user.id, media_item_bundle_id=bundle.id))
        db.commit()

        assert _candidates(c, game).json() == []

    def test_media_also_linked_to_a_game_the_caller_cannot_see_is_not_listed(self, env):
        c, db, app, lib = env
        _act_as(app, _user(db, max_content_rating="E"))
        game, _ = _game(db, slug="kids", content_rating="E")
        hidden, _ = _game(db, slug="adult", content_rating="M")
        bundle, _ = _media_bundle(db, "Art", [_image(lib / "media" / "a.png")], game=game)
        from backend.models.media import make_entity_link

        db.add(make_entity_link("media_item_bundle", bundle.id, "game_item_bundle", hidden.id))
        db.commit()

        assert _candidates(c, game).json() == []

    def test_hidden_game_is_the_same_404_as_a_missing_game(self, env):
        c, db, app, _ = env
        _act_as(app, _user(db, max_content_rating="E"))
        hidden, _ = _game(db, content_rating="M")

        a = _candidates(c, hidden)
        b = c.get("/api/v1/game-item-bundle/999999/cover-candidates")

        assert a.status_code == b.status_code == 404
        assert a.json() == b.json()

    def test_403_without_can_manage_game(self, env):
        c, db, app, _ = env
        _act_as(app, _user(db, can_manage_game=False))
        game, _ = _game(db)

        assert _candidates(c, game).status_code == 403


class TestSetCover:
    def test_writes_the_file_to_the_display_disc_not_the_launch_disc(self, env):
        c, db, app, lib = env
        _act_as(app, _user(db))
        game, leaves = _game(db, discs=2)
        game.launch_disk_id, game.display_disk_id = leaves[0].id, leaves[1].id
        db.commit()
        art = _image(lib / "media" / "a.png")
        _, items = _media_bundle(db, "Art", [art], game=game)

        resp = _set(c, game, items[0].id)

        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == leaves[1].id
        db.refresh(leaves[0])
        db.refresh(leaves[1])
        assert leaves[1].cover_art_path == str(art.resolve())
        assert leaves[0].cover_art_path is None

    def test_missing_unlinked_hidden_and_non_image_ids_all_answer_the_same_404(self, env):
        from backend.models.media_restriction import MediaRestriction

        c, db, app, lib = env
        user = _user(db)
        _act_as(app, user)
        game, leaves = _game(db)
        _, unlinked = _media_bundle(db, "Unlinked", [_image(lib / "media" / "u.png")])
        _, audio = _media_bundle(db, "Ost", [_image(lib / "media" / "o.mp3", b"x")], kind="audio", game=game)
        hidden_bundle, hidden = _media_bundle(db, "Secret", [_image(lib / "media" / "s.png")], game=game)
        db.add(MediaRestriction(user_item_id=user.id, media_item_bundle_id=hidden_bundle.id))
        db.commit()

        answers = [_set(c, game, i) for i in (999999, unlinked[0].id, audio[0].id, hidden[0].id)]

        assert {r.status_code for r in answers} == {404}
        assert len({r.text for r in answers}) == 1
        db.refresh(leaves[0])
        assert leaves[0].cover_art_path is None

    def test_a_file_outside_the_library_is_never_written(self, env, tmp_path_factory):
        c, db, app, _ = env
        _act_as(app, _user(db))
        game, leaves = _game(db)
        outside = _image(tmp_path_factory.mktemp("elsewhere") / "x.png")
        _, items = _media_bundle(db, "Art", [outside], game=game)

        resp = _set(c, game, items[0].id)

        assert resp.status_code in (404, 422)
        db.refresh(leaves[0])
        assert leaves[0].cover_art_path is None

    def test_403_without_can_manage_game(self, env):
        c, db, app, lib = env
        _act_as(app, _user(db, can_manage_game=False))
        game, _ = _game(db)
        _, items = _media_bundle(db, "Art", [_image(lib / "media" / "a.png")], game=game)

        assert _set(c, game, items[0].id).status_code == 403
