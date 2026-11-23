"""Route-level tests for GET /media/{file_path} in backend/main.py.

backend.main calls init_settings() at import, which would open the real
settings DB. The fixture pre-seeds settings state and marks it initialised so
that call is a no-op, and get_db is overridden with an in-memory session. The
lifespan never runs because TestClient is not used as a context manager.
"""

import pytest


def _with_client_ip(app, host: str):
    async def _wrapper(scope, receive, send):
        if scope.get("type") in ("http", "websocket"):
            scope = {**scope, "client": (host, 50000)}
        await app(scope, receive, send)

    return _wrapper


@pytest.fixture
def media_client(tmp_path, monkeypatch):
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine
    from fastapi.testclient import TestClient

    import backend.api.middleware.security as security_module
    import backend.core.settings as core_settings
    import backend.service.utils.settings as settings_state
    import backend.models  # noqa: F401, registers all table models with SQLModel.metadata

    library_root = tmp_path / "library"
    library_root.mkdir()
    (library_root / "cover.png").write_bytes(b"png-bytes")
    (tmp_path / "outside.txt").write_text("secret")

    media_root = library_root / "software" / "media"
    (media_root / "doom").mkdir(parents=True)
    for name, data in {
        "track.mp3": b"ID3audio",
        "notes.txt": b"plain text",
        "manual.pdf": b"%PDF-1.4",
        "pack.zip": b"PK\x03\x04",
        "page.html": b"<script>alert(1)</script>",
        "art.svg": b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
        "page.xhtml": b"<html/>",
        "app.js": b"alert(1)",
        "photo.JPG": b"\xff\xd8\xff",
    }.items():
        (media_root / "doom" / name).write_bytes(data)
    games_root = library_root / "software" / "games" / "nes" / "mario"
    games_root.mkdir(parents=True)
    (games_root / "mario.zip").write_bytes(b"PK\x03\x04rom")
    (games_root / "mario.nes").write_bytes(b"NES\x1a")

    monkeypatch.setattr(core_settings, "_initialised", True)
    # Simulate a configured install: while first-run is incomplete,
    # FirstRunGuardMiddleware redirects extensionless non-API paths to
    # /first-run, which the SPA fallback answers with index.html (200).
    monkeypatch.setattr(security_module, "_first_run_done_cache", True)
    monkeypatch.setattr(
        settings_state,
        "_state",
        {
            "LIBRARY_PATH": str(library_root),
            "ALLOW_NETWORK_ACCESS": False,
            "_env": {"MEDIA_PATH": str(media_root)},
        },
    )

    from backend.core.database import get_db
    from backend.main import app

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        app.dependency_overrides[get_db] = lambda: session
        try:
            yield TestClient(_with_client_ip(app, "127.0.0.1")), session
        finally:
            app.dependency_overrides.pop(get_db, None)


def _logged_in_cookie(db) -> str:
    from backend.core.identity import issue_session
    from backend.models.user import UserItem

    user = UserItem(name="Viewer", is_owner=False, is_admin=False)
    db.add(user)
    db.commit()
    db.refresh(user)
    token, _ = issue_session(db, user)
    return f"peach_token={user.id}.{token}"


class TestMediaRouteAuth:
    def test_no_session_is_401(self, media_client):
        client, _ = media_client

        resp = client.get("/media/cover.png")

        assert resp.status_code == 401, resp.text

    def test_malformed_cookie_is_401(self, media_client):
        client, _ = media_client

        resp = client.get("/media/cover.png", headers={"Cookie": "peach_token=not-a-session"})

        assert resp.status_code == 401, resp.text

    def test_stale_token_is_401(self, media_client):
        client, db = media_client
        cookie = _logged_in_cookie(db)
        user_id = cookie.split("=", 1)[1].split(".", 1)[0]

        resp = client.get("/media/cover.png", headers={"Cookie": f"peach_token={user_id}.wrong"})

        assert resp.status_code == 401, resp.text

    def test_valid_session_serves_file(self, media_client):
        client, db = media_client

        resp = client.get("/media/cover.png", headers={"Cookie": _logged_in_cookie(db)})

        assert resp.status_code == 200, resp.text
        assert resp.content == b"png-bytes"

    def test_valid_session_missing_file_is_404(self, media_client):
        client, db = media_client

        resp = client.get("/media/absent.png", headers={"Cookie": _logged_in_cookie(db)})

        assert resp.status_code == 404

    def test_valid_session_traversal_is_404(self, media_client):
        client, db = media_client

        resp = client.get("/media/..%2Foutside.txt", headers={"Cookie": _logged_in_cookie(db)})

        assert resp.status_code == 404


