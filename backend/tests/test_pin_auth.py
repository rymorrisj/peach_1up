"""Tests for PIN-based account switching and account lockout.

The spec referenced POST /api/v1/auth/verify-pin, but no such endpoint
exists. The actual PIN verification flow is POST /api/v1/auth/switch
(api/routes/auth.py:switch_user), which is what these tests exercise.
Account unlock is POST /api/v1/users/{user_id}/unlock (api/routes/users.py).
"""

import pytest
from argon2 import PasswordHasher


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
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import auth, users
    from backend.core.database import get_db

    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(users.router)
    app.dependency_overrides[get_db] = lambda: mem_session

    with TestClient(app) as client:
        yield client


@pytest.fixture
def owner(mem_session):
    from backend.models.user import User

    ph = PasswordHasher()
    u = User(
        name="Owner",
        is_owner=True,
        is_admin=True,
        pin_required=True,
        can_launch_media=True,
        pin_hash=ph.hash("1234"),
    )
    mem_session.add(u)
    mem_session.commit()
    mem_session.refresh(u)
    return u


class TestPinVerification:
    def test_correct_pin_returns_200_and_sets_cookie(self, app_client, owner):
        resp = app_client.post("/api/v1/auth/switch", json={"user_id": owner.id, "pin": "1234"})

        assert resp.status_code == 200
        assert "peach_token" in resp.cookies

    def test_wrong_pin_returns_401_and_increments_failed_attempts(self, app_client, mem_session, owner):
        from backend.models.user import User

        resp = app_client.post("/api/v1/auth/switch", json={"user_id": owner.id, "pin": "0000"})

        assert resp.status_code == 401
        refreshed = mem_session.get(User, owner.id)
        assert refreshed.failed_pin_attempts == 1

    def test_fourth_wrong_pin_locks_account(self, app_client, mem_session, owner):
        from backend.models.user import User

        for _ in range(3):
            resp = app_client.post("/api/v1/auth/switch", json={"user_id": owner.id, "pin": "0000"})
            assert resp.status_code == 401

        resp = app_client.post("/api/v1/auth/switch", json={"user_id": owner.id, "pin": "0000"})
        assert resp.status_code == 401

        refreshed = mem_session.get(User, owner.id)
        assert refreshed.failed_pin_attempts == 4
        assert refreshed.is_locked is True

    def test_locked_account_rejects_correct_pin_with_403(self, app_client, mem_session, owner):
        from backend.models.user import User

        owner_row = mem_session.get(User, owner.id)
        owner_row.is_locked = True
        mem_session.add(owner_row)
        mem_session.commit()

        resp = app_client.post("/api/v1/auth/switch", json={"user_id": owner.id, "pin": "1234"})
        assert resp.status_code == 403


class TestSessionInvalidation:
    def test_new_login_invalidates_old_session(self, app_client, owner):
        resp1 = app_client.post("/api/v1/auth/switch", json={"user_id": owner.id, "pin": "1234"})
        assert resp1.status_code == 200
        cookie1 = resp1.cookies.get("peach_token")

        resp2 = app_client.post("/api/v1/auth/switch", json={"user_id": owner.id, "pin": "1234"})
        assert resp2.status_code == 200
        cookie2 = resp2.cookies.get("peach_token")

        assert cookie1 != cookie2

        stale = app_client.get("/api/v1/users", cookies={"peach_token": cookie1})
        assert stale.status_code == 401

        fresh = app_client.get("/api/v1/users", cookies={"peach_token": cookie2})
        assert fresh.status_code == 200


class TestForceLogout:
    def test_force_logout_invalidates_target_session(self, app_client, mem_session, owner):
        from backend.models.user import User

        sub = User(name="Kid", is_owner=False, is_admin=False, pin_required=False)
        mem_session.add(sub)
        mem_session.commit()
        mem_session.refresh(sub)

        sub_resp = app_client.post("/api/v1/auth/switch", json={"user_id": sub.id, "pin": ""})
        assert sub_resp.status_code == 200
        sub_cookie = sub_resp.cookies.get("peach_token")
        assert app_client.get("/api/v1/users", cookies={"peach_token": sub_cookie}).status_code == 200

        owner_resp = app_client.post("/api/v1/auth/switch", json={"user_id": owner.id, "pin": "1234"})
        owner_cookie = owner_resp.cookies.get("peach_token")

        force_resp = app_client.post(
            f"/api/v1/users/{sub.id}/force-logout",
            cookies={"peach_token": owner_cookie},
        )
        assert force_resp.status_code == 200

        after = app_client.get("/api/v1/users", cookies={"peach_token": sub_cookie})
        assert after.status_code == 401

    def test_force_logout_against_owner_returns_403(self, app_client, owner):
        owner_resp = app_client.post("/api/v1/auth/switch", json={"user_id": owner.id, "pin": "1234"})
        owner_cookie = owner_resp.cookies.get("peach_token")

        resp = app_client.post(
            f"/api/v1/users/{owner.id}/force-logout",
            cookies={"peach_token": owner_cookie},
        )
        assert resp.status_code == 403


class TestSetupOwnerSession:
    def test_setup_owner_session_validates(self, app_client, mem_session):
        from backend.core.identity import parse_session_cookie, validate_session

        resp = app_client.post(
            "/api/v1/auth/setup-owner",
            json={"name": "Boss", "pin": "5678", "confirm_pin": "5678"},
        )
        assert resp.status_code == 200, resp.text
        cookie = resp.cookies.get("peach_token")
        assert cookie is not None

        parsed = parse_session_cookie(cookie)
        assert parsed is not None
        user = validate_session(mem_session, parsed[0], parsed[1])
        assert user is not None
        assert user.name == "Boss"

    def test_setup_owner_sets_identity_token_secret_explicitly(self, app_client, mem_session):
        """Regression: setup_owner must not depend on issue_session's lazy
        backfill — it's the primary first-run creation path, not a defensive
        fallback case like the CLI owner-recovery script."""
        from backend.models.user import User

        resp = app_client.post(
            "/api/v1/auth/setup-owner",
            json={"name": "Boss", "pin": "5678", "confirm_pin": "5678"},
        )
        assert resp.status_code == 200, resp.text

        owner = mem_session.query(User).filter(User.is_owner.is_(True)).first()
        assert owner.identity_token_secret is not None


class TestUnlockSubAccount:
    def test_owner_can_unlock_sub_account(self, app_client, mem_session, owner):
        from backend.core.identity import issue_session
        from backend.models.user import User

        sub = User(
            name="Kid",
            is_owner=False,
            is_admin=False,
            pin_required=True,
            is_locked=True,
            failed_pin_attempts=4,
            pin_hash=PasswordHasher().hash("4321"),
        )
        mem_session.add(sub)
        mem_session.commit()
        mem_session.refresh(sub)

        owner_token, _expires_at = issue_session(mem_session, owner)

        resp = app_client.post(
            f"/api/v1/users/{sub.id}/unlock",
            cookies={"peach_token": f"{owner.id}.{owner_token}"},
        )

        assert resp.status_code == 200
        refreshed = mem_session.get(User, sub.id)
        assert refreshed.is_locked is False
        assert refreshed.failed_pin_attempts == 0
