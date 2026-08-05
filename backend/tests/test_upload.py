"""Tests for the browser-upload ingestion path:

- path_utils.safe_basename / resolve_under — the path-traversal fix.
- upload_utils.begin_upload — collision-free destination allocation built on those.
- POST /api/v1/game-items/uploads/{init,chunks,complete} — chunked software-media
  upload, chains into upload_finalize._ingest_media_entry et al.
- POST /api/v1/media-items/upload — generic Media-archive upload (doc 03): stages
  bytes under MEDIA_PATH only, no era/media_type — creating the MediaItem row
  is a separate call.
- POST /api/v1/environment-items/{slug}/install-media — OS install-media upload
  (doc 04): the old media_type='os' logic, relocated and now slug-scoped with
  era read from the Environment record instead of trusted form input.
"""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _reset_media_dup_index():
    """Defense-in-depth: clears the module-level cache even though isolation
    currently also holds via each test using a unique tmp_path root."""
    from backend.service.utils import media_dup_index

    media_dup_index._index.clear()
    media_dup_index._built_for = None
    yield
    media_dup_index._index.clear()
    media_dup_index._built_for = None


# ---------------------------------------------------------------------------
# safe_basename / resolve_under — unit level
# ---------------------------------------------------------------------------

class TestSafeBasename:
    def test_strips_posix_directory_components(self):
        from backend.service.utils.path_utils import safe_basename
        assert safe_basename("../../etc/passwd") == "passwd"

    def test_strips_backslash_traversal(self):
        from backend.service.utils.path_utils import safe_basename
        assert safe_basename("..\\..\\evil.iso") == "evil.iso"

    def test_strips_embedded_separators(self):
        from backend.service.utils.path_utils import safe_basename
        assert "/" not in safe_basename("a/b/c.iso")
        assert "\\" not in safe_basename("a\\b\\c.iso")

    def test_preserves_case_and_extension(self):
        # Case is deliberately preserved (unlike the old slugify-based
        # sanitize_filename this replaces) — see safe_basename's docstring
        # for why a content-derived filename (PS3 .rap license files) can't
        # be lowercased without breaking RPCS3's own filename matching.
        from backend.service.utils.path_utils import safe_basename
        assert safe_basename("Doom.iso") == "Doom.iso"

    def test_preserves_underscores(self):
        from backend.service.utils.path_utils import safe_basename
        assert safe_basename("UP0177-NPUB30724_00-00BAYONETTAHDDUS.rap") == \
            "UP0177-NPUB30724_00-00BAYONETTAHDDUS.rap"

    def test_empty_stem_falls_back(self):
        from backend.service.utils.path_utils import safe_basename
        assert safe_basename("../../") == "upload"

    def test_extension_is_alnum_only(self):
        from backend.service.utils.path_utils import safe_basename
        result = safe_basename("game.is/o")
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
    from backend.models.user import UserItem
    return UserItem(id=1, name="Owner", is_owner=True)


# ---------------------------------------------------------------------------
# Chunked upload flow: POST /init → PUT /chunks → POST /complete → DELETE (abort)
# ---------------------------------------------------------------------------

