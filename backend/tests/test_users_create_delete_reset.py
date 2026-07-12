"""Tests for backend/api/routes/users.py — create_user, delete_user, reset_pin.

Per dev_docs/v2/09_test_coverage.md item 2. update_user's permission matrix is
already covered by test_pin_auth.py::TestUpdateUser; this file only covers
create_user, delete_user, and reset_pin.

Uses an in-memory SQLModel SQLite DB with StaticPool and get_active_user/get_db
dependency overrides (same pattern as test_dependencies_content_rating.py),
not test_pin_auth.py's cookie-based flow.
"""

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mem_db_session():
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


def _make_user(db, **overrides):
    from backend.models.user import User

    kwargs = dict(name="User", is_owner=False, is_admin=False)
    kwargs.update(overrides)
    user = User(**kwargs)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def http_client(mem_db_session):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import users
    from backend.core.database import get_db

    app = FastAPI()
    app.include_router(users.router)
    app.dependency_overrides[get_db] = lambda: mem_db_session

    with TestClient(app) as c:
        yield c, mem_db_session, app


def _set_active_user(app, user):
    from backend.core.dependencies import get_active_user

    app.dependency_overrides[get_active_user] = lambda: user


# ---------------------------------------------------------------------------
# create_user — capability flag round-trip
# ---------------------------------------------------------------------------

# The 7 capability flags UserCreate exposes (excludes is_admin, which is a
# role flag rather than a capability, and is_owner, which is not settable
# via UserCreate at all).
_CAPABILITY_FLAGS = [
    "can_launch_media",
    "can_edit_environments",
    "can_manage_software",
    "can_edit_media",
    "can_manage_controllers",
    "can_edit_settings",
    "can_manage_users",
]


class TestCreateUserCapabilityFlags:
    def test_all_capability_flags_persist_when_granted(self, http_client):
        """Round-trip: every capability flag granted at creation must persist
        as True. This is the exact gap the prior audit found under-threaded
        (can_edit_media / can_manage_controllers were ungrantable)."""
        c, db, app = http_client
        owner = _make_user(db, name="Owner", is_owner=True)
        _set_active_user(app, owner)

        body = {"name": "Kid", **{flag: True for flag in _CAPABILITY_FLAGS}, "is_admin": True}
        resp = c.post("/api/v1/users", json=body)

        assert resp.status_code == 201, resp.text
        payload = resp.json()
        for flag in _CAPABILITY_FLAGS:
            assert payload[flag] is True, f"{flag} did not persist as True"
        assert payload["is_admin"] is True

    def test_no_flags_granted_persists_all_false(self, http_client):
        """Negative case: explicitly granting nothing must persist every flag
        as False, not just leave the true-path unproven."""
        c, db, app = http_client
        owner = _make_user(db, name="Owner", is_owner=True)
        _set_active_user(app, owner)

        body = {"name": "Kid", **{flag: False for flag in _CAPABILITY_FLAGS}, "is_admin": False}
        resp = c.post("/api/v1/users", json=body)

        assert resp.status_code == 201, resp.text
        payload = resp.json()
        for flag in _CAPABILITY_FLAGS:
            assert payload[flag] is False, f"{flag} did not persist as False"
        assert payload["is_admin"] is False


# ---------------------------------------------------------------------------
# delete_user — profile reassignment + MediaRestriction cleanup
# ---------------------------------------------------------------------------


