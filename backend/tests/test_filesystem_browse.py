"""Tests for GET /api/v1/filesystem/browse's listing behavior.

test_normalise_path.py covers normalise_path, the outside-the-allowlist 400,
and the permission-gate 403s. This file covers the listing logic inside
browse() itself: a ".."-bearing traversal path, symlink filtering, the
extensions filter, show_files, and parent_path nulling at a root.
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
        # allowed_browse_roots() also allowlists every drive letter, which
        # would let paths outside LIBRARY_PATH through. Stub it down so only
        # that allowlist is in play (as test_normalise_path.py does).
        monkeypatch.setattr(filesystem, "allowed_browse_roots", lambda: [library_path.resolve()])

        app = FastAPI()
        app.include_router(filesystem.router)
        app.dependency_overrides[get_active_user] = lambda: UserItem(id=1, name="Owner", is_owner=True)

        with TestClient(app) as client:
            yield client, library_path

    def test_dotdot_traversal_path_outside_roots_returns_400(self, app_client, tmp_path):
        """normalise_path collapses '..' via Path.resolve() rather than
        rejecting it, so the allowlist check is what has to catch the escape."""
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
        # Extension-like directory name: the filter must never reach the dirs
        # branch, or a filtered browse would hide navigable directories.
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

    def test_show_files_false_returns_dirs_only(self, app_client):
        client, library_path = app_client
        (library_path / "game.iso").write_bytes(b"x")
        (library_path / "sub").mkdir()

        resp = client.get(
            "/api/v1/filesystem/browse",
            params={"path": str(library_path), "show_files": "false"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["files"] == []
        assert {d["name"] for d in body["dirs"]} == {"sub"}

    def test_dot_prefixed_dir_hidden_while_dot_prefixed_file_is_listed(self, app_client):
        """The dot filter is on the dirs branch only, files are not filtered."""
        client, library_path = app_client
        (library_path / ".hidden_dir").mkdir()
        (library_path / ".hidden_file").write_bytes(b"x")

        resp = client.get("/api/v1/filesystem/browse", params={"path": str(library_path)})

        assert resp.status_code == 200
        body = resp.json()
        assert ".hidden_dir" not in {d["name"] for d in body["dirs"]}
        assert ".hidden_file" in {f["name"] for f in body["files"]}

    def test_path_inside_roots_that_is_a_file_returns_400(self, app_client):
        client, library_path = app_client
        target = library_path / "game.iso"
        target.write_bytes(b"x")

        resp = client.get("/api/v1/filesystem/browse", params={"path": str(target)})

        assert resp.status_code == 400

    def test_path_inside_roots_that_does_not_exist_returns_400(self, app_client):
        client, library_path = app_client

        resp = client.get(
            "/api/v1/filesystem/browse", params={"path": str(library_path / "no_such_dir")},
        )

        assert resp.status_code == 400

    def test_browsing_root_path_itself_has_null_parent_path(self, app_client):
        client, library_path = app_client

        resp = client.get("/api/v1/filesystem/browse", params={"path": str(library_path)})

        assert resp.status_code == 200
        assert resp.json()["parent_path"] is None

    def test_home_listing_omits_unset_and_nonexistent_path_keys(self, app_client, tmp_path):
        """No path argument returns the configured base dirs. The fixture sets
        only LIBRARY_PATH, so the other five keys must not appear as entries."""
        client, library_path = app_client

        resp = client.get("/api/v1/filesystem/browse")

        assert resp.status_code == 200
        body = resp.json()
        assert body["current_path"] is None
        assert body["parent_path"] is None
        assert body["files"] == []
        assert [d["name"] for d in body["dirs"]] == ["Library"]
        assert body["dirs"][0]["path"] == str(library_path.resolve())
