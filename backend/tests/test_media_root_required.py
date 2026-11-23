"""An unset or blank MEDIA_PATH must fail loudly, never resolve to the process
working directory: path_utils.media_root(), POST /api/v1/media-items/upload,
the chunked software_media upload root (software_media._root) and its
/complete route (which must also mark the upload's job failed), and the Fetch
Metadata Accept All step (media_link.prepare_apply).
"""

import io

import pytest


class _FakeSettings:
    def __init__(self, media_path, library_path=""):
        self._media_path = media_path
        self._library_path = library_path

    def get_env_var(self, key):
        if key == "LIBRARY_PATH":
            return self._library_path
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

    def _set(value, library_path=""):
        monkeypatch.setattr(core_settings, "get_settings", lambda: _FakeSettings(value, library_path))
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


class TestChunkedUploadCompleteMarksJobFailed:
    """A 503 at /complete (MEDIA_PATH emptied between /init and /complete)
    schedules no finalize task, so the route itself must resolve the job."""

    @pytest.mark.parametrize("value", _UNSET)
    def test_complete_503_fails_the_job_and_drops_the_session(self, media_settings, value, tmp_path, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import backend.core.rate_limit as rl
        from backend.api.routes import uploads
        from backend.core import jobs
        from backend.core.dependencies import get_active_user
        from backend.models.user import UserItem
        from backend.service.uploads import core as cu
        from backend.service.uploads import software_media

        # Staging lives under LIBRARY_PATH; MEDIA_PATH stays unset throughout.
        media_settings(value, library_path=str(tmp_path))
        monkeypatch.setattr(rl, "enforce", lambda *a, **kw: None)
        software_media.register()

        app = FastAPI()
        app.include_router(uploads.software_media_router)
        app.dependency_overrides[get_active_user] = lambda: UserItem(id=1, name="Owner", is_owner=True)

        with TestClient(app) as c:
            init = c.post(
                "/api/v1/uploads/software-media/init",
                json={"kind": "file", "title": None, "files": [{"name": "song.mp3", "size": 3, "chunks": 1}]},
            )
            assert init.status_code == 200, init.text
            upload_id, job_id = init.json()["upload_id"], init.json()["job_id"]
            put = c.put(
                f"/api/v1/uploads/software-media/{upload_id}/chunks/0/0",
                files={"chunk": ("song.mp3", io.BytesIO(b"ID3"), "application/octet-stream")},
            )
            assert put.status_code == 200, put.text
            assert jobs.get(job_id)["status"] == "processing"

            resp = c.post(f"/api/v1/uploads/software-media/{upload_id}/complete")

        assert resp.status_code == 503, resp.text
        assert "MEDIA_PATH" in resp.json()["detail"]
        job = jobs.get(job_id)
        assert job["status"] == "error"
        assert "MEDIA_PATH" in job["error"]
        # Same terminal handling as a failed finalize: the session and its
        # staged chunks are gone, nothing is left "processing".
        assert cu.get_session(upload_id) is None


class TestAcceptAllMediaRoot:
    @pytest.fixture
    def db(self):
        from sqlalchemy.pool import StaticPool
        from sqlmodel import Session, SQLModel, create_engine
        import backend.models  # noqa: F401, registers all table models

        engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            yield session

    def _game(self, db):
        from backend.models.game import GameItemBundle

        game = GameItemBundle(title="Doom", platform="dos", slug="doom")
        db.add(game)
        db.commit()
        db.refresh(game)
        return game

    @pytest.mark.parametrize("value", _UNSET)
    def test_unset_media_path_is_503_before_any_download_or_write(
        self, media_settings, value, db, tmp_path, monkeypatch,
    ):
        from fastapi import HTTPException

        import backend.service.utils.asset_fetch as asset_fetch_mod
        from backend.models.media import MediaItemBundle
        from backend.service.games.media_link import prepare_apply
        from backend.service.metadata_providers import MetadataAsset

        media_settings(value)
        monkeypatch.chdir(tmp_path)
        downloads: list = []
        monkeypatch.setattr(asset_fetch_mod, "fetch_image_to_temp", lambda *a, **kw: downloads.append(a))
        game = self._game(db)
        assets = [MetadataAsset(url="https://cdn.thegamesdb.net/images/original/box.jpg", type="boxart_front")]

        with pytest.raises(HTTPException) as exc_info:
            prepare_apply(game.id, assets, db)

        assert exc_info.value.status_code == 503
        assert "MEDIA_PATH" in exc_info.value.detail
        assert downloads == []
        assert db.query(MediaItemBundle).count() == 0
        assert list(tmp_path.iterdir()) == []
