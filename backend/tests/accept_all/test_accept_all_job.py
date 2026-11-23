"""Accept All as a background job (backend/service/games/accept_all_job.py and
the accept-metadata-assets routes in backend/api/routes/game_metadata.py):

- synchronous pre-checks answer before any job exists (403, 404, 413, 409, 422)
- job states, progress counts, the current asset label
- every failure names its real reason as {code, message}, leaks no URL or
  exception text, and removes every file and row the apply created
- cancel stops the job and cleans up like a failure
- the apply locks are released on done, failed, cancelled and any exception

Downloads are replaced by the fake in conftest.py. Jobs are run
by calling the BackgroundTasks entries directly, on the test's own engine.
"""

import errno
import time

import httpx2
import pytest
from fastapi import HTTPException

from backend.service.utils.asset_fetch import AssetFetchFailure
from backend.tests.accept_all.helpers import _BOX, _assets, _counts, _game, _game_with_discs, _url

_ROUTE = "/api/v1/game-items"


@pytest.fixture(autouse=True)
def _job_engine(db, monkeypatch):
    monkeypatch.setattr("backend.core.database.get_engine", lambda: db.get_bind())


def _start(db, game, assets, **kwargs):
    from fastapi import BackgroundTasks

    from backend.service.games import accept_all_job
    from backend.service.games.media_link import prepare_apply

    tasks = BackgroundTasks()
    job_id = accept_all_job.start(prepare_apply(game.id, assets, db, **kwargs), tasks)
    return job_id, tasks


def _run(tasks):
    for task in tasks.tasks:
        task.func(*task.args, **task.kwargs)


def _status(job_id):
    from backend.service.games import accept_all_job

    return accept_all_job.status(job_id)


def _assert_nothing_left(db, env):
    from backend.service.games import media_link

    assert _counts(db) == (0, 0, 0)
    assert env.files() == []
    assert env.staging_leftovers() == []
    assert media_link._running_applies == {}


class TestLifecycle:
    def test_queued_then_running_then_done(self, db, env):
        from backend.core import jobs
        from backend.service.games import media_link

        game = _game(db)
        job_id, tasks = _start(db, game, _assets(_url(0), _url(1)))

        queued = _status(job_id)
        assert (queued["state"], queued["done"], queued["total"], queued["error"]) == ("queued", 0, 2, None)
        assert ("game", game.id) in media_link._running_applies

        seen = []
        env.before_fetch = lambda url, kwargs: seen.append(_status(job_id))
        _run(tasks)

        assert [s["state"] for s in seen] == ["running", "running"]
        assert [(s["done"], s["total"], s["label"]) for s in seen] == [
            (0, 2, "screenshot (1 of 2)"),
            (1, 2, "screenshot (2 of 2)"),
        ]
        final = _status(job_id)
        assert (final["state"], final["done"], final["total"], final["label"], final["error"]) == (
            "done",
            2,
            2,
            None,
            None,
        )
        assert final["result"]["item_count"] == 2
        assert (final["result"]["created_count"], final["result"]["cover_set"]) == (2, False)
        assert jobs.get(job_id)["status"] == "done"
        assert len(env.files()) == 2
        assert media_link._running_applies == {}

    def test_a_keep_apply_with_only_known_urls_reports_nothing_created(self, db, env):
        game = _game(db)
        _, tasks = _start(db, game, _assets(_url(0)))
        _run(tasks)

        job_id, tasks = _start(db, game, _assets(_url(0)), previous_assets="keep")
        _run(tasks)

        result = _status(job_id)["result"]
        assert (_status(job_id)["state"], result["created_count"], result["cover_set"]) == ("done", 0, False)

    def test_game_cover_is_set_in_the_same_job(self, db, env):
        game, leaves = _game_with_discs(db)
        job_id, tasks = _start(
            db,
            game,
            _assets(_url(0), _BOX, types=["screenshot", "boxart_front"]),
            cover_asset_url=_BOX,
        )

        _run(tasks)

        assert _status(job_id)["state"] == "done"
        assert _status(job_id)["result"]["cover_set"] is True
        db.refresh(leaves[0])
        assert leaves[0].cover_art_path is not None and leaves[0].cover_art_path.endswith("boxart_front-1.jpg")

    def test_a_job_of_another_kind_is_not_visible_here(self):
        from backend.core import jobs

        scan_id = jobs.create("scan")
        try:
            assert _status(scan_id) is None
        finally:
            jobs._jobs.pop(scan_id, None)
        assert _status("missing") is None


