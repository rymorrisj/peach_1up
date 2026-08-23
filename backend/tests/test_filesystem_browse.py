"""Tests for GET /api/v1/filesystem/browse's listing behavior.

test_normalise_path.py already covers normalise_path itself and the
outside-the-allowlist 400 case (TestFilesystemAllowlist, using a plain
outside-directory path, no ".." involved) and the permission-gate 403s
(TestFilesystemPermissionGate). Kept in a separate file rather than
appended there because that file's own docstring scopes it to
normalise_path plus the allowlist gate; the behaviors here (a ".."-bearing
traversal path, symlink filtering, the extensions filter, and parent_path
nulling at a root) are the listing logic inside browse() itself, a
different concern.
"""

import pytest


class TestFilesystemBrowseListing:
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
            lambda: {
                "LIBRARY_PATH": str(library_path), "SOFTWARE_PATH": "", "MEDIA_PATH": "",
                "OS_PATH": "", "ROMS_PATH": "", "PROFILES_PATH": "",
            },
        )
        # Same rationale as test_normalise_path.py's TestFilesystemAllowlist:
        # allowed_browse_roots() also allowlists every drive letter, stub it
        # down to just LIBRARY_PATH so only that allowlist is in play.
        monkeypatch.setattr(filesystem, "allowed_browse_roots", lambda: [library_path.resolve()])

        app = FastAPI()
        app.include_router(filesystem.router)
        app.dependency_overrides[get_active_user] = lambda: UserItem(id=1, name="Owner", is_owner=True)

        with TestClient(app) as client:
            yield client, library_path

    def test_dotdot_traversal_path_outside_roots_returns_400(self, app_client, tmp_path):
        """Distinct from TestFilesystemAllowlist's existing 400 case: that one
        passes a directly-outside absolute path with no '..' in it. This
        exercises the '..'-collapsing behavior itself (normalise_path
        resolves it via Path.resolve(), see TestNormalisePath) landing
        outside the allowlist."""
        client, library_path = app_client
        outside = tmp_path / "outside"
        outside.mkdir()

        traversal_path = str(library_path / ".." / "outside")
        resp = client.get("/api/v1/filesystem/browse", params={"path": traversal_path})

        assert resp.status_code == 400

    def test_symlink_entry_excluded_from_both_dirs_and_files(self, app_client):
        client, library_path = app_client
        real_dir = library_path / "real_target"
        real_dir.mkdir()
        (real_dir / "inner.txt").write_text("x")

        link_path = library_path / "linked_dir"
        try:
            link_path.symlink_to(real_dir, target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"Symlink creation not permitted in this environment: {exc}")

        resp = client.get("/api/v1/filesystem/browse", params={"path": str(library_path)})

        assert resp.status_code == 200
        body = resp.json()
        dir_names = {d["name"] for d in body["dirs"]}
        file_names = {f["name"] for f in body["files"]}
        assert "linked_dir" not in dir_names
        assert "linked_dir" not in file_names
        assert "real_target" in dir_names

    def test_extensions_filter_excludes_non_matching_files_but_not_dirs(self, app_client):
        client, library_path = app_client
        (library_path / "game.iso").write_bytes(b"x")
        (library_path / "game.cue").write_bytes(b"x")
        (library_path / "readme.txt").write_bytes(b"x")
        # A directory whose name looks extension-like, to confirm the filter
        # only ever touches the files branch, never the dirs branch.
        (library_path / "some_dir.txt").mkdir()

        resp = client.get(
            "/api/v1/filesystem/browse",
            params={"path": str(library_path), "extensions": "iso,cue"},
        )

        assert resp.status_code == 200
        body = resp.json()
        file_names = {f["name"] for f in body["files"]}
        assert file_names == {"game.iso", "game.cue"}
        dir_names = {d["name"] for d in body["dirs"]}
        assert "some_dir.txt" in dir_names

    def test_browsing_root_path_itself_has_null_parent_path(self, app_client):
        client, library_path = app_client

        resp = client.get("/api/v1/filesystem/browse", params={"path": str(library_path)})

        assert resp.status_code == 200
        assert resp.json()["parent_path"] is None