class TestMediaRouteHardening:
    """MED-10 / MED-11: lexical URL-path validation before any disk access,
    an extension allowlist, nosniff on every response, and attachment
    disposition for everything that is not a plain raster image."""

    def _get(self, media_client, path: str):
        client, db = media_client
        return client.get(f"/media/{path}", headers={"Cookie": _logged_in_cookie(db)})

    def test_inline_image_has_nosniff_and_no_attachment(self, media_client):
        resp = self._get(media_client, "cover.png")

        assert resp.status_code == 200
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["content-type"] == "image/png"
        assert "attachment" not in resp.headers.get("content-disposition", "")

    def test_uppercase_image_extension_is_inline(self, media_client):
        resp = self._get(media_client, "software/media/doom/photo.JPG")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/jpeg"
        assert "attachment" not in resp.headers.get("content-disposition", "")

    @pytest.mark.parametrize("name", ["track.mp3", "notes.txt", "manual.pdf", "pack.zip"])
    def test_non_image_is_served_as_attachment_with_nosniff(self, media_client, name):
        resp = self._get(media_client, f"software/media/doom/{name}")

        assert resp.status_code == 200, resp.text
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["content-disposition"].startswith("attachment")

    @pytest.mark.parametrize("name", ["page.html", "art.svg", "page.xhtml", "app.js"])
    def test_active_content_extension_is_404(self, media_client, name):
        resp = self._get(media_client, f"software/media/doom/{name}")

        assert resp.status_code == 404

    def test_rom_extension_outside_allowlist_is_404(self, media_client):
        resp = self._get(media_client, "software/games/nes/mario/mario.nes")

        assert resp.status_code == 404

    def test_archive_outside_media_path_is_404(self, media_client):
        """A .zip elsewhere in the library is typically a ROM or BIOS pack."""
        resp = self._get(media_client, "software/games/nes/mario/mario.zip")

        assert resp.status_code == 404

    def test_directory_is_404(self, media_client):
        resp = self._get(media_client, "software/media/doom")

        assert resp.status_code == 404
        assert "text/html" not in resp.headers.get("content-type", "")

    @pytest.mark.parametrize(
        "path",
        [
            "..%2Foutside.txt",
            "software/..%2F..%2Foutside.txt",
            "%5C%5Cattacker%5Cshare%5Cx.png",  # \\attacker\share\x.png
            "%2F%2Fattacker%2Fshare%2Fx.png",  # //attacker/share/x.png
            "C:%5CWindows%5Cwin.png",  # drive-absolute
            "C:x.png",  # drive-relative
            "%2Fetc%2Fx.png",  # absolute
            "cover.png:stream",  # NTFS alternate data stream
            "~%2Fcover.png",  # home-relative
        ],
    )
    def test_hostile_paths_are_404_without_touching_disk(self, media_client, monkeypatch, path):
        """Rejected before Path.resolve() runs, so a UNC path never reaches
        the SMB client."""
        from pathlib import Path

        real_resolve = Path.resolve

        def _guard(self, *args, **kwargs):
            if str(self).replace("\\", "/").startswith("//"):
                raise AssertionError(f"resolve() reached for {self!s}")
            return real_resolve(self, *args, **kwargs)

        monkeypatch.setattr(Path, "resolve", _guard)
        resp = self._get(media_client, path)

        assert resp.status_code == 404