_FAILURES = {
    "provider_5xx": (
        lambda: AssetFetchFailure(502, "x", kind="upstream", upstream_status=503),
        "provider_error",
        "TheGamesDB server returned 503.",
    ),
    "unusable_redirect": (
        lambda: HTTPException(502, "Asset redirect has no Location header"),
        "provider_error",
        "TheGamesDB server sent an unusable response.",
    ),
    "dns": (
        lambda: AssetFetchFailure(502, "x", kind="network"),
        "network_error",
        "Could not resolve the TheGamesDB server.",
    ),
    "connection": (
        lambda: httpx2.ConnectError("refused https://cdn.thegamesdb.net/a.jpg?apikey=SECRET"),
        "network_error",
        "Could not reach the TheGamesDB server.",
    ),
    "download_timeout": (
        lambda: httpx2.ReadTimeout("timed out https://cdn.thegamesdb.net/a.jpg"),
        "network_error",
        "Timed out waiting for the TheGamesDB server.",
    ),
    "too_large": (
        lambda: HTTPException(422, "Asset image exceeds the 20 MB size limit"),
        "asset_rejected",
        "20 MB size limit",
    ),
    "wrong_type": (
        lambda: HTTPException(422, "Asset url returned a disallowed content-type: text/html"),
        "asset_rejected",
        "disallowed content-type",
    ),
    "not_allowlisted": (
        lambda: HTTPException(422, "Asset url host is not an allowed metadata provider CDN"),
        "asset_rejected",
        "not an allowed metadata provider CDN",
    ),
    "time_budget": (
        lambda: AssetFetchFailure(422, "x", kind="time_budget"),
        "time_budget_exceeded",
        "time limit",
    ),
    "disk_full": (lambda: OSError(errno.ENOSPC, "No space left on device"), "disk_full", "The disk is full."),
    "permission": (lambda: PermissionError(errno.EACCES, "denied"), "permission_error", "Permission denied"),
    "other_io": (lambda: OSError(errno.EIO, "io"), "storage_error", "(EIO)"),
    "conflict": (
        lambda: HTTPException(409, "Asset destination already exists: a.jpg"),
        "conflict",
        "already exists",
    ),
    "unexpected": (lambda: RuntimeError("secret internals"), "internal_error", "Unexpected error."),
}


