"""Route-level (TestClient/HTTP) tests for backend/api/routes/restrictions.py.

GET/PUT /api/v1/restrictions/{domain}/{entity_id}, is_admin gate.

"game" domain only. The media and app domains have no coverage.

In-memory SQLModel SQLite + StaticPool + get_active_user/get_db dependency
overrides, as in test_game_item_bundles_routes.py.
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


def _make_collection(db, **overrides):
    from backend.models.game import GameItemBundle

    kwargs = dict(title="Doom", file_path="/library/games/dos/doom", era="dos", slug="doom")
    kwargs.update(overrides)
    collection = GameItemBundle(**kwargs)
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return collection


@pytest.fixture
def http_client(mem_db_session):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import restrictions
    from backend.core.database import get_db

    app = FastAPI()
    app.include_router(restrictions.router)
    app.dependency_overrides[get_db] = lambda: mem_db_session

    with TestClient(app) as c:
        yield c, mem_db_session, app


def _set_active_user(app, user):
    from backend.core.dependencies import get_active_user

    app.dependency_overrides[get_active_user] = lambda: user


# ---------------------------------------------------------------------------
# GET/PUT /api/v1/restrictions/game/{entity_id}, is_admin gate
# ---------------------------------------------------------------------------


class TestRestrictionsEndpoint:
    def test_non_admin_gets_403_on_get(self, http_client):
        c, db, app = http_client
        collection = _make_collection(db)
        non_admin = _make_user(db, can_manage_game=True, is_admin=False)
        _set_active_user(app, non_admin)

        resp = c.get(f"/api/v1/restrictions/game/{collection.id}")
        assert resp.status_code == 403, resp.text

    def test_admin_gets_restriction_list(self, http_client):
        from backend.models.media_restriction import MediaRestriction

        c, db, app = http_client
        collection = _make_collection(db)
        restricted_user = _make_user(db, name="Kid")
        db.add(MediaRestriction(user_item_id=restricted_user.id, game_item_bundle_id=collection.id))
        db.commit()
        admin = _make_user(db, name="Admin", is_admin=True)
        _set_active_user(app, admin)

        resp = c.get(f"/api/v1/restrictions/game/{collection.id}")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"restricted_user_item_ids": [restricted_user.id]}

    def test_non_admin_gets_403_on_put(self, http_client):
        c, db, app = http_client
        collection = _make_collection(db)
        non_admin = _make_user(db, can_manage_game=True, is_admin=False)
        _set_active_user(app, non_admin)

        resp = c.put(
            f"/api/v1/restrictions/game/{collection.id}",
            json={"user_item_ids": [non_admin.id]},
        )
        assert resp.status_code == 403, resp.text

    def test_admin_put_delete_then_reinsert_persists(self, http_client):
        """set_restrictions deletes all existing rows for the collection then
        reinserts the new list, confirm a second PUT with a different set
        actually replaces (not merges with) the first."""
        from backend.models.media_restriction import MediaRestriction

        c, db, app = http_client
        collection = _make_collection(db)
        user_a = _make_user(db, name="A")
        user_b = _make_user(db, name="B")
        admin = _make_user(db, name="Admin", is_admin=True)
        _set_active_user(app, admin)

        first = c.put(
            f"/api/v1/restrictions/game/{collection.id}",
            json={"user_item_ids": [user_a.id]},
        )
        assert first.status_code == 200, first.text
        assert first.json() == {"restricted_user_item_ids": [user_a.id]}

        second = c.put(
            f"/api/v1/restrictions/game/{collection.id}",
            json={"user_item_ids": [user_b.id]},
        )
        assert second.status_code == 200, second.text
        assert second.json() == {"restricted_user_item_ids": [user_b.id]}

        db.expire_all()
        rows = db.query(MediaRestriction).filter(
            MediaRestriction.game_item_bundle_id == collection.id
        ).all()
        persisted_ids = {r.user_item_id for r in rows}
        assert persisted_ids == {user_b.id}
