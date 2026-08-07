"""Route-level (TestClient/HTTP) tests for backend/api/routes/settings.py.

Per dev_docs/P1_AUDIT.md TST-10, only GET /owner-status had coverage
(test_owner_guard.py); the step-up secret endpoints and the generic settings
PATCH were untested, including the route that rotates PIN_PEPPER (the secret
protecting every user's PIN hash). Covers:

    - is_owner gating (403 for non-owner) on GET /pin-pepper/status,
      GET /thegamesdb-api-key/status, GET /igdb-status, PATCH /pin-pepper
    - can_manage_settings gating (403 for non-editor) on PATCH /settings,
      plus its structural rejections that run before any settings I/O:
      PIN_PEPPER routed to the wrong endpoint (400), a disallowed key (403),
      and an invalid launch_history_retention value (422)
    - PATCH /pin-pepper's same-pepper no-op short-circuit, and a rotation
      with no existing owner pin_hash (owner_rehashed stays False, affected
      sub-accounts have pin_hash cleared and pin_required re-armed)

get_env_secret/set_env_secret are monkeypatched rather than exercising the
real .env file, since its contents are machine-specific and this suite must
not depend on (or mutate) whatever the local .env happens to hold. Routes
that touch backend.core.settings.get_settings() (the generic settings state
facade, distinct from env_secrets) are out of scope here, that facade
requires init_settings() to have run, which is a real DB/.env-backed process
boot step this route-level suite does not perform; the PATCH /settings
checks below all raise before reaching that call.
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


@pytest.fixture
def http_client(mem_db_session):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import settings as settings_routes
    from backend.core.database import get_db

    app = FastAPI()
    app.include_router(settings_routes.router)
    app.dependency_overrides[get_db] = lambda: mem_db_session

    with TestClient(app) as c:
        yield c, mem_db_session, app


def _set_active_user(app, user):
    from backend.core.dependencies import get_active_user

    app.dependency_overrides[get_active_user] = lambda: user


# ---------------------------------------------------------------------------
# is_owner gate, step-up secret status endpoints
# ---------------------------------------------------------------------------


class TestSecretStatusGate:
    def test_pin_pepper_status_403_for_non_owner(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db))

        resp = c.get("/api/v1/settings/pin-pepper/status")

        assert resp.status_code == 403, resp.text

    def test_pin_pepper_status_200_for_owner(self, http_client, monkeypatch):
        from backend.service.utils import env_secrets

        c, db, app = http_client
        monkeypatch.setattr(env_secrets, "get_env_secret", lambda key: "some-pepper")
        _set_active_user(app, _make_user(db, is_owner=True))

        resp = c.get("/api/v1/settings/pin-pepper/status")

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"enabled": True}

    def test_thegamesdb_status_403_for_non_owner(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db))

        resp = c.get("/api/v1/settings/thegamesdb-api-key/status")

        assert resp.status_code == 403, resp.text

    def test_thegamesdb_status_200_for_owner_reports_disabled_when_unset(self, http_client, monkeypatch):
        from backend.service.utils import env_secrets

        c, db, app = http_client
        monkeypatch.setattr(env_secrets, "get_env_secret", lambda key: "")
        _set_active_user(app, _make_user(db, is_owner=True))

        resp = c.get("/api/v1/settings/thegamesdb-api-key/status")

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"enabled": False}

    def test_igdb_status_403_for_non_owner(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db))

        resp = c.get("/api/v1/settings/igdb-status")

        assert resp.status_code == 403, resp.text

    def test_igdb_status_requires_both_credentials(self, http_client, monkeypatch):
        """Only one of the two IGDB secrets set must still report disabled."""
        from backend.service.utils import env_secrets

        c, db, app = http_client
        monkeypatch.setattr(
            env_secrets, "get_env_secret",
            lambda key: "client-id-value" if key == "IGDB_CLIENT_ID" else "",
        )
        _set_active_user(app, _make_user(db, is_owner=True))

        resp = c.get("/api/v1/settings/igdb-status")

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"enabled": False}


# ---------------------------------------------------------------------------
# can_manage_settings gate + structural checks, PATCH /settings
# ---------------------------------------------------------------------------


class TestPatchSettingsGate:
    def test_403_for_non_editor(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, can_manage_settings=False))

        resp = c.patch("/api/v1/settings", json={"updates": {"suppress_confirmations": True}})

        assert resp.status_code == 403, resp.text

    def test_pin_pepper_key_rejected_with_400(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, can_manage_settings=True))

        resp = c.patch("/api/v1/settings", json={"updates": {"PIN_PEPPER": "x"}})

        assert resp.status_code == 400, resp.text

    def test_disallowed_key_rejected_with_403(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, can_manage_settings=True))

        resp = c.patch("/api/v1/settings", json={"updates": {"ALLOW_NETWORK_ACCESS": True}})

        assert resp.status_code == 403, resp.text

    def test_invalid_launch_history_retention_rejected_with_422(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, can_manage_settings=True))

        resp = c.patch("/api/v1/settings", json={"updates": {"launch_history_retention": "not-a-real-value"}})

        assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# PATCH /pin-pepper
# ---------------------------------------------------------------------------


class TestPatchPinPepper:
    def test_403_for_non_owner(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db))

        resp = c.patch("/api/v1/settings/pin-pepper", json={"pepper": "new-pepper"})

        assert resp.status_code == 403, resp.text

    def test_same_pepper_is_a_noop(self, http_client, monkeypatch):
        from backend.service.utils import env_secrets

        c, db, app = http_client
        monkeypatch.setattr(env_secrets, "get_env_secret", lambda key: "current-pepper")
        set_calls = []
        monkeypatch.setattr(env_secrets, "set_env_secret", lambda key, value: set_calls.append((key, value)))
        _set_active_user(app, _make_user(db, is_owner=True))

        resp = c.patch("/api/v1/settings/pin-pepper", json={"pepper": "current-pepper"})

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"pepper_enabled": True, "owner_rehashed": False, "sub_accounts_reset": []}
        assert set_calls == []

    def test_rotation_with_no_existing_owner_pin_clears_sub_account_pins(self, http_client, monkeypatch):
        """Owner has no pin_hash set yet (pin_hash=None), so the re-hash/
        verify branch is skipped entirely; sub-accounts with a pin_hash are
        still cleared and re-armed for the admin reset-pin flow."""
        from backend.service.utils import env_secrets

        c, db, app = http_client
        monkeypatch.setattr(env_secrets, "get_env_secret", lambda key: "old-pepper")
        set_calls = []
        monkeypatch.setattr(env_secrets, "set_env_secret", lambda key, value: set_calls.append((key, value)))

        owner = _make_user(db, name="Owner", is_owner=True, pin_hash=None)
        sub = _make_user(db, name="Sub", pin_hash="some-hash", pin_required=False)
        _set_active_user(app, owner)

        resp = c.patch("/api/v1/settings/pin-pepper", json={"pepper": "new-pepper"})

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["owner_rehashed"] is False
        assert body["sub_accounts_reset"] == ["Sub"]
        assert set_calls == [("PIN_PEPPER", "new-pepper")]

        db.refresh(sub)
        assert sub.pin_hash is None
        assert sub.pin_required is True