class TestDeleteUserCleanup:
    def test_profiles_reassigned_to_owner_on_delete(self, http_client):
        from backend.models.profile import Profile

        c, db, app = http_client
        owner = _make_user(db, name="Owner", is_owner=True)
        sub = _make_user(db, name="Sub")
        profile = Profile(
            name="My Profile",
            slug="my-profile",
            emulator_slug="dosbox-x",
            era="dos",
            user_id=sub.id,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        _set_active_user(app, owner)

        resp = c.delete(f"/api/v1/users/{sub.id}")
        assert resp.status_code == 204, resp.text

        db.expire_all()
        reloaded = db.get(Profile, profile.id)
        assert reloaded is not None
        assert reloaded.user_id == owner.id

    def test_media_restrictions_deleted_not_orphaned(self, http_client):
        from backend.models.media_restriction import MediaRestriction
        from backend.models.game import GameItemBundle

        c, db, app = http_client
        owner = _make_user(db, name="Owner", is_owner=True)
        sub = _make_user(db, name="Sub")
        collection = GameItemBundle(
            title="Doom", file_path="/library/games/dos/doom", era="dos", slug="doom",
        )
        db.add(collection)
        db.commit()
        db.refresh(collection)
        restriction = MediaRestriction(user_id=sub.id, game_item_bundle_id=collection.id)
        db.add(restriction)
        db.commit()
        db.refresh(restriction)
        restriction_id = restriction.id
        _set_active_user(app, owner)

        resp = c.delete(f"/api/v1/users/{sub.id}")
        assert resp.status_code == 204, resp.text

        db.expire_all()
        assert db.get(MediaRestriction, restriction_id) is None


# ---------------------------------------------------------------------------
# reset_pin — locked-account guard
# ---------------------------------------------------------------------------


class TestResetPinLockedGuard:
    def test_self_reset_via_can_manage_users_rejected_while_locked(self, http_client):
        """A locked sub-account cannot reset its own PIN through the
        can_manage_users self-service path — an admin must do it
        (users.py:236-237)."""
        c, db, app = http_client
        locked = _make_user(db, name="Locked", can_manage_users=True, is_locked=True)
        _set_active_user(app, locked)

        resp = c.post(f"/api/v1/users/{locked.id}/reset-pin", json={"pin": "123456"})

        assert resp.status_code == 403, resp.text
        assert "locked" in resp.json()["detail"].lower()

    def test_admin_can_reset_pin_of_locked_account(self, http_client):
        """An admin resetting a locked sub-account's PIN succeeds and clears
        the lock, per the guard's `not (active_user.is_owner or
        active_user.is_admin)` condition."""
        c, db, app = http_client
        admin = _make_user(db, name="Admin", is_admin=True)
        locked = _make_user(db, name="Locked", is_locked=True, failed_pin_attempts=4)
        _set_active_user(app, admin)

        resp = c.post(f"/api/v1/users/{locked.id}/reset-pin", json={"pin": "123456"})

        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert payload["is_locked"] is False
        assert payload["failed_pin_attempts"] == 0

    def test_owner_can_reset_pin_of_locked_account(self, http_client):
        c, db, app = http_client
        owner = _make_user(db, name="Owner", is_owner=True)
        locked = _make_user(db, name="Locked", is_locked=True, failed_pin_attempts=4)
        _set_active_user(app, owner)

        resp = c.post(f"/api/v1/users/{locked.id}/reset-pin", json={"pin": "123456"})

        assert resp.status_code == 200, resp.text
        assert resp.json()["is_locked"] is False

    def test_locked_admin_self_reset_rejected(self, http_client):
        """An admin targeting their OWN locked account is rejected with 403.
        The guard at users.py rejects any admin target unless the active
        user is the owner, so an admin can never reset an admin PIN
        (including their own), regardless of lock state."""
        c, db, app = http_client
        locked_admin = _make_user(db, name="Admin", is_admin=True, is_locked=True, failed_pin_attempts=4)
        _set_active_user(app, locked_admin)

        resp = c.post(f"/api/v1/users/{locked_admin.id}/reset-pin", json={"pin": "123456"})

        assert resp.status_code == 403, resp.text

    def test_admin_cannot_reset_other_admin_pin(self, http_client):
        """An admin resetting another admin's PIN is rejected with 403,
        regardless of the target's lock state."""
        c, db, app = http_client
        admin = _make_user(db, name="Admin", is_admin=True)
        other_admin = _make_user(db, name="OtherAdmin", is_admin=True, is_locked=True, failed_pin_attempts=4)
        _set_active_user(app, admin)

        resp = c.post(f"/api/v1/users/{other_admin.id}/reset-pin", json={"pin": "123456"})

        assert resp.status_code == 403, resp.text
