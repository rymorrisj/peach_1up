"""An unset or blank MEDIA_PATH must fail loudly, never resolve to the process
working directory: path_utils.media_root(), POST /api/v1/media-items/upload,
and the chunked software_media upload root (software_media._root).
"""

import io

import pytest


class _FakeSettings:
    def __init__(self, media_path):
        self._media_path = media_path

    def get_env_var(self, key):
        if key != "MEDIA_PATH":
            return ""
        if self._media_path is None:
            raise KeyError(key)
        return self._media_path

    def get(self, key, default=None):
        return default


_UNSET = [None, "", "   "]


@pytest.fixture
def media_settings(monkeypatch):
    import backend.core.settings as core_settings

    def _set(value):
        monkeypatch.setattr(core_settings, "get_settings", lambda: _FakeSettings(value))
    return _set


class TestMediaRootHelper:
    @pytest.mark.parametrize("value", _UNSET)
    def test_unset_or_blank_raises(self, media_settings, value):
        from backend.service.utils.path_utils import media_root

        media_settings(value)
        with pytest.raises(ValueError, match="MEDIA_PATH is not configured"):
            media_root()

    def test_configured_value_resolves(self, media_settings, tmp_path):
        from backend.service.utils.path_utils import media_root

        media_settings(str(tmp_path / "media"))
        assert media_root() == (tmp_path / "media").resolve()


class TestSingleShotUpload:
    @pytest.mark.parametrize("value", _UNSET)
    def test_upload_is_503_and_writes_nothing(self, media_settings, value, tmp_path, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from backend.api.routes import media
        from backend.core.dependencies import get_active_user
        from backend.models.user import UserItem

        media_settings(value)
        monkeypatch.chdir(tmp_path)
        app = FastAPI()
        app.include_router(media.router)
        app.dependency_overrides[get_active_user] = lambda: UserItem(id=1, name="Owner", is_owner=True)

        with TestClient(app) as c:
            resp = c.post(
                "/api/v1/media-items/upload",
                files={"file": ("song.mp3", io.BytesIO(b"ID3"), "audio/mpeg")},
            )

        assert resp.status_code == 503, resp.text
        assert "MEDIA_PATH" in resp.json()["detail"]
        assert list(tmp_path.iterdir()) == []


class TestChunkedUploadRoot:
    @pytest.mark.parametrize("value", _UNSET)
    def test_root_resolver_is_503(self, media_settings, value):
        from fastapi import HTTPException

        from backend.service.uploads.software_media import _root

        media_settings(value)
        with pytest.raises(HTTPException) as exc_info:
            _root()
        assert exc_info.value.status_code == 503
        assert "MEDIA_PATH" in exc_info.value.detail

    def test_root_resolver_returns_configured_root(self, media_settings, tmp_path):
        from backend.service.uploads.software_media import _root

        media_settings(str(tmp_path))
        assert _root() == tmp_path.resolve()
