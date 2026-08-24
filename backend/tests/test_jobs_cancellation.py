"""Tests for backend/core/jobs.py's cancellation state machine and retention
sweep.

No sleep anywhere: retention is driven by patching jobs.time.time.
"""

import pytest


@pytest.fixture(autouse=True)
def _reset_jobs():
    """_jobs/_cancel_events are module-level and shared across the whole test
    process; clear either side so jobs never leak between tests."""
    from backend.core import jobs
    jobs._jobs.clear()
    jobs._cancel_events.clear()
    yield
    jobs._jobs.clear()
    jobs._cancel_events.clear()


class TestRequestCancel:
    def test_processing_job_flips_to_cancelling_and_sets_the_flag(self):
        """Both the status flip and the cooperative-cancel flag are asserted
        through jobs.get / jobs.cancel_requested, not the returned dict, since
        the running job loop reads them that way."""
        from backend.core import jobs
        job_id = jobs.create("upload")

        result = jobs.request_cancel(job_id)

        assert result is not None
        assert result["status"] == "cancelling"
        assert jobs.get(job_id)["status"] == "cancelling"
        assert jobs.cancel_requested(job_id) is True

    def test_already_done_job_is_a_noop(self):
        """Cancellation is not retroactive: a terminal job must come back None
        with no field mutated, never resurrected into 'cancelling'."""
        from backend.core import jobs
        job_id = jobs.create("upload")
        jobs.complete(job_id, result={"ok": True}, message="Finished")
        before = jobs.get(job_id)

        result = jobs.request_cancel(job_id)

        assert result is None
        after = jobs.get(job_id)
        assert after == before
        assert jobs.cancel_requested(job_id) is False


    def test_unknown_job_id_returns_none(self):
        """A cancel arriving after the job was swept must not raise or
        register a flag for an id that no longer exists."""
        from backend.core import jobs
        assert jobs.request_cancel("no-such-job-id") is None
        assert jobs.cancel_requested("no-such-job-id") is False


class TestUpdateProgressClamp:
    def test_progress_is_clamped_to_the_zero_to_one_range(self):
        """Callers divide bytes by a client-declared total, so a bogus
        manifest can push the ratio outside 0..1 and past the UI's bar."""
        from backend.core import jobs
        job_id = jobs.create("upload")

        jobs.update(job_id, progress=2.5)
        assert jobs.get(job_id)["progress"] == 1.0

        jobs.update(job_id, progress=-0.5)
        assert jobs.get(job_id)["progress"] == 0.0

    def test_update_on_a_swept_job_is_a_noop(self):
        """A worker thread still reporting progress after its job was swept
        must not resurrect the entry."""
        from backend.core import jobs
        jobs.update("no-such-job-id", progress=0.5, message="…")
        assert jobs.get("no-such-job-id") is None


class TestRetentionSweep:
    def test_finished_job_past_retain_seconds_is_dropped_processing_job_is_not(self, monkeypatch):
        """_sweep_locked runs from both create() and list_recent(). A finished
        job past _RETAIN_SECONDS is dropped; a processing job is kept at any
        age, since a long upload must not lose its own progress record."""
        from backend.core import jobs

        t0 = 1_000_000.0
        monkeypatch.setattr(jobs.time, "time", lambda: t0)

        finished_id = jobs.create("upload")
        jobs.complete(finished_id, result={"ok": True})

        processing_id = jobs.create("upload")

        monkeypatch.setattr(jobs.time, "time", lambda: t0 + jobs._RETAIN_SECONDS + 10)

        remaining = jobs.list_recent()
        remaining_ids = {j["id"] for j in remaining}

        assert finished_id not in remaining_ids
        assert jobs.get(finished_id) is None

        assert processing_id in remaining_ids
        retained = jobs.get(processing_id)
        assert retained is not None
        assert retained["status"] == "processing"

    def test_sweep_also_drops_the_swept_jobs_cancel_event(self, monkeypatch):
        """_cancel_events is a parallel dict keyed by job_id. Leaving an entry
        behind after its job is gone is an unbounded leak, since the registry
        is process-lifetime."""
        from backend.core import jobs

        t0 = 1_000_000.0
        monkeypatch.setattr(jobs.time, "time", lambda: t0)

        finished_id = jobs.create("upload")
        jobs.complete(finished_id, result={"ok": True})
        assert finished_id in jobs._cancel_events

        monkeypatch.setattr(jobs.time, "time", lambda: t0 + jobs._RETAIN_SECONDS + 10)
        jobs.list_recent()

        assert finished_id not in jobs._cancel_events


# INTEGRATION TEST NEEDED: jobs.py's stated thread-safety, background worker
# threads mutating a job while the GET /api/v1/jobs poll reads it from the
# event loop. Every test here is single-threaded, so the _lock discipline
# itself (and _sweep_locked running under a poll concurrent with a create)
# is unverified.