class TestSoftwareUploadRoute:
    @pytest.fixture(autouse=True)
    def _reset_jobs(self):
        """core.jobs is a module-level, in-memory store shared across the
        whole test process (matching _scan_state / install_registry, see its
        own docstring), not reset by any app/DB fixture below. Every upload
        in this class now finalizes as a background job (no inline path),
        so tests here actually populate it, clear it before and after each
        test so one test's job never leaks into another's assertions."""
        from backend.core import jobs

        jobs._jobs.clear()
        jobs._cancel_events.clear()
        yield
        jobs._jobs.clear()
        jobs._cancel_events.clear()

    @pytest.fixture
    def client(self, tmp_path, mem_db_session, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.api.routes import game_item_bundles, jobs as jobs_routes, uploads
        from backend.core.database import get_db
        from backend.core.dependencies import get_active_user
        from backend.core.lifespan import _register_upload_domains
        import backend.core.rate_limit as rl

        media_path = tmp_path / "media"
        media_path.mkdir()

        import backend.core.settings as settings_mod
        monkeypatch.setattr(
            settings_mod,
            "get_settings",
            # LIBRARY_PATH backs chunked-upload staging (library/tmp_chunks/,
            # a sibling of software/, not nested inside it) — set here too so
            # staging lands inside this test's own tmp_path sandbox instead of
            # the real process cwd.
            lambda: _FakeSettings({"SOFTWARE_PATH": str(media_path), "LIBRARY_PATH": str(tmp_path)}),
        )
        # The in-memory rate limiter is module-level and persists across test
        # methods; bypass it so the 10-inits-per-60s bucket never trips.
        monkeypatch.setattr(rl, "enforce", lambda *a, **kw: None)

        # This app is bare with no lifespan attached, so the real startup
        # path (backend.core.lifespan.lifespan) never runs, and the
        # software-games route depends on registry state that lifespan
        # would normally populate. Register directly here instead.
        _register_upload_domains()

        app = FastAPI()
        app.include_router(uploads.software_games_router)
        app.include_router(game_item_bundles.router)
        app.include_router(jobs_routes.router)
        app.dependency_overrides[get_active_user] = _owner_user
        app.dependency_overrides[get_db] = lambda: mem_db_session

        with TestClient(app) as c:
            yield c, media_path

    @staticmethod
    def _upload(c, filename: str, content: bytes, title: str | None = None):
        """Run the full init → PUT chunk → complete flow, then resolve the
        background finalize job to its terminal state and return that GET
        /api/v1/jobs/{id} response. Every upload finalizes as a background
        job now (no inline path), but TestClient/httpx's ASGI transport runs
        BackgroundTasks to completion as part of the same request/response
        cycle (no real async boundary/thread), so the job is already
        terminal ("done" or "error") by the time /complete responds, this
        just fetches its final state rather than the (now content-free,
        always {job_id, status: "processing"}) /complete response body."""
        size = len(content)
        init = c.post(
            "/api/v1/uploads/software-games/init",
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
            f"/api/v1/uploads/software-games/{uid}/chunks/0/0",
            files={"chunk": (filename, content, "application/octet-stream")},
        )
        complete = c.post(f"/api/v1/uploads/software-games/{uid}/complete")
        if complete.status_code != 202:
            return complete
        return c.get(f"/api/v1/jobs/{complete.json()['job_id']}")

    @staticmethod
    def _media_files(media_path: Path) -> list[Path]:
        """Return files under media_path, excluding the tmp_chunks staging area."""
        return [p for p in media_path.rglob("*") if p.is_file() and "tmp_chunks" not in p.parts]

    def test_init_job_is_pollable_before_any_bytes_transferred(self, client):
        """Closes 2B: job creation moved from /complete to /init, so job_id
        is usable against GET /api/v1/jobs/{id} immediately, before any
        chunk has been PUT and long before /complete is ever called."""
        c, _media_path = client
        init = c.post(
            "/api/v1/uploads/software-games/init",
            json={"kind": "file", "title": None, "files": [{"name": "doom.iso", "size": 4, "chunks": 1}]},
        )
        assert init.status_code == 200, init.text
        job_id = init.json()["job_id"]

        job_resp = c.get(f"/api/v1/jobs/{job_id}")
        assert job_resp.status_code == 200, job_resp.text
        job = job_resp.json()
        assert job["status"] == "processing"
        assert job["kind"] == "upload"

    def test_same_job_id_threads_from_init_through_finalize(self, client):
        """The job /init creates is the same one /complete backgrounds and
        finalize_background eventually completes, not a second job minted
        somewhere along the way."""
        c, _media_path = client
        init = c.post(
            "/api/v1/uploads/software-games/init",
            json={"kind": "file", "title": None, "files": [{"name": "doom.iso", "size": 4, "chunks": 1}]},
        )
        job_id = init.json()["job_id"]
        uid = init.json()["upload_id"]

        c.put(
            f"/api/v1/uploads/software-games/{uid}/chunks/0/0",
            files={"chunk": ("doom.iso", b"data", "application/octet-stream")},
        )
        complete = c.post(f"/api/v1/uploads/software-games/{uid}/complete")
        assert complete.status_code == 202, complete.text
        assert complete.json()["job_id"] == job_id

        job = c.get(f"/api/v1/jobs/{job_id}").json()
        assert job["status"] == "done", job

    def test_successful_upload_creates_library_item(self, client):
        c, media_path = client
        resp = self._upload(c, "Doom.iso", b"not a real iso but enough bytes")
        assert resp.status_code == 200, resp.text
        job = resp.json()
        assert job["status"] == "done", job
        assert job["result"]["title"] == "Doom"
        files = self._media_files(media_path)
        assert len(files) == 1
        assert files[0].is_relative_to(media_path.resolve())

    def test_missing_file_field_is_422(self, client):
        c, _ = client
        resp = c.post(
            "/api/v1/uploads/software-games/init",
            json={"kind": "file", "title": None, "files": []},
        )
        assert resp.status_code == 422

    def test_oversized_file_rejected_and_cleaned_up(self, client):
        c, media_path = client
        from backend.service.utils.upload_utils import DEFAULT_MAX_BYTES
        resp = c.post(
            "/api/v1/uploads/software-games/init",
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
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "done", resp.text
        files = self._media_files(media_path)
        assert all(f.is_relative_to(media_path.resolve()) for f in files)

    def test_duplicate_content_on_still_tracked_item_is_rejected_without_extra_copy(self, client):
        """Uploading byte-identical content under a different filename, while the
        first upload is still a tracked library item, triggers _ItemAlreadyExists
        inside finalize_background → the job ends in 'error' with a clean
        message, leaving no second physical copy behind."""
        c, media_path = client
        content = b"identical bytes for dedup test"
        first = self._upload(c, "doom.iso", content)
        assert first.json()["status"] == "done", first.text

        second = self._upload(c, "doom-copy.iso", content)
        assert second.status_code == 200, second.text
        second_job = second.json()
        assert second_job["status"] == "error", second_job
        assert second_job["error"] == "This upload's content is already in the library."

        assert len(self._media_files(media_path)) == 1

    def test_duplicate_content_after_remove_reuses_orphaned_file(self, client):
        """The realistic re-add scenario: an item is removed (file kept on disk,
        per remove-not-delete semantics), then the same content is re-uploaded.
        The orphaned file is reused in place rather than copied again."""
        c, media_path = client
        content = b"identical bytes for dedup test"
        first = self._upload(c, "doom.iso", content)
        assert first.json()["status"] == "done", first.text
        collection_id = first.json()["result"]["id"]

        token_resp = c.post(f"/api/v1/game-item-bundle/{collection_id}/confirm-delete")
        assert token_resp.status_code == 200, token_resp.text
        token = token_resp.json()["confirmation_token"]
        del_resp = c.delete(f"/api/v1/game-item-bundle/{collection_id}", params={"confirmation_token": token})
        assert del_resp.status_code == 204, del_resp.text

        files_after_remove = self._media_files(media_path)
        assert len(files_after_remove) == 1  # remove, not delete — file stays on disk
        original_file = files_after_remove[0]

        second = self._upload(c, "doom-readded.iso", content)
        assert second.json()["status"] == "done", second.text
        assert second.json()["result"]["reused_existing_media"] is True

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

        # Dedup is checked against the games domain root (media_path/games),
        # not media_path itself — see path_utils.library_domain_root.
        root = (media_path / "games").resolve()
        rglob_calls_on_root = []
        original_rglob = media_dup_index.Path.rglob

        def spy_rglob(self, pattern):
            if self == root:
                rglob_calls_on_root.append(pattern)
            return original_rglob(self, pattern)

        monkeypatch.setattr(media_dup_index.Path, "rglob", spy_rglob)

        content = b"identical bytes for warm-index test"
        first = self._upload(c, "warm-a.iso", content)
        assert first.json()["status"] == "done", first.text
        assert len(rglob_calls_on_root) == 1  # initial index build

        second = self._upload(c, "warm-b.iso", content)
        assert second.json()["status"] == "error", second.text  # still-tracked duplicate, via the index
        assert len(rglob_calls_on_root) == 1  # no rebuild — index stayed warm

    def test_index_does_not_return_stale_match_after_file_removed_from_disk(self, client):
        """Confirms re-uploading genuinely-gone content is treated as new rather
        than falsely matched against a now-stale index entry — exercises the
        index's self-healing path for out-of-band filesystem deletions."""
        c, media_path = client
        content = b"identical bytes for stale-index test"
        first = self._upload(c, "gone.iso", content)
        assert first.json()["status"] == "done", first.text

        original_files = self._media_files(media_path)
        assert len(original_files) == 1
        original_path = original_files[0]
        original_path.unlink()  # simulates the file genuinely disappearing

        second = self._upload(c, "gone-again.iso", content)
        assert second.json()["status"] == "done", second.text
        assert second.json()["result"]["reused_existing_media"] is False

        new_files = self._media_files(media_path)
        assert len(new_files) == 1
        assert new_files[0] != original_path
        assert new_files[0].exists()


# ---------------------------------------------------------------------------
# POST /api/v1/media-items/upload — generic Media-archive upload (doc 03).
#
# Repurposed from the old OS-image-only route: no era/media_type form fields
# anymore, gated on can_manage_media, and stages bytes under MEDIA_PATH only —
# it never creates a MediaItem row itself (a separate POST /api/v1/media-items call
# with the returned path does that; see media.py's module comment).
# ---------------------------------------------------------------------------

class TestMediaArchiveUploadRoute:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.api.routes import media
        from backend.core.dependencies import get_active_user

        media_path = tmp_path / "media_archive"
        media_path.mkdir()

        import backend.core.settings as settings_mod
        monkeypatch.setattr(
            settings_mod,
            "get_settings",
            lambda: _FakeSettings({"MEDIA_PATH": str(media_path)}),
        )

        app = FastAPI()
        app.include_router(media.router)
        app.dependency_overrides[get_active_user] = _owner_user

        with TestClient(app) as c:
            yield c, media_path

    def test_missing_filename_is_422(self, client):
        c, _ = client
        resp = c.post(
            "/api/v1/media-items/upload",
            files={"file": ("", b"data", "application/octet-stream")},
        )
        assert resp.status_code == 422

    def test_successful_archive_upload(self, client):
        c, media_path = client
        resp = c.post(
            "/api/v1/media-items/upload",
            files={"file": ("soundtrack.zip", b"archive-bytes", "application/octet-stream")},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        result_path = Path(body["path"]).resolve()
        assert result_path.is_relative_to(media_path.resolve())
        assert result_path.exists()
        assert body["size_bytes"] == len(b"archive-bytes")
        assert body["slug"]

    def test_traversal_filename_stays_inside_media_root(self, client):
        c, media_path = client
        resp = c.post(
            "/api/v1/media-items/upload",
            files={"file": ("../../../etc/passwd", b"payload", "application/octet-stream")},
        )
        assert resp.status_code == 200, resp.text
        result_path = Path(resp.json()["path"]).resolve()
        assert result_path.is_relative_to(media_path.resolve())

    def test_requires_can_manage_media_permission(self, client):
        c, _ = client
        from backend.core.dependencies import get_active_user
        from backend.models.user import UserItem
        c.app.dependency_overrides[get_active_user] = lambda: UserItem(
            id=2, name="Guest", is_owner=False, can_manage_media=False,
        )
        resp = c.post(
            "/api/v1/media-items/upload",
            files={"file": ("soundtrack.zip", b"data", "application/octet-stream")},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/v1/environment-items/{slug}/install-media — OS install-media upload
# (doc 04). This is where the old media_type='os' logic actually moved to:
# slug-scoped to a real Environment row, era read from that row (not trusted
# form input), gated on can_manage_environment, PC-era validated.
# ---------------------------------------------------------------------------

class TestEnvironmentInstallMediaRoute:
    @pytest.fixture
    def client(self, tmp_path, mem_db_session, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.api.routes import environments
        from backend.core.database import get_db
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
        app.include_router(environments.router)
        app.dependency_overrides[get_active_user] = _owner_user
        app.dependency_overrides[get_db] = lambda: mem_db_session

        with TestClient(app) as c:
            yield c, os_path, mem_db_session

    @staticmethod
    def _make_environment(db, **overrides):
        from backend.models.environment import EnvironmentItem
        kwargs = dict(name="Win98 Box", era="win98", emulator_slug="86box", slug="win98-box")
        kwargs.update(overrides)
        environment = EnvironmentItem(**kwargs)
        db.add(environment)
        db.commit()
        db.refresh(environment)
        return environment

    def test_unknown_slug_is_404(self, client):
        c, _, _db = client
        resp = c.post(
            "/api/v1/environment-items/not-a-slug/install-media",
            files={"file": ("win98.iso", b"data", "application/octet-stream")},
        )
        assert resp.status_code == 404

    def test_non_pc_era_environment_rejected(self, client):
        c, _, db = client
        self._make_environment(db, era="ps1", emulator_slug="duckstation", slug="ps1-box")
        resp = c.post(
            "/api/v1/environment-items/ps1-box/install-media",
            files={"file": ("game.iso", b"data", "application/octet-stream")},
        )
        assert resp.status_code == 422
        assert "PC-era" in resp.json()["detail"]

    def test_missing_filename_is_422(self, client):
        c, _, db = client
        self._make_environment(db)
        resp = c.post(
            "/api/v1/environment-items/win98-box/install-media",
            files={"file": ("", b"data", "application/octet-stream")},
        )
        assert resp.status_code == 422

    def test_successful_install_media_upload_is_scoped_under_environment_era(self, client):
        c, os_path, db = client
        self._make_environment(db)
        resp = c.post(
            "/api/v1/environment-items/win98-box/install-media",
            files={"file": ("win98.iso", b"disk-bytes", "application/octet-stream")},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        result_path = Path(body["path"]).resolve()
        assert result_path.is_relative_to((os_path / "win98").resolve())
        assert result_path.exists()
        assert body["size_bytes"] == len(b"disk-bytes")

    def test_traversal_filename_stays_inside_os_root(self, client):
        c, os_path, db = client
        self._make_environment(db)
        resp = c.post(
            "/api/v1/environment-items/win98-box/install-media",
            files={"file": ("../../../etc/passwd", b"payload", "application/octet-stream")},
        )
        assert resp.status_code == 200, resp.text
        result_path = Path(resp.json()["path"]).resolve()
        assert result_path.is_relative_to(os_path.resolve())

    def test_requires_can_manage_environment_permission(self, client):
        c, _, db = client
        self._make_environment(db)
        from backend.core.dependencies import get_active_user
        from backend.models.user import UserItem
        c.app.dependency_overrides[get_active_user] = lambda: UserItem(
            id=2, name="Guest", is_owner=False, can_manage_environment=False,
        )
        resp = c.post(
            "/api/v1/environment-items/win98-box/install-media",
            files={"file": ("win98.iso", b"data", "application/octet-stream")},
        )
        assert resp.status_code == 403
