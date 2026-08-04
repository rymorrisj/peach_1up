"""Route-level (TestClient/HTTP) tests for backend/api/routes/drives.py.

Per dev_docs/P1_AUDIT.md TST-7 — drives.py had zero test coverage despite
gating a destructive on-disk image delete behind a confirmation-token flow
and a permission check that differs by drive ownership (can_manage_game for
game-owned drives, can_manage_app for app-owned drives). Covers:

    - 404 for a nonexistent drive on confirm-token issuance and delete
    - 403 for a non-editor on confirm-token issuance and delete, for both
      game-owned and app-owned drives, and that the permission gate runs
      before token consumption (a garbage token still yields 403, not 400)
    - owner bypasses the permission gate regardless of the flag
    - delete rejects a missing, mismatched, and expired confirmation token
    - end-to-end delete: the on-disk image file is removed, the owning
      bundle's drive_id is cleared, and the Drive row itself is deleted

Uses the same in-memory SQLModel SQLite DB + StaticPool +
get_active_user/get_db dependency-override pattern as
test_launches_routes.py / test_game_item_bundles_routes.py.
"""

import time

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
    from backend.models.user import UserItem

    kwargs = dict(name="UserItem", is_owner=False, is_admin=False)
    kwargs.update(overrides)
    user = UserItem(**kwargs)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_game_bundle(db, **overrides):
    from backend.models.game import GameItemBundle

    kwargs = dict(title="Doom", file_path="/library/games/dos/doom", era="dos", slug="doom")
    kwargs.update(overrides)
    bundle = GameItemBundle(**kwargs)
    db.add(bundle)
    db.commit()
    db.refresh(bundle)
    return bundle


def _make_app_bundle(db, **overrides):
    from backend.models.app import AppItemBundle

    kwargs = dict(title="Notepad++", era="winxp")
    kwargs.update(overrides)
    bundle = AppItemBundle(**kwargs)
    db.add(bundle)
    db.commit()
    db.refresh(bundle)
    return bundle


def _make_game_drive(db, game_bundle, **overrides):
    from backend.models.drive import Drive

    kwargs = dict(name="doom-drive", game_item_bundle_id=game_bundle.id)
    kwargs.update(overrides)
    drive = Drive(**kwargs)
    db.add(drive)
    db.commit()
    db.refresh(drive)
    game_bundle.drive_id = drive.id
    db.add(game_bundle)
    db.commit()
    return drive


def _make_app_drive(db, app_bundle, **overrides):
    from backend.models.drive import Drive

    kwargs = dict(name="app-drive", app_item_bundle_id=app_bundle.id)
    kwargs.update(overrides)
    drive = Drive(**kwargs)
    db.add(drive)
    db.commit()
    db.refresh(drive)
    app_bundle.drive_id = drive.id
    db.add(app_bundle)
    db.commit()
    return drive


@pytest.fixture
def http_client(mem_db_session):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import drives
    from backend.core.database import get_db

    app = FastAPI()
    app.include_router(drives.router)
    app.dependency_overrides[get_db] = lambda: mem_db_session

    with TestClient(app) as c:
        yield c, mem_db_session, app


def _set_active_user(app, user):
    from backend.core.dependencies import get_active_user

    app.dependency_overrides[get_active_user] = lambda: user


# ---------------------------------------------------------------------------
# GET /{drive_id} and /{drive_id}/confirm-token — 404 for nonexistent drive
# ---------------------------------------------------------------------------


class TestNotFound:
    def test_get_drive_404_when_missing(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, is_owner=True))

        resp = c.get("/api/v1/drives/999")

        assert resp.status_code == 404, resp.text

    def test_confirm_token_404_when_missing(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, is_owner=True))

        resp = c.get("/api/v1/drives/999/confirm-token")

        assert resp.status_code == 404, resp.text

    def test_delete_404_when_missing(self, http_client):
        c, db, app = http_client
        _set_active_user(app, _make_user(db, is_owner=True))

        resp = c.delete("/api/v1/drives/999?confirmation_token=garbage")

        assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# Permission gate — can_manage_game for game-owned drives
# ---------------------------------------------------------------------------


class TestGameOwnedPermissionGate:
    def test_confirm_token_403_for_non_editor(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db)
        drive = _make_game_drive(db, bundle)
        _set_active_user(app, _make_user(db, can_manage_game=False))

        resp = c.get(f"/api/v1/drives/{drive.id}/confirm-token")

        assert resp.status_code == 403, resp.text

    def test_confirm_token_200_for_editor(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db)
        drive = _make_game_drive(db, bundle)
        _set_active_user(app, _make_user(db, can_manage_game=True))

        resp = c.get(f"/api/v1/drives/{drive.id}/confirm-token")

        assert resp.status_code == 200, resp.text
        assert "confirmation_token" in resp.json()

    def test_delete_403_for_non_editor_even_with_garbage_token(self, http_client):
        """Permission gate must run before token consumption — a non-editor
        gets 403, not 400, even when no valid token could exist yet."""
        c, db, app = http_client
        bundle = _make_game_bundle(db)
        drive = _make_game_drive(db, bundle)
        _set_active_user(app, _make_user(db, can_manage_game=False))

        resp = c.delete(f"/api/v1/drives/{drive.id}?confirmation_token=garbage")

        assert resp.status_code == 403, resp.text

    def test_owner_bypasses_gate_without_the_flag(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db)
        drive = _make_game_drive(db, bundle)
        _set_active_user(app, _make_user(db, is_owner=True, can_manage_game=False))

        resp = c.get(f"/api/v1/drives/{drive.id}/confirm-token")

        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Permission gate — can_manage_app for app-owned drives
