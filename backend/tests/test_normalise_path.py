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


def _no_configured_roots(monkeypatch):
    import backend.service.utils.settings as settings_mod

    monkeypatch.setattr(settings_mod, "get", lambda key, default=None: default)


def _configured_library_root(monkeypatch, root: str):
    import backend.service.utils.settings as settings_mod

    monkeypatch.setattr(
        settings_mod,
        "get",
        lambda key, default=None: root if key == "LIBRARY_PATH" else default,
    )


class TestNormalisePathRejections:
    """MED-10: UNC, device and drive-relative forms are rejected lexically,
    before Path.resolve() can touch the filesystem (resolving a UNC path
    opens an SMB connection to the named host)."""

    @pytest.fixture(autouse=True)
    def _never_resolve(self, monkeypatch):
        """Any rejection must happen before resolve(); fail loudly if not."""
        from pathlib import Path

        real_resolve = Path.resolve

        def _guard(self, *args, **kwargs):
            s = str(self).replace("\\", "/")
            if s.startswith("//") or s.startswith("/??/"):
                raise AssertionError(f"resolve() reached for rejected path {self!s}")
            return real_resolve(self, *args, **kwargs)

        monkeypatch.setattr(Path, "resolve", _guard)

    @pytest.mark.parametrize(
        "path",
        [
            "\\\\attacker\\share\\x.png",
            "//attacker/share/x.png",
            "\\\\attacker.example.com\\c$\\Windows",
            "\\/attacker/share/x.png",
            "\\\\127.0.0.1\\share\\x",
        ],
    )
    def test_unc_rejected(self, monkeypatch, path):
        from backend.service.utils.path_utils import normalise_path

        _no_configured_roots(monkeypatch)
        with pytest.raises(ValueError, match="UNC"):
            normalise_path(path)

    @pytest.mark.parametrize(
        "path",
        [
            "\\\\?\\C:\\Windows\\System32",
            "\\\\.\\PhysicalDrive0",
            "//?/C:/Windows",
            "//./COM1",
            "\\??\\C:\\Windows",
            "\\\\?\\UNC\\attacker\\share",
        ],
    )
    def test_device_paths_rejected(self, monkeypatch, path):
        from backend.service.utils.path_utils import normalise_path

        _no_configured_roots(monkeypatch)
        with pytest.raises(ValueError, match="Device"):
            normalise_path(path)

    @pytest.mark.parametrize("path", ["\\\\?\\C:\\x", "\\\\.\\pipe\\x"])
    def test_device_paths_rejected_even_with_allow_unc(self, path):
        from backend.service.utils.path_utils import normalise_path

        with pytest.raises(ValueError, match="Device"):
            normalise_path(path, allow_unc=True)

    @pytest.mark.parametrize("path", ["C:foo", "c:..\\..\\Windows", "D:", "Z:relative\\x.png"])
    def test_drive_relative_rejected(self, path):
        from backend.service.utils.path_utils import normalise_path

        with pytest.raises(ValueError, match="Drive-relative"):
            normalise_path(path)

    def test_drive_absolute_is_not_drive_relative(self):
        """'C:\\x' and 'C:/x' are absolute and must pass the drive-relative
        check (the result is platform-dependent, so only no-raise is asserted)."""
        from backend.service.utils.path_utils import normalise_path

        normalise_path("C:\\library\\x.png")
        normalise_path("C:/library/x.png")

    def test_null_byte_still_rejected_before_unc_check(self):
        from backend.service.utils.path_utils import normalise_path

        with pytest.raises(ValueError, match="null byte"):
            normalise_path("\\\\attacker\\share\x00")

    def test_unc_rejected_when_settings_uninitialised(self, monkeypatch):
        """No configured roots (settings.get raises) fails closed."""
        import backend.service.utils.settings as settings_mod
        from backend.service.utils.path_utils import normalise_path

        def _raise(key, default=None):
            raise RuntimeError("settings.init() has not been called.")

        monkeypatch.setattr(settings_mod, "get", _raise)
        with pytest.raises(ValueError, match="UNC"):
            normalise_path("\\\\attacker\\share\\x")


class TestNormalisePathUncExemptions:
    """The two exemptions agreed for MED-10: allow_unc=True (Environment
    images, SECURITY.md's NAS exception) and UNC paths lexically inside an
    operator-configured library root (a library on a mapped network drive,
    which Path.resolve() stores as UNC)."""

    @pytest.fixture(autouse=True)
    def _no_disk(self, monkeypatch):
        """Exempted UNC paths still resolve(); stub it for UNC paths only so
        no test opens SMB. Every other path resolves normally."""
        from pathlib import Path

        real_resolve = Path.resolve

        def _stub(self, *args, **kwargs):
            if str(self).replace("\\", "/").startswith("//"):
                return self
            return real_resolve(self, *args, **kwargs)

        monkeypatch.setattr(Path, "resolve", _stub)

    def test_allow_unc_accepts_unc(self, monkeypatch):
        from backend.service.utils.path_utils import normalise_path

        _no_configured_roots(monkeypatch)
        result = normalise_path("\\\\nas\\images\\win98.vhd", allow_unc=True)
        assert str(result).replace("\\", "/").endswith("nas/images/win98.vhd")

    def test_unc_under_configured_root_accepted(self, monkeypatch):
        from backend.service.utils.path_utils import normalise_path

        _configured_library_root(monkeypatch, "\\\\nas\\share\\library")
        normalise_path("\\\\nas\\share\\library\\software\\media\\x.png")
        normalise_path("//NAS/Share/Library/software/x.png")  # case-insensitive, either separator

    def test_unc_root_itself_accepted(self, monkeypatch):
        from backend.service.utils.path_utils import normalise_path

        _configured_library_root(monkeypatch, "\\\\nas\\share\\library")
        normalise_path("\\\\nas\\share\\library")

    @pytest.mark.parametrize(
        "path",
        [
            "\\\\attacker\\share\\library\\x.png",  # different host
            "\\\\nas\\other\\library\\x.png",  # different share
            "\\\\nas\\share\\library-evil\\x.png",  # prefix, not a child
            "\\\\nas\\share\\library\\..\\..\\..\\x.png",  # climbs out lexically
            "\\\\nas\\share\\library\\..\\secrets\\x.png",
        ],
    )
    def test_unc_outside_configured_root_rejected(self, monkeypatch, path):
        from backend.service.utils.path_utils import normalise_path

        _configured_library_root(monkeypatch, "\\\\nas\\share\\library")
        with pytest.raises(ValueError, match="UNC"):
            normalise_path(path)

    def test_local_root_does_not_exempt_unc(self, monkeypatch):
        from backend.service.utils.path_utils import normalise_path

        _configured_library_root(monkeypatch, "C:\\library")
        with pytest.raises(ValueError, match="UNC"):
            normalise_path("\\\\attacker\\share\\x.png")


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
            lambda: {
                "LIBRARY_PATH": str(library_path),
                "SOFTWARE_PATH": "",
                "MEDIA_PATH": "",
                "OS_PATH": "",
                "ROMS_PATH": "",
                "PROFILES_PATH": "",
            },
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
