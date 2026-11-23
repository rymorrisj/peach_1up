"""MED-10 read side: a stored cover or file path that is UNC or a device path
must produce no URL and no filesystem access (no resolve(), no exists()) on
GameItemRead, AppItemRead, MediaItemRead and MediaItemBundleRead.

is_untrusted_remote_path (backend/service/utils/path_utils.py) is the lexical
predicate behind all four; a UNC path lexically under an operator-configured
library root (a library on a mapped network drive) is still trusted, matching
normalise_path.
"""

from pathlib import Path

import pytest

_HOSTILE = [
    "\\\\attacker\\share\\cover.png",
    "//attacker/share/cover.png",
    "\\\\?\\C:\\Windows\\cover.png",
    "\\\\.\\PhysicalDrive0",
    "\\??\\C:\\cover.png",
]


@pytest.fixture
def no_roots(monkeypatch):
    """Settings with no configured library roots, so no UNC path is trusted."""
    import backend.service.utils.settings as settings_mod

    monkeypatch.setattr(settings_mod, "get", lambda key, default=None: default)


@pytest.fixture
def disk_calls(monkeypatch):
    """Record every Path.resolve()/exists() call made while building a read."""
    calls: list[str] = []
    real_resolve, real_exists = Path.resolve, Path.exists

    def _resolve(self, *args, **kwargs):
        calls.append(f"resolve:{self}")
        return real_resolve(self, *args, **kwargs)

    def _exists(self, *args, **kwargs):
        calls.append(f"exists:{self}")
        return real_exists(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", _resolve)
    monkeypatch.setattr(Path, "exists", _exists)
    return calls


class TestPredicate:
    @pytest.mark.parametrize("path", _HOSTILE)
    def test_hostile_paths_are_untrusted(self, no_roots, path):
        from backend.service.utils.path_utils import is_untrusted_remote_path

        assert is_untrusted_remote_path(path) is True

    @pytest.mark.parametrize("path", ["C:\\library\\cover.png", "/library/cover.png", "relative/cover.png"])
    def test_local_paths_are_not_untrusted(self, no_roots, path):
        from backend.service.utils.path_utils import is_untrusted_remote_path

        assert is_untrusted_remote_path(path) is False

    def test_unc_under_a_configured_root_is_trusted(self, monkeypatch):
        import backend.service.utils.settings as settings_mod
        from backend.service.utils.path_utils import is_untrusted_remote_path

        monkeypatch.setattr(
            settings_mod,
            "get",
            lambda key, default=None: "\\\\nas\\share\\library" if key == "LIBRARY_PATH" else default,
        )
        assert is_untrusted_remote_path("\\\\nas\\share\\library\\games\\cover.png") is False
        assert is_untrusted_remote_path("\\\\nas\\share\\library\\..\\other\\cover.png") is True
        assert is_untrusted_remote_path("\\\\attacker\\share\\cover.png") is True


class TestReadModelsDoNoDiskAccess:
    @pytest.mark.parametrize("path", _HOSTILE)
    def test_game_item_read(self, no_roots, disk_calls, path):
        from backend.models.game import GameItemRead

        read = GameItemRead(id=1, game_item_bundle_id=1, disc_number=1, file_path="/x.bin", cover_art_path=path)

        assert read.cover_art_url is None
        assert disk_calls == []

    @pytest.mark.parametrize("path", _HOSTILE)
    def test_app_item_read(self, no_roots, disk_calls, path):
        from backend.models.app import AppItemRead

        read = AppItemRead(id=1, app_item_bundle_id=1, file_path="/x.exe", cover_art_path=path)

        assert read.cover_art_url is None
        assert disk_calls == []

    @pytest.mark.parametrize("path", _HOSTILE)
    def test_media_item_read_cover_and_file(self, no_roots, disk_calls, path):
        from backend.models.media import MediaItemRead

        read = MediaItemRead(id=1, title="X", media_kind="image", file_path=path, cover_art_path=path)

        assert read.cover_art_url is None
        assert read.file_url is None
        assert disk_calls == []

    @pytest.mark.parametrize("path", _HOSTILE)
    def test_media_item_bundle_read(self, no_roots, disk_calls, path):
        from backend.models.media import MediaItemBundleRead

        read = MediaItemBundleRead(id=1, title="X", media_kind="image", cover_art_path=path)

        assert read.cover_art_url is None
        assert disk_calls == []

    def test_local_cover_still_resolves(self, tmp_path, monkeypatch):
        """Control: an ordinary library path still gets a URL."""
        import backend.service.utils.settings as settings_mod
        from backend.models.game import GameItemRead

        monkeypatch.setattr(
            settings_mod,
            "get",
            lambda key, default=None: str(tmp_path) if key == "LIBRARY_PATH" else default,
        )
        cover = tmp_path / "games" / "cover.png"
        cover.parent.mkdir()
        cover.write_bytes(b"\x89PNG\r\n\x1a\n")

        read = GameItemRead(id=1, game_item_bundle_id=1, disc_number=1, file_path="/x.bin", cover_art_path=str(cover))

        assert read.cover_art_url == "/media/games/cover.png"