class TestFailures:
    @pytest.mark.parametrize("name", list(_FAILURES))
    def test_failure_names_its_reason_and_cleans_up(self, db, env, name):
        from backend.core import jobs

        make, code, fragment = _FAILURES[name]
        game = _game(db)
        job_id, tasks = _start(db, game, _assets(_url(0), _url(1)))

        def boom(url, kwargs):
            if url == _url(1):
                raise make()

        env.before_fetch = boom
        _run(tasks)

        status = _status(job_id)
        assert status["state"] == "failed"
        assert status["error"]["code"] == code
        assert fragment in status["error"]["message"]
        for leaked in ("SECRET", "secret internals", "https://", "apikey"):
            assert leaked not in status["error"]["message"]
        assert jobs.get(job_id)["error"] == status["error"]["message"]
        _assert_nothing_left(db, env)

    def test_failure_after_files_were_moved_removes_them(self, db, env, monkeypatch):
        import backend.service.utils.asset_fetch as asset_fetch_mod

        real_commit = asset_fetch_mod.commit_temp_image
        calls = []

        def _second_commit_fails(tmp, dest, *, overwrite):
            if calls:
                raise OSError(errno.ENOSPC, "No space left on device")
            real_commit(tmp, dest, overwrite=overwrite)
            calls.append(dest)

        monkeypatch.setattr(asset_fetch_mod, "commit_temp_image", _second_commit_fails)
        job_id, tasks = _start(db, _game(db), _assets(_url(0), _url(1)))

        _run(tasks)

        assert len(calls) == 1
        assert _status(job_id)["error"]["code"] == "disk_full"
        _assert_nothing_left(db, env)

    def test_unrecoverable_exception_still_ends_the_job_and_frees_the_locks(self, db, env):
        game = _game(db)
        job_id, tasks = _start(db, game, _assets(_url(0)))

        def boom(url, kwargs):
            raise KeyboardInterrupt

        env.before_fetch = boom
        with pytest.raises(KeyboardInterrupt):
            _run(tasks)

        assert _status(job_id)["state"] == "failed"
        _assert_nothing_left(db, env)

    def test_session_failure_before_the_apply_frees_the_locks(self, db, env, monkeypatch):
        def no_engine():
            raise RuntimeError("secret engine detail")

        monkeypatch.setattr("backend.core.database.get_engine", no_engine)
        job_id, tasks = _start(db, _game(db), _assets(_url(0)))

        _run(tasks)

        status = _status(job_id)
        assert (status["state"], status["error"]["code"]) == ("failed", "internal_error")
        assert "secret" not in status["error"]["message"]
        _assert_nothing_left(db, env)

    def test_scheduling_failure_frees_the_locks(self, db, env, monkeypatch):
        from backend.core import jobs
        from backend.service.games import media_link

        def no_job(*args, **kwargs):
            raise RuntimeError("registry down")

        monkeypatch.setattr(jobs, "create", no_job)

        with pytest.raises(RuntimeError):
            _start(db, _game(db), _assets(_url(0)))

        assert media_link._running_applies == {}

    def test_a_restart_leaves_no_job_or_lock_behind(self, db, env):
        """Jobs and locks live only in process memory (core.jobs,
        media_link._running_applies), so a restart starts with neither: no
        job can be left 'running', and the same game accepts a new apply."""
        from backend.core import jobs
        from backend.service.games import media_link

        game = _game(db)
        job_id, _ = _start(db, game, _assets(_url(0)))
        assert _status(job_id)["state"] == "queued"

        jobs._jobs.clear()
        jobs._cancel_events.clear()
        media_link._running_applies.clear()

        assert _status(job_id) is None
        job_id, tasks = _start(db, game, _assets(_url(0)))
        _run(tasks)
        assert _status(job_id)["state"] == "done"


class TestCancel:
    def test_cancel_between_downloads_stops_and_cleans_up(self, db, env):
        from backend.core import jobs

        job_id, tasks = _start(db, _game(db), _assets(_url(0), _url(1)))
        seen = []

        def cancel_on_first(url, kwargs):
            jobs.request_cancel(job_id)
            seen.append(_status(job_id))

        env.before_fetch = cancel_on_first
        _run(tasks)

        assert (seen[0]["state"], seen[0]["cancel_requested"]) == ("running", True)
        final = _status(job_id)
        assert (final["state"], final["error"]) == ("cancelled", None)
        assert env.fetched == [_url(0)]
        _assert_nothing_left(db, env)

    def test_cancel_just_before_the_commit_removes_files_already_moved(self, db, env, monkeypatch):
        import backend.service.utils.asset_fetch as asset_fetch_mod
        from backend.core import jobs

        real_commit = asset_fetch_mod.commit_temp_image
        moved = []

        def _spy(tmp, dest, *, overwrite):
            real_commit(tmp, dest, overwrite=overwrite)
            moved.append(dest)

        monkeypatch.setattr(asset_fetch_mod, "commit_temp_image", _spy)
        job_id, tasks = _start(db, _game(db), _assets(_url(0)))
        env.before_fetch = lambda url, kwargs: jobs.request_cancel(job_id)

        _run(tasks)

        assert len(moved) == 1
        assert _status(job_id)["state"] == "cancelled"
        _assert_nothing_left(db, env)

    def test_cancelled_replace_keeps_the_earlier_set(self, db, env):
        from backend.core import jobs
        from backend.service.games.media_link import prepare_apply, run_apply

        game = _game(db)
        run_apply(prepare_apply(game.id, _assets(_url(0)), db), db)
        before = _counts(db)
        before_files = env.files()
        job_id, tasks = _start(db, game, _assets(_url(1)), previous_assets="replace")
        env.before_fetch = lambda url, kwargs: jobs.request_cancel(job_id)

        _run(tasks)

        assert _status(job_id)["state"] == "cancelled"
        assert _counts(db) == before
        assert env.files() == before_files


