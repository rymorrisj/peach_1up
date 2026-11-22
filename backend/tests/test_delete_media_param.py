"""DELETE /game-item-bundle/{id} and /app-item-bundle/{id} take an optional
delete_media query param: the delete-confirm checkbox's choice for that one
delete. It replaces the frontend's pre-delete PATCH of delete_media_override,
so nothing is persisted when a delete is refused (rating-change 409) and the
user cancels the follow-up prompt.
"""

import pytest


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
def media_deletes(monkeypatch):
    """Records which collections had their media deleted, and never touches
    disk. The global delete_media_on_removal fallback is pinned to False."""
    import backend.service.apps.items as app_svc
    import backend.service.games.items as game_svc

    deleted: list[tuple[str, int]] = []
    monkeypatch.setattr(game_svc, "_delete_leaf_media_folders", lambda c: deleted.append(("game", c.id)))
    monkeypatch.setattr(app_svc, "_delete_leaf_media_folders", lambda c: deleted.append(("app", c.id)))
    monkeypatch.setattr(game_svc, "_should_delete_media", lambda c: bool(c.delete_media_override))
    monkeypatch.setattr(app_svc, "_should_delete_media", lambda c: bool(c.delete_media_override))
    return deleted


@pytest.fixture
def client(mem_db_session, tmp_path, monkeypatch, media_deletes):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import backend.service.utils.settings as settings_mod
    from backend.api.routes import apps, game_item_bundles
    from backend.core.database import get_db
    from backend.core.dependencies import get_active_user
    from backend.models.user import UserItem

    monkeypatch.setattr(
        settings_mod, "get", lambda key, default=None: str(tmp_path) if key == "LIBRARY_PATH" else default,
    )
    app = FastAPI()
    app.include_router(game_item_bundles.router)
    app.include_router(apps.router)
    app.dependency_overrides[get_active_user] = lambda: UserItem(id=1, name="Owner", is_owner=True)
    app.dependency_overrides[get_db] = lambda: mem_db_session
    with TestClient(app) as c:
        yield c


def _game(db, rating=None, override=None):
    from backend.models.game import GameItemBundle

    game = GameItemBundle(title="Doom", platform="dos", slug="doom", content_rating=rating,
                          delete_media_override=override)
    db.add(game)
    db.commit()
    db.refresh(game)
    return game


def _app(db, override=None):
    from backend.models.app import AppItemBundle

    app = AppItemBundle(title="Tool", platform="ps1", slug="tool", delete_media_override=override)
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


def _token(client, base):
    return client.post(f"{base}/confirm-delete").json()["confirmation_token"]


class TestGameDelete:
    def test_cancelled_rating_prompt_persists_nothing(self, client, mem_db_session, media_deletes):
        """The refused attempt (409, the point the UI asks and the user can
        cancel) must leave delete_media_override exactly as it was."""
        from backend.models.game import GameItemBundle
        from backend.models.media import MediaItemBundle, make_entity_link

        db = mem_db_session
        game = _game(db, rating="M", override=None)
        # An unrated media bundle linked to an M game is effectively M;
        # deleting the game would clear that, so the delete needs confirm.
        media = MediaItemBundle(title="Art", media_kind="image", slug="art")
        db.add(media)
        db.commit()
        db.add(make_entity_link("media_item_bundle", media.id, "game_item_bundle", game.id))
        db.commit()

        base = f"/api/v1/game-item-bundle/{game.id}"
        resp = client.delete(base, params={"confirmation_token": _token(client, base), "delete_media": "true"})

        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"]["error_type"] == "rating_change_requires_confirmation"
        db.expire_all()
        assert db.get(GameItemBundle, game.id).delete_media_override is None
        assert media_deletes == []

    def test_param_true_overrides_a_false_override_for_this_delete(self, client, mem_db_session, media_deletes):
        game = _game(mem_db_session, override=False)
        base = f"/api/v1/game-item-bundle/{game.id}"

        resp = client.delete(base, params={"confirmation_token": _token(client, base), "delete_media": "true"})
        assert resp.status_code == 204, resp.text
        assert media_deletes == [("game", game.id)]

    def test_param_false_overrides_a_true_override_for_this_delete(self, client, mem_db_session, media_deletes):
        game = _game(mem_db_session, override=True)
        base = f"/api/v1/game-item-bundle/{game.id}"

        resp = client.delete(base, params={"confirmation_token": _token(client, base), "delete_media": "false"})
        assert resp.status_code == 204, resp.text
        assert media_deletes == []

    def test_omitted_param_falls_back_to_the_stored_override(self, client, mem_db_session, media_deletes):
        game = _game(mem_db_session, override=True)
        base = f"/api/v1/game-item-bundle/{game.id}"

        assert client.delete(base, params={"confirmation_token": _token(client, base)}).status_code == 204
        assert media_deletes == [("game", game.id)]


class TestAppDelete:
    @pytest.mark.parametrize("param,override,expected", [
        ("true", False, True), ("false", True, False), (None, True, True),
    ])
    def test_param_applies_to_this_delete_only(self, client, mem_db_session, media_deletes, param, override,
                                               expected):
        app = _app(mem_db_session, override=override)
        base = f"/api/v1/app-item-bundle/{app.id}"
        params = {"confirmation_token": _token(client, base)}
        if param is not None:
            params["delete_media"] = param

        assert client.delete(base, params=params).status_code == 204
        assert media_deletes == ([("app", app.id)] if expected else [])
