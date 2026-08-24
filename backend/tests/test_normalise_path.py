"""Tests for backend.service.utils.path_utils.normalise_path and the
filesystem allowlist enforcement built on top of it (api/routes/filesystem.py).

normalise_path itself only handles null-byte rejection, separator
unification, and ``Path.resolve()`` (which silently collapses ``..``
segments, it does not raise on traversal). The allowlist check that rejects
paths outside configured roots is ``path_utils.is_within_roots``, called by
``api/routes/filesystem.browse`` and exercised here via
GET /api/v1/filesystem/browse, the closest equivalent to a "scan endpoint"
that accepts an arbitrary path. browse()'s own listing behaviour lives in
test_filesystem_browse.py.
"""

import pytest


class TestNormalisePath:
    def test_clean_path_under_library_path_resolves(self, tmp_path):
        from backend.service.utils.path_utils import normalise_path

        target = tmp_path / "library" / "media"
        target.mkdir(parents=True)

        result = normalise_path(str(target))
        assert result == target.resolve()

    def test_unix_style_traversal_is_collapsed_not_raised(self, tmp_path):
        """normalise_path does not raise on '..', Path.resolve() collapses it."""
        from backend.service.utils.path_utils import normalise_path

        nested = tmp_path / "library" / "media"
        nested.mkdir(parents=True)

        result = normalise_path(str(nested / ".." / ".."))
        assert result == tmp_path.resolve()

    def test_null_byte_raises_value_error(self):
        from backend.service.utils.path_utils import normalise_path

        with pytest.raises(ValueError):
            normalise_path("/some/path\x00/etc")

    def test_empty_path_raises_value_error(self):
        from backend.service.utils.path_utils import normalise_path

        with pytest.raises(ValueError):
            normalise_path("")

    def test_windows_style_traversal_is_collapsed_not_raised(self, tmp_path):
        """Backslash separators are unified to '/' then resolved, '..\\..' collapses."""
        from backend.service.utils.path_utils import normalise_path

        nested = tmp_path / "library" / "media"
        nested.mkdir(parents=True)

        result = normalise_path(str(nested) + "\\..\\..")
        assert result == tmp_path.resolve()


class TestFilesystemAllowlist:
    @pytest.fixture
    def app_client(self, tmp_path, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.api.routes import filesystem
        from backend.core.dependencies import get_active_user
        from backend.models.user import UserItem

        library_path = tmp_path / "library"
        library_path.mkdir()

        from backend.core import settings as settings_mod
        monkeypatch.setattr(
            settings_mod,
            "get_settings",
            lambda: {"LIBRARY_PATH": str(library_path), "SOFTWARE_PATH": "", "MEDIA_PATH": "", "OS_PATH": "", "ROMS_PATH": "", "PROFILES_PATH": ""},
        )

        # allowed_browse_roots() additionally allowlists every existing drive
        # root (so users can browse any drive to configure library paths).
        # That's orthogonal to the LIBRARY_PATH allowlist under test here, and
        # would make "outside library path" paths under e.g. C:\Users\... pass
        # the allowlist check anyway. Stub it down to just the configured
        # LIBRARY_PATH so only that allowlist is exercised.
        monkeypatch.setattr(filesystem, "allowed_browse_roots", lambda: [library_path.resolve()])

        app = FastAPI()
        app.include_router(filesystem.router)
        app.dependency_overrides[get_active_user] = lambda: UserItem(id=1, name="Owner", is_owner=True)

        with TestClient(app) as client:
            yield client, library_path

    def test_path_outside_library_path_rejected_with_400(self, app_client, tmp_path):
        client, _library_path = app_client
        outside = tmp_path / "outside"
        outside.mkdir()

        resp = client.get("/api/v1/filesystem/browse", params={"path": str(outside)})
        assert resp.status_code == 400

    def test_path_inside_library_path_accepted(self, app_client):
        client, library_path = app_client
        sub = library_path / "media"
        sub.mkdir()

        resp = client.get("/api/v1/filesystem/browse", params={"path": str(sub)})
        assert resp.status_code == 200


class TestFilesystemPermissionGate:
    """require_game_or_environment_editor's permission check itself, not the
    owner bypass TestFilesystemAllowlist above exercises. Non-editor 403 on
    browse, drives, and launch-file-extensions, plus 200s for the latter two.
    """

    @pytest.fixture
    def app_client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.api.routes import filesystem

        app = FastAPI()
        app.include_router(filesystem.router)

        with TestClient(app) as client:
            yield app, client

    def _set_user(self, app, **overrides):
        from backend.core.dependencies import get_active_user
        from backend.models.user import UserItem

        kwargs = dict(id=1, name="U", is_owner=False, can_manage_game=False, can_manage_environment=False)
        kwargs.update(overrides)
        app.dependency_overrides[get_active_user] = lambda: UserItem(**kwargs)

    def test_browse_403_for_non_editor(self, app_client):
        app, client = app_client
        self._set_user(app)

        resp = client.get("/api/v1/filesystem/browse")

        assert resp.status_code == 403

    def test_drives_403_for_non_editor(self, app_client):
        app, client = app_client
        self._set_user(app)

        resp = client.get("/api/v1/filesystem/drives")

        assert resp.status_code == 403

    def test_launch_file_extensions_403_for_non_editor(self, app_client):
        app, client = app_client
        self._set_user(app)

        resp = client.get("/api/v1/filesystem/launch-file-extensions")

        assert resp.status_code == 403

    def test_drives_200_for_environment_editor(self, app_client):
        """can_manage_environment alone (no can_manage_game, not owner) is
        enough, the two flags are OR'd in require_game_or_environment_editor."""
        app, client = app_client
        self._set_user(app, can_manage_environment=True)

        resp = client.get("/api/v1/filesystem/drives")

        assert resp.status_code == 200
        assert "drives" in resp.json()

    def test_launch_file_extensions_200_for_game_editor(self, app_client):
        app, client = app_client
        self._set_user(app, can_manage_game=True)

        resp = client.get("/api/v1/filesystem/launch-file-extensions")

        assert resp.status_code == 200
        assert isinstance(resp.json()["extensions"], list)
