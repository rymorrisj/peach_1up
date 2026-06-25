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
# POST /api/v1/library/upload
# ---------------------------------------------------------------------------

class TestLibraryUploadRoute:
    @pytest.fixture
    def client(self, tmp_path, mem_db_session, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.api.routes import library
        from backend.core.database import get_db
        from backend.core.dependencies import get_active_user

        media_path = tmp_path / "media"
        media_path.mkdir()

        import backend.core.settings as settings_mod
        monkeypatch.setattr(
            settings_mod,
            "get_settings",
            lambda: _FakeSettings({"MEDIA_PATH": str(media_path)}),
        )

        app = FastAPI()
        app.include_router(library.router)
        app.dependency_overrides[get_active_user] = _owner_user
        app.dependency_overrides[get_db] = lambda: mem_db_session

        with TestClient(app) as c:
            yield c, media_path

    def test_successful_upload_creates_library_item(self, client):
        c, media_path = client
        resp = c.post(
            "/api/v1/library/upload",
            files={"file": ("Doom.iso", b"not a real iso but enough bytes", "application/octet-stream")},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["title"] == "Doom"
        assert Path(body["media_path"]).is_relative_to(media_path.resolve())
        assert Path(body["media_path"]).exists()

    def test_missing_file_field_is_422(self, client):
        c, _ = client
        resp = c.post("/api/v1/library/upload", files={})
        assert resp.status_code == 422

    def test_oversized_file_rejected_and_cleaned_up(self, client):
        c, media_path = client
        import backend.core.settings as settings_mod
        original = settings_mod.get_settings
        settings_mod.get_settings = lambda: _FakeSettings(
            {"MEDIA_PATH": str(media_path)}, {"UPLOAD_MAX_BYTES": 10}
        )
        try:
            resp = c.post(
                "/api/v1/library/upload",
                files={"file": ("big.iso", b"x" * 1024, "application/octet-stream")},
            )
        finally:
            settings_mod.get_settings = original

        assert resp.status_code == 413
        # nothing left behind under MEDIA_PATH after the failed upload
        assert list(media_path.iterdir()) == []

    def test_traversal_filename_stays_inside_media_root(self, client):
        c, media_path = client
        resp = c.post(
            "/api/v1/library/upload",
            files={"file": ("../../../etc/passwd", b"payload", "application/octet-stream")},
        )
        assert resp.status_code == 201, resp.text
        media_file_path = Path(resp.json()["media_path"]).resolve()
        assert media_file_path.is_relative_to(media_path.resolve())

    def test_duplicate_content_on_still_tracked_item_is_rejected_without_extra_copy(self, client):
        """Uploading byte-identical content under a different filename, while the
        first upload is still a tracked library item, hits the existing
        _ItemAlreadyExists path (via the matched file) — same 409 as a literal
        path collision — and leaves no second physical copy behind."""
        c, media_path = client
        content = b"identical bytes for dedup test"
        first = c.post(
            "/api/v1/library/upload",
            files={"file": ("doom.iso", content, "application/octet-stream")},
        )
        assert first.status_code == 201, first.text

        second = c.post(
            "/api/v1/library/upload",
            files={"file": ("doom-copy.iso", content, "application/octet-stream")},
        )
        assert second.status_code == 409, second.text

        media_files = [p for p in media_path.rglob("*") if p.is_file()]
        assert len(media_files) == 1

    def test_duplicate_content_after_remove_reuses_orphaned_file(self, client):
        """The realistic re-add scenario: an item is removed (file kept on disk,
        per the project's remove-not-delete semantics), then the same content is
        re-uploaded under a new filename. The orphaned file is no longer tracked
        by any item, so it should be reused in place rather than copied again."""
        c, media_path = client
        content = b"identical bytes for dedup test"
        first = c.post(
            "/api/v1/library/upload",
            files={"file": ("doom.iso", content, "application/octet-stream")},
        )
        assert first.status_code == 201, first.text
        item_id = first.json()["id"]
        original_media_path = Path(first.json()["media_path"])

        token_resp = c.post(f"/api/v1/library/{item_id}/confirm-delete")
        assert token_resp.status_code == 200, token_resp.text
        token = token_resp.json()["confirmation_token"]
        del_resp = c.delete(f"/api/v1/library/{item_id}", params={"confirmation_token": token})
        assert del_resp.status_code == 204, del_resp.text
        assert original_media_path.exists()  # remove, not delete — file stays on disk

        second = c.post(
            "/api/v1/library/upload",
            files={"file": ("doom-readded.iso", content, "application/octet-stream")},
        )
        assert second.status_code == 201, second.text
        body = second.json()
        assert body["reused_existing_media"] is True
        assert Path(body["media_path"]) == original_media_path

        media_files = [p for p in media_path.rglob("*") if p.is_file()]
        assert len(media_files) == 1

    def test_duplicate_detection_uses_warm_index_not_a_fresh_scan(self, client, monkeypatch):
        """Second upload's duplicate match must come from the warm in-memory
        index (media_dup_index), not a second directory walk. Spies on
        Path.rglob, filtered to calls against media_path itself, so the
        assertion is specific to the dedup index's own walk and isn't
        confused by any other code calling rglob for unrelated reasons. This
        also proves the index reflects the first upload immediately — the
        second call finds the match on the very next request, no lag."""
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
        first = c.post(
            "/api/v1/library/upload",
            files={"file": ("warm-a.iso", content, "application/octet-stream")},
        )
        assert first.status_code == 201, first.text
        assert len(rglob_calls_on_root) == 1  # initial index build

        second = c.post(
            "/api/v1/library/upload",
            files={"file": ("warm-b.iso", content, "application/octet-stream")},
        )
        assert second.status_code == 409, second.text  # still-tracked duplicate, via the index
        assert len(rglob_calls_on_root) == 1  # no rebuild — index stayed warm

    def test_index_does_not_return_stale_match_after_file_removed_from_disk(self, client):
        """No in-app flow deletes a tracked media file directly today — DELETE
        /api/v1/library/{item_id} explicitly leaves it on disk (see the
        remove-not-delete test above), and the only file it does unlink (a
        Drive.image_path .img file) is outside the dedup extension allowlist
        by design (see upload_utils.find_existing_duplicate). To exercise the
        index's self-healing path for content that's genuinely gone — the
        drift scenario the index must never get wrong — this test removes the
        file directly, the way an out-of-band filesystem change would, and
        confirms re-uploading identical bytes is treated as new rather than
        falsely matched against the now-stale index entry."""
        c, media_path = client
        content = b"identical bytes for stale-index test"
        first = c.post(
            "/api/v1/library/upload",
            files={"file": ("gone.iso", content, "application/octet-stream")},
        )
        assert first.status_code == 201, first.text
        original_path = Path(first.json()["media_path"])

        original_path.unlink()  # simulates the file genuinely disappearing

        second = c.post(
            "/api/v1/library/upload",
            files={"file": ("gone-again.iso", content, "application/octet-stream")},
        )
        assert second.status_code == 201, second.text
        body = second.json()
        assert body.get("reused_existing_media") is not True
        assert Path(body["media_path"]) != original_path
        assert Path(body["media_path"]).exists()


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
