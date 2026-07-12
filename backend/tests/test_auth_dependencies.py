"""Tests for backend.core.dependencies: get_active_user, require_permission,
and require_self_or_admin.

A minimal FastAPI app with throwaway endpoints exercises the dependencies
against an in-memory SQLite session, with get_db overridden.
"""

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def mem_session():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import SQLModel, Session, create_engine
    import backend.models  # noqa: F401 — registers all table models with SQLModel.metadata

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def app_client(mem_session):
    from fastapi import FastAPI, Depends
    from fastapi.testclient import TestClient
    from backend.core.database import get_db
    from backend.core.dependencies import get_active_user, require_permission, require_self_or_admin
    from backend.models.user import UserItem

    app = FastAPI()

    @app.get("/whoami")
    def whoami(user: UserItem = Depends(get_active_user)):
        return {"id": user.id, "name": user.name}

    @app.get("/needs-flag")
    def needs_flag(user: UserItem = require_permission("can_manage_game")):
        return {"id": user.id}

    @app.get("/users/{user_item_id}/private")
    def private(user_item_id: int, user: UserItem = Depends(require_self_or_admin)):
        return {"id": user.id}

    app.dependency_overrides[get_db] = lambda: mem_session

    with TestClient(app) as client:
        yield client


@pytest.fixture
def make_user(mem_session):
    from backend.models.user import UserItem

    def _make(**kwargs):
        defaults = dict(name="User", is_owner=False, is_admin=False, can_manage_game=False)
        defaults.update(kwargs)
        u = UserItem(**defaults)
        mem_session.add(u)
        mem_session.commit()
        mem_session.refresh(u)
        return u

    return _make


@pytest.fixture
def make_session(mem_session):
    """Issue a real session for *user* and return the peach_token cookie value."""
    from backend.core.identity import issue_session

    def _make(user):
        token, _expires_at = issue_session(mem_session, user)
        return f"{user.id}.{token}"

    return _make


class TestGetActiveUser:
    def test_valid_cookie_resolves_to_correct_user(self, app_client, make_user, make_session):
        user = make_user(name="Alice")
        cookie = make_session(user)

        resp = app_client.get("/whoami", cookies={"peach_token": cookie})

        assert resp.status_code == 200
        assert resp.json() == {"id": user.id, "name": "Alice"}

    def test_missing_cookie_returns_401(self, app_client):
        resp = app_client.get("/whoami")
        assert resp.status_code == 401

    def test_malformed_cookie_no_separator_returns_401(self, app_client):
        resp = app_client.get("/whoami", cookies={"peach_token": "no-dot-here"})
        assert resp.status_code == 401

    def test_malformed_cookie_non_digit_user_id_returns_401(self, app_client):
        resp = app_client.get("/whoami", cookies={"peach_token": "abc.sometoken"})
        assert resp.status_code == 401

    def test_logged_out_session_returns_401(self, app_client, mem_session, make_user, make_session):
        from backend.core.identity import clear_session

        user = make_user(name="Bob")
        cookie = make_session(user)
        clear_session(mem_session, user)

        resp = app_client.get("/whoami", cookies={"peach_token": cookie})
        assert resp.status_code == 401

    def test_expired_session_returns_401(self, app_client, mem_session, make_user):
        from backend.core.identity import hash_session_token

        user = make_user(name="Carol")
        user.session_token_hash = hash_session_token("some-token")
        user.session_token_expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        mem_session.add(user)
        mem_session.commit()

        resp = app_client.get("/whoami", cookies={"peach_token": f"{user.id}.some-token"})
        assert resp.status_code == 401

    def test_invalid_session_does_not_fall_back_to_owner(self, app_client, make_user):
        """Regression: an unresolvable cookie must never silently resolve to an
        owner account, even when owners exist in the database. No owner
        fallback existed in the prior token model either — this locks it in.
        """
        make_user(name="Owner1", is_owner=True)
        make_user(name="Owner2", is_owner=True)

        resp = app_client.get("/whoami", cookies={"peach_token": "999.bogus-token"})
        assert resp.status_code == 401


class TestRequirePermission:
    def test_passes_when_flag_true(self, app_client, make_user, make_session):
        user = make_user(name="Editor", can_manage_game=True)
        cookie = make_session(user)

        resp = app_client.get("/needs-flag", cookies={"peach_token": cookie})
        assert resp.status_code == 200

    def test_raises_403_when_flag_false(self, app_client, make_user, make_session):
        user = make_user(name="ReadOnly", can_manage_game=False)
        cookie = make_session(user)

        resp = app_client.get("/needs-flag", cookies={"peach_token": cookie})
        assert resp.status_code == 403

    def test_owner_bypasses_flag(self, app_client, make_user, make_session):
        user = make_user(name="Owner", is_owner=True, can_manage_game=False)
        cookie = make_session(user)

        resp = app_client.get("/needs-flag", cookies={"peach_token": cookie})
        assert resp.status_code == 200


class TestRequireSelfOrAdmin:
    def test_user_can_access_own_resource(self, app_client, make_user, make_session):
        user = make_user(name="Self")
        cookie = make_session(user)

        resp = app_client.get(f"/users/{user.id}/private", cookies={"peach_token": cookie})
        assert resp.status_code == 200

    def test_admin_can_access_any_resource(self, app_client, make_user, make_session):
        admin = make_user(name="Admin", is_admin=True)
        other = make_user(name="Other")
        cookie = make_session(admin)

        resp = app_client.get(f"/users/{other.id}/private", cookies={"peach_token": cookie})
        assert resp.status_code == 200

    def test_non_admin_cannot_access_other_users_resource(self, app_client, make_user, make_session):
        user = make_user(name="NonAdmin")
        other = make_user(name="Other")
        cookie = make_session(user)

        resp = app_client.get(f"/users/{other.id}/private", cookies={"peach_token": cookie})
        assert resp.status_code == 403
