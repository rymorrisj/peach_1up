"""Tests for the browser-upload ingestion path:

- path_utils.sanitize_filename / resolve_under — the path-traversal fix.
- upload_utils.begin_upload — collision-free destination allocation built on those.
- POST /api/v1/library/upload — game media upload, chains into _prepare_item.
- POST /api/v1/media/upload — OS image upload only (media_type='game' now rejected).
"""

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# sanitize_filename / resolve_under — unit level
# ---------------------------------------------------------------------------

class TestSanitizeFilename:
    def test_strips_posix_directory_components(self):
        from backend.service.utils.path_utils import sanitize_filename
        assert sanitize_filename("../../etc/passwd") == "passwd"

    def test_strips_backslash_traversal(self):
        from backend.service.utils.path_utils import sanitize_filename
        assert sanitize_filename("..\\..\\evil.iso") == "evil.iso"

    def test_strips_embedded_separators(self):
        from backend.service.utils.path_utils import sanitize_filename
        assert "/" not in sanitize_filename("a/b/c.iso")
        assert "\\" not in sanitize_filename("a\\b\\c.iso")

    def test_preserves_clean_name_and_extension(self):
        from backend.service.utils.path_utils import sanitize_filename
        assert sanitize_filename("Doom.iso") == "doom.iso"

    def test_empty_stem_falls_back(self):
        from backend.service.utils.path_utils import sanitize_filename
        assert sanitize_filename("../../") == "upload"

    def test_extension_is_alnum_only(self):
        from backend.service.utils.path_utils import sanitize_filename
        result = sanitize_filename("game.is/o")
        assert "/" not in result


class TestResolveUnder:
    def test_safe_join_returns_resolved_path(self, tmp_path):
        from backend.service.utils.path_utils import resolve_under
        result = resolve_under(tmp_path, "sub", "file.iso")
        assert result == (tmp_path / "sub" / "file.iso").resolve()

    def test_escaping_path_raises(self, tmp_path):
        from backend.service.utils.path_utils import resolve_under
        with pytest.raises(ValueError):
            resolve_under(tmp_path, "../../etc/passwd")

    def test_base_itself_is_allowed(self, tmp_path):
        from backend.service.utils.path_utils import resolve_under
        assert resolve_under(tmp_path) == tmp_path.resolve()


# ---------------------------------------------------------------------------
# begin_upload — collision-free destination allocation
# ---------------------------------------------------------------------------

class TestBeginUpload:
    def test_dest_path_is_under_base_dir_even_for_malicious_filename(self, tmp_path):
        from backend.service.utils.upload_utils import begin_upload
        dest_dir, dest_path = begin_upload(tmp_path, "../../../etc/passwd")
        assert dest_dir.is_relative_to(tmp_path.resolve())
        assert dest_path.is_relative_to(tmp_path.resolve())

    def test_repeated_filename_gets_distinct_dirs(self, tmp_path):
        from backend.service.utils.upload_utils import begin_upload
        dest_dir1, _ = begin_upload(tmp_path, "doom.iso")
        dest_dir2, _ = begin_upload(tmp_path, "doom.iso")
        assert dest_dir1 != dest_dir2
        assert dest_dir1.exists()
        assert dest_dir2.exists()


# ---------------------------------------------------------------------------
# Route-level tests — shared fixture plumbing
# ---------------------------------------------------------------------------

class _FakeSettings:
    def __init__(self, env: dict, extra: dict | None = None):
        self._env = env
        self._extra = extra or {}

    def get_env_var(self, key):
        return self._env.get(key, "")

    def get(self, key, default=None):
        return self._extra.get(key, default)


@pytest.fixture
def mem_db_session():
    from sqlmodel import SQLModel, Session, create_engine
    from sqlalchemy.pool import StaticPool
    import backend.models  # noqa: F401 — registers all table models with SQLModel.metadata

    # StaticPool shares one connection across threads — TestClient dispatches
    # requests on a different thread, and sqlite ":memory:" is per-connection.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _owner_user():
    from backend.models.user import User
    return User(id=1, name="Owner", is_owner=True)


# ---------------------------------------------------------------------------
# Chunked upload flow: POST /init → PUT /chunks → POST /complete → DELETE (abort)
# ---------------------------------------------------------------------------