@pytest.fixture
def client(db, env, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import backend.service.metadata_providers as providers_mod
    from backend.api.routes import game_metadata
    from backend.core.database import get_db
    from backend.core.dependencies import get_active_user
    from backend.models.user import UserItem

    monkeypatch.setattr(providers_mod, "is_metadata_fetch_enabled", lambda: True)
    monkeypatch.setattr(game_metadata, "_enforce_rate_limit", lambda *a, **k: None)
    app = FastAPI()
    app.include_router(game_metadata.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_active_user] = lambda: UserItem(id=1, name="Owner", is_owner=True)
    with TestClient(app) as c:
        yield c


def _post(c, game_id, urls, **extra):
    return c.post(
        f"{_ROUTE}/{game_id}/accept-metadata-assets",
        json={"assets": [{"url": u, "type": "screenshot"} for u in urls], **extra},
    )


def _job_count():
    from backend.core import jobs

    return len(jobs.list_recent())


class TestAcceptRoute:
    def test_accepted_with_202_and_the_job_finishes(self, client, db, env):
        resp = _post(client, _game(db).id, [_url(0), _url(1)])

        assert resp.status_code == 202, resp.text
        assert resp.json()["state"] == "queued"
        polled = client.get(f"{_ROUTE}/metadata-jobs/{resp.json()['job_id']}")
        assert polled.status_code == 200
        assert (polled.json()["state"], polled.json()["done"], polled.json()["total"]) == ("done", 2, 2)

    def test_409_then_keep_retry(self, client, db, env):
        game = _game(db)
        assert _post(client, game.id, [_url(0)]).status_code == 202
        jobs_before = _job_count()

        conflict = _post(client, game.id, [_url(1)])
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["existing_count"] == 1
        assert _job_count() == jobs_before

        retry = _post(client, game.id, [_url(1)], previous_assets="keep")
        assert retry.status_code == 202, retry.text
        assert env.fetched == [_url(0), _url(1)]

    def test_unknown_previous_assets_value_is_422(self, client, db, env):
        resp = _post(client, _game(db).id, [_url(0)], previous_assets="merge")

        assert resp.status_code == 422
        assert env.fetched == []

    def test_missing_game_is_404_and_starts_no_job(self, client, db, env):
        before = _job_count()

        resp = _post(client, 9999, [_url(0)])

        assert resp.status_code == 404
        assert _job_count() == before

    def test_too_many_assets_is_413_before_any_job(self, client, db, env):
        from backend.service.games.media_link import ACCEPT_ALL_MAX_ASSETS

        before = _job_count()

        resp = _post(client, _game(db).id, [_url(n) for n in range(ACCEPT_ALL_MAX_ASSETS + 1)])

        assert resp.status_code == 413
        assert _job_count() == before
        assert env.fetched == []

    def test_a_running_apply_is_409_and_its_lock_is_not_released(self, client, db, env, monkeypatch):
        import backend.service.games.media_link as media_link_mod

        game = _game(db)
        monkeypatch.setattr(media_link_mod, "_running_applies", {("game", game.id): time.monotonic()})
        before = _job_count()

        resp = _post(client, game.id, [_url(0)])

        assert resp.status_code == 409
        assert list(media_link_mod._running_applies) == [("game", game.id)]
        assert _job_count() == before

    def test_cover_asset_outside_the_submitted_ones_is_422_before_any_job(self, client, db, env):
        before = _job_count()

        resp = _post(client, _game_with_discs(db)[0].id, [_url(0)], cover_asset_url=_BOX)

        assert resp.status_code == 422
        assert _job_count() == before
        assert env.fetched == []

    def test_cover_is_applied_through_the_route(self, client, db, env):
        game, leaves = _game_with_discs(db)

        resp = client.post(
            f"{_ROUTE}/{game.id}/accept-metadata-assets",
            json={"assets": [{"url": _BOX, "type": "boxart_front"}], "cover_asset_url": _BOX},
        )

        assert resp.status_code == 202, resp.text
        db.refresh(leaves[0])
        assert leaves[0].cover_art_path is not None

    def test_disabled_setting_is_403_and_nothing_starts(self, client, db, env, monkeypatch):
        import backend.service.metadata_providers as providers_mod

        monkeypatch.setattr(providers_mod, "is_metadata_fetch_enabled", lambda: False)
        before = _job_count()

        resp = _post(client, _game(db).id, [_url(0)])

        assert resp.status_code == 403
        assert _job_count() == before

    def test_non_owner_is_403_on_start_status_and_cancel(self, client, db, env):
        from backend.core.dependencies import get_active_user
        from backend.models.user import UserItem

        game = _game(db)
        job_id = _post(client, game.id, [_url(0)]).json()["job_id"]
        client.app.dependency_overrides[get_active_user] = lambda: UserItem(id=2, name="Kid", is_owner=False)

        assert _post(client, game.id, [_url(1)]).status_code == 403
        assert client.get(f"{_ROUTE}/metadata-jobs/{job_id}").status_code == 403
        assert client.post(f"{_ROUTE}/metadata-jobs/{job_id}/cancel").status_code == 403


class TestStatusAndCancelRoutes:
    def test_unknown_job_is_404(self, client):
        assert client.get(f"{_ROUTE}/metadata-jobs/nope").status_code == 404
        assert client.post(f"{_ROUTE}/metadata-jobs/nope/cancel").status_code == 404

    def test_another_kind_of_job_is_404(self, client):
        from backend.core import jobs

        job_id = jobs.create("scan")
        try:
            assert client.get(f"{_ROUTE}/metadata-jobs/{job_id}").status_code == 404
            assert client.post(f"{_ROUTE}/metadata-jobs/{job_id}/cancel").status_code == 404
        finally:
            jobs._jobs.pop(job_id, None)

    def test_failed_job_status_carries_code_and_message(self, client, db, env):
        env.fail_on = _url(0)
        job_id = _post(client, _game(db).id, [_url(0)]).json()["job_id"]

        body = client.get(f"{_ROUTE}/metadata-jobs/{job_id}").json()

        assert body["state"] == "failed"
        assert body["error"]["code"] == "provider_error"
        assert "boom" not in body["error"]["message"]

    def test_cancel_before_the_job_starts_ends_cancelled(self, client, db, env):
        game = _game(db)
        job_id, tasks = _start(db, game, _assets(_url(0), _url(1)))

        cancelled = client.post(f"{_ROUTE}/metadata-jobs/{job_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["cancel_requested"] is True

        _run(tasks)

        assert client.get(f"{_ROUTE}/metadata-jobs/{job_id}").json()["state"] == "cancelled"
        _assert_nothing_left(db, env)

    def test_cancelling_a_finished_job_is_409(self, client, db, env):
        job_id = _post(client, _game(db).id, [_url(0)]).json()["job_id"]

        resp = client.post(f"{_ROUTE}/metadata-jobs/{job_id}/cancel")

        assert resp.status_code == 409