# ---------------------------------------------------------------------------


class TestAppOwnedPermissionGate:
    def test_confirm_token_403_for_non_editor(self, http_client):
        c, db, app = http_client
        bundle = _make_app_bundle(db)
        drive = _make_app_drive(db, bundle)
        _set_active_user(app, _make_user(db, can_manage_app=False, can_manage_game=True))

        resp = c.get(f"/api/v1/drives/{drive.id}/confirm-token")

        # can_manage_game must not leak permission onto an app-owned drive.
        assert resp.status_code == 403, resp.text

    def test_confirm_token_200_for_editor(self, http_client):
        c, db, app = http_client
        bundle = _make_app_bundle(db)
        drive = _make_app_drive(db, bundle)
        _set_active_user(app, _make_user(db, can_manage_app=True))

        resp = c.get(f"/api/v1/drives/{drive.id}/confirm-token")

        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Confirmation-token validation on delete
# ---------------------------------------------------------------------------


class TestConfirmationTokenValidation:
    def test_delete_400_missing_token_param(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db)
        drive = _make_game_drive(db, bundle)
        _set_active_user(app, _make_user(db, can_manage_game=True))

        resp = c.delete(f"/api/v1/drives/{drive.id}")

        assert resp.status_code == 422, resp.text  # missing required query param

    def test_delete_400_invalid_token(self, http_client):
        c, db, app = http_client
        bundle = _make_game_bundle(db)
        drive = _make_game_drive(db, bundle)
        _set_active_user(app, _make_user(db, can_manage_game=True))

        resp = c.delete(f"/api/v1/drives/{drive.id}?confirmation_token=not-a-real-token")

        assert resp.status_code == 400, resp.text

    def test_delete_400_token_issued_for_a_different_drive(self, http_client):
        from backend.service.utils import confirmation_tokens

        c, db, app = http_client
        bundle_a = _make_game_bundle(db, slug="doom")
        drive_a = _make_game_drive(db, bundle_a)
        bundle_b = _make_game_bundle(db, slug="doom2", title="Doom 2")
        drive_b = _make_game_drive(db, bundle_b)
        _set_active_user(app, _make_user(db, can_manage_game=True))

        token = confirmation_tokens.issue("drive", drive_b.id)
        resp = c.delete(f"/api/v1/drives/{drive_a.id}?confirmation_token={token}")

        assert resp.status_code == 400, resp.text

    def test_delete_400_expired_token(self, http_client, monkeypatch):
        from backend.service.utils import confirmation_tokens as mod

        c, db, app = http_client
        bundle = _make_game_bundle(db)
        drive = _make_game_drive(db, bundle)
        _set_active_user(app, _make_user(db, can_manage_game=True))

        token = mod.issue("drive", drive.id)
        real_monotonic = time.monotonic()
        monkeypatch.setattr(mod.time, "monotonic", lambda: real_monotonic + mod.TOKEN_TTL + 1)

        resp = c.delete(f"/api/v1/drives/{drive.id}?confirmation_token={token}")

        assert resp.status_code == 400, resp.text


# ---------------------------------------------------------------------------
# End-to-end delete
# ---------------------------------------------------------------------------


class TestDeleteEndToEnd:
    def test_delete_removes_image_file_clears_fk_and_deletes_row(self, http_client, tmp_path):
        from backend.service.utils import confirmation_tokens

        c, db, app = http_client
        image = tmp_path / "doom.img"
        image.write_bytes(b"fake image contents")
        bundle = _make_game_bundle(db)
        drive = _make_game_drive(db, bundle, image_path=str(image))
        _set_active_user(app, _make_user(db, can_manage_game=True))

        token = confirmation_tokens.issue("drive", drive.id)
        resp = c.delete(f"/api/v1/drives/{drive.id}?confirmation_token={token}")

        assert resp.status_code == 204, resp.text
        assert not image.exists()

        from backend.models.drive import Drive

        assert db.get(Drive, drive.id) is None
        db.refresh(bundle)
        assert bundle.drive_id is None

    def test_delete_clears_app_bundle_fk(self, http_client, tmp_path):
        from backend.service.utils import confirmation_tokens

        c, db, app = http_client
        bundle = _make_app_bundle(db)
        drive = _make_app_drive(db, bundle)
        _set_active_user(app, _make_user(db, can_manage_app=True))

        token = confirmation_tokens.issue("drive", drive.id)
        resp = c.delete(f"/api/v1/drives/{drive.id}?confirmation_token={token}")

        assert resp.status_code == 204, resp.text
        db.refresh(bundle)
        assert bundle.drive_id is None

    def test_delete_tolerates_missing_image_file(self, http_client, tmp_path):
        """image_path pointing at a file that no longer exists on disk must
        not raise — the row/FK cleanup still completes."""
        from backend.service.utils import confirmation_tokens

        c, db, app = http_client
        missing = tmp_path / "already-gone.img"
        bundle = _make_game_bundle(db)
        drive = _make_game_drive(db, bundle, image_path=str(missing))
        _set_active_user(app, _make_user(db, can_manage_game=True))

        token = confirmation_tokens.issue("drive", drive.id)
        resp = c.delete(f"/api/v1/drives/{drive.id}?confirmation_token={token}")

        assert resp.status_code == 204, resp.text
