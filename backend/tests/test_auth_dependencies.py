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
    import backend.models.auth_token  # noqa: F401 — registers AuthToken with SQLModel.metadata

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
    from backend.models.user import User

    app = FastAPI()

    @app.get("/whoami")
    def whoami(user: User = Depends(get_active_user)):
        return {"id": user.id, "name": user.name}

    @app.get("/needs-flag")
    def needs_flag(user: User = require_permission("can_edit_library")):
        return {"id": user.id}

    @app.get("/users/{user_id}/private")
    def private(user_id: int, user: User = Depends(require_self_or_admin)):
        return {"id": user.id}

    app.dependency_overrides[get_db] = lambda: mem_session

    with TestClient(app) as client:
        yield client


@pytest.fixture
def make_user(mem_session):
    from backend.models.user import User

    def _make(**kwargs):
        defaults = dict(name="User", is_owner=False, is_admin=False, can_edit_library=False)
        defaults.update(kwargs)
        u = User(**defaults)
        mem_session.add(u)
        mem_session.commit()
        mem_session.refresh(u)
        return u

    return _make


@pytest.fixture
def make_token(mem_session):
    from backend.core.token_store import create_token

    def _make(user, session_expiry_minutes=None):
        return create_token(mem_session, user.id, session_expiry_minutes)

    return _make


class TestGetActiveUser:
    def test_valid_cookie_resolves_to_correct_user(self, app_client, make_user, make_token):
        user = make_user(name="Alice")
        token = make_token(user)

        resp = app_client.get("/whoami", cookies={"peach_token": token})

        assert resp.status_code == 200
        assert resp.json() == {"id": user.id, "name": "Alice"}

    def test_missing_cookie_returns_401(self, app_client):
        resp = app_client.get("/whoami")
        assert resp.status_code == 401

    def test_revoked_token_returns_401(self, app_client, mem_session, make_user, make_token):
        from backend.core.token_store import revoke_token

        user = make_user(name="Bob")
        token = make_token(user)
        revoke_token(mem_session, token)

        resp = app_client.get("/whoami", cookies={"peach_token": token})
        assert resp.status_code == 401

    def test_expired_token_returns_401(self, app_client, mem_session, make_user):
        from backend.models.auth_token import AuthToken

        user = make_user(name="Carol")
        row = AuthToken(
            token="expired-tok",
            user_id=user.id,
            issued_at=datetime.now(timezone.utc) - timedelta(days=2),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            revoked=False,
        )
        mem_session.add(row)
        mem_session.commit()

        resp = app_client.get("/whoami", cookies={"peach_token": "expired-tok"})
        assert resp.status_code == 401


class TestRequirePermission:
    def test_passes_when_flag_true(self, app_client, make_user, make_token):
        user = make_user(name="Editor", can_edit_library=True)
        token = make_token(user)

        resp = app_client.get("/needs-flag", cookies={"peach_token": token})
        assert resp.status_code == 200

    def test_raises_403_when_flag_false(self, app_client, make_user, make_token):
        user = make_user(name="ReadOnly", can_edit_library=False)
        token = make_token(user)

        resp = app_client.get("/needs-flag", cookies={"peach_token": token})
        assert resp.status_code == 403

    def test_owner_bypasses_flag(self, app_client, make_user, make_token):
        user = make_user(name="Owner", is_owner=True, can_edit_library=False)
        token = make_token(user)

        resp = app_client.get("/needs-flag", cookies={"peach_token": token})
        assert resp.status_code == 200


class TestRequireSelfOrAdmin:
    def test_user_can_access_own_resource(self, app_client, make_user, make_token):
        user = make_user(name="Self")
        token = make_token(user)

        resp = app_client.get(f"/users/{user.id}/private", cookies={"peach_token": token})
        assert resp.status_code == 200

    def test_admin_can_access_any_resource(self, app_client, make_user, make_token):
        admin = make_user(name="Admin", is_admin=True)
        other = make_user(name="Other")
        token = make_token(admin)

        resp = app_client.get(f"/users/{other.id}/private", cookies={"peach_token": token})
        assert resp.status_code == 200

    def test_non_admin_cannot_access_other_users_resource(self, app_client, make_user, make_token):
        user = make_user(name="NonAdmin")
        other = make_user(name="Other")
        token = make_token(user)

        resp = app_client.get(f"/users/{other.id}/private", cookies={"peach_token": token})
        assert resp.status_code == 403