class TestLibraryUploadRoute:
    @pytest.fixture
    def client(self, tmp_path, mem_db_session, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.api.routes import library_items, uploads
        from backend.core.database import get_db
        from backend.core.dependencies import get_active_user
        import backend.core.rate_limit as rl

        media_path = tmp_path / "media"
        media_path.mkdir()

        import backend.core.settings as settings_mod
        monkeypatch.setattr(
            settings_mod,
            "get_settings",
            lambda: _FakeSettings({"MEDIA_PATH": str(media_path)}),
        )
        # The in-memory rate limiter is module-level and persists across test
        # methods; bypass it so the 10-inits-per-60s bucket never trips.
        monkeypatch.setattr(rl, "enforce", lambda *a, **kw: None)

        app = FastAPI()
        app.include_router(uploads.router)
        app.include_router(library_items.router)
        app.dependency_overrides[get_active_user] = _owner_user
        app.dependency_overrides[get_db] = lambda: mem_db_session

        with TestClient(app) as c:
            yield c, media_path

    @staticmethod
    def _upload(c, filename: str, content: bytes, title: str | None = None):
        """Run the full init → PUT chunk → complete flow. Returns the complete response."""
        size = len(content)
        init = c.post(
            "/api/v1/library/uploads/init",
            json={
                "kind": "file",
                "title": title,
                "files": [{"name": filename, "size": size, "chunks": 1}],
            },
        )
        if init.status_code != 200:
            return init
        uid = init.json()["upload_id"]
        c.put(
            f"/api/v1/library/uploads/{uid}/chunks/0/0",
            files={"chunk": (filename, content, "application/octet-stream")},
        )
        return c.post(f"/api/v1/library/uploads/{uid}/complete")

    @staticmethod
    def _media_files(media_path: Path) -> list[Path]:
        """Return files under media_path, excluding the tmp_chunks staging area."""
        return [p for p in media_path.rglob("*") if p.is_file() and "tmp_chunks" not in p.parts]

    def test_successful_upload_creates_library_item(self, client):
        c, media_path = client
        resp = self._upload(c, "Doom.iso", b"not a real iso but enough bytes")
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["title"] == "Doom"
        files = self._media_files(media_path)
        assert len(files) == 1
        assert files[0].is_relative_to(media_path.resolve())

    def test_missing_file_field_is_422(self, client):
        c, _ = client
        resp = c.post(
            "/api/v1/library/uploads/init",
            json={"kind": "file", "title": None, "files": []},
        )
        assert resp.status_code == 422

    def test_oversized_file_rejected_and_cleaned_up(self, client):
        c, media_path = client
        from backend.service.utils.upload_utils import DEFAULT_MAX_BYTES
        resp = c.post(
            "/api/v1/library/uploads/init",
            json={
                "kind": "file",
                "title": None,
                "files": [{"name": "big.iso", "size": DEFAULT_MAX_BYTES + 1, "chunks": 1}],
            },
        )
        assert resp.status_code == 422
        assert list(media_path.iterdir()) == []

    def test_traversal_filename_stays_inside_media_root(self, client):
        c, media_path = client
        resp = self._upload(c, "../../../etc/passwd", b"payload")
        assert resp.status_code == 201, resp.text
        files = self._media_files(media_path)
        assert all(f.is_relative_to(media_path.resolve()) for f in files)

    def test_duplicate_content_on_still_tracked_item_is_rejected_without_extra_copy(self, client):
        """Uploading byte-identical content under a different filename, while the
        first upload is still a tracked library item, triggers _ItemAlreadyExists
        at complete → 409, leaving no second physical copy behind."""
        c, media_path = client
        content = b"identical bytes for dedup test"
        first = self._upload(c, "doom.iso", content)
        assert first.status_code == 201, first.text

        second = self._upload(c, "doom-copy.iso", content)
        assert second.status_code == 409, second.text

        assert len(self._media_files(media_path)) == 1

    def test_duplicate_content_after_remove_reuses_orphaned_file(self, client):
        """The realistic re-add scenario: an item is removed (file kept on disk,
        per remove-not-delete semantics), then the same content is re-uploaded.
        The orphaned file is reused in place rather than copied again."""
        c, media_path = client
        content = b"identical bytes for dedup test"
        first = self._upload(c, "doom.iso", content)
        assert first.status_code == 201, first.text
        item_id = first.json()["id"]

        token_resp = c.post(f"/api/v1/library/{item_id}/confirm-delete")
        assert token_resp.status_code == 200, token_resp.text
        token = token_resp.json()["confirmation_token"]
        del_resp = c.delete(f"/api/v1/library/{item_id}", params={"confirmation_token": token})
        assert del_resp.status_code == 204, del_resp.text

        files_after_remove = self._media_files(media_path)
        assert len(files_after_remove) == 1  # remove, not delete — file stays on disk
        original_file = files_after_remove[0]

        second = self._upload(c, "doom-readded.iso", content)
        assert second.status_code == 201, second.text
        assert second.json()["reused_existing_media"] is True

        files_after_readd = self._media_files(media_path)
        assert len(files_after_readd) == 1
        assert files_after_readd[0] == original_file

    def test_duplicate_detection_uses_warm_index_not_a_fresh_scan(self, client, monkeypatch):
        """Second upload's duplicate match must come from the warm in-memory
        index (media_dup_index), not a second directory walk. Spies on
        Path.rglob filtered to calls against media_path itself, so the
        assertion is specific to the dedup index and not confused by other
        rglob callers. Also proves the index reflects the first upload
        immediately — the second call finds the match with no lag."""
        c, media_path = client
        from backend.service.utils import media_dup_index

        root = media_path.resolve()
        rglob_calls_on_root = []
        original_rglob = media_dup_index.Path.rglob

        def spy_rglob(self, pattern):
            if self == root:
                rglob_calls_on_root.append(pattern)
            return original_rglob(self, pattern)

        monkeypatch.setattr(media_dup_index.Path, "rglob", spy_rglob)

        content = b"identical bytes for warm-index test"
        first = self._upload(c, "warm-a.iso", content)
        assert first.status_code == 201, first.text
        assert len(rglob_calls_on_root) == 1  # initial index build

        second = self._upload(c, "warm-b.iso", content)
        assert second.status_code == 409, second.text  # still-tracked duplicate, via the index
        assert len(rglob_calls_on_root) == 1  # no rebuild — index stayed warm

    def test_index_does_not_return_stale_match_after_file_removed_from_disk(self, client):
        """Confirms re-uploading genuinely-gone content is treated as new rather
        than falsely matched against a now-stale index entry — exercises the
        index's self-healing path for out-of-band filesystem deletions."""
        c, media_path = client
        content = b"identical bytes for stale-index test"
        first = self._upload(c, "gone.iso", content)
        assert first.status_code == 201, first.text

        original_files = self._media_files(media_path)
        assert len(original_files) == 1
        original_path = original_files[0]
        original_path.unlink()  # simulates the file genuinely disappearing

        second = self._upload(c, "gone-again.iso", content)
        assert second.status_code == 201, second.text
        body = second.json()
        assert body["reused_existing_media"] is False

        new_files = self._media_files(media_path)
        assert len(new_files) == 1
        assert new_files[0] != original_path
        assert new_files[0].exists()


# ---------------------------------------------------------------------------
# POST /api/v1/media/upload (OS images only)
# ---------------------------------------------------------------------------

class TestMediaUploadRoute:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.api.routes import media
        from backend.core.dependencies import get_active_user

        os_path = tmp_path / "os"
        os_path.mkdir()

        import backend.core.settings as settings_mod
        monkeypatch.setattr(
            settings_mod,
            "get_settings",
            lambda: _FakeSettings({"OS_PATH": str(os_path)}),
        )

        app = FastAPI()
        app.include_router(media.router)
        app.dependency_overrides[get_active_user] = _owner_user

        with TestClient(app) as c:
            yield c, os_path

    def test_game_media_type_now_rejected(self, client):
        c, _ = client
        resp = c.post(
            "/api/v1/media/upload",
            data={"era": "win98", "media_type": "game"},
            files={"file": ("game.iso", b"data", "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "library/upload" in resp.json()["detail"]

    def test_missing_era_field_is_422(self, client):
        c, _ = client
        resp = c.post(
            "/api/v1/media/upload",
            data={"media_type": "os"},
            files={"file": ("win98.iso", b"data", "application/octet-stream")},
        )
        assert resp.status_code == 422

    def test_non_pc_era_rejected(self, client):
        c, _ = client
        resp = c.post(
            "/api/v1/media/upload",
            data={"era": "ps1", "media_type": "os"},
            files={"file": ("win98.iso", b"data", "application/octet-stream")},
        )
        assert resp.status_code == 422

    def test_successful_os_upload(self, client):
        c, os_path = client
        resp = c.post(
            "/api/v1/media/upload",
            data={"era": "win98", "media_type": "os"},
            files={"file": ("win98.iso", b"data", "application/octet-stream")},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        result_path = Path(body["path"]).resolve()
        assert result_path.is_relative_to(os_path.resolve())
        assert result_path.exists()

    def test_traversal_filename_stays_inside_os_root(self, client):
        c, os_path = client
        resp = c.post(
            "/api/v1/media/upload",
            data={"era": "win98", "media_type": "os"},
            files={"file": ("../../../etc/passwd", b"payload", "application/octet-stream")},
        )
        assert resp.status_code == 200, resp.text
        result_path = Path(resp.json()["path"]).resolve()
        assert result_path.is_relative_to(os_path.resolve())
