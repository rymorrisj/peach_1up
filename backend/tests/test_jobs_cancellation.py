"""Tests for backend/core/jobs.py's request_cancel and retention sweep.

No existing test file is scoped to jobs.py's own behavior (other test files
only import it to clear/reset its module-level state as a fixture
concern), so this is a new file rather than an extension.

No real sleep anywhere: retention is driven by monkeypatching jobs.time.time,
never a real wall-clock wait.
"""

import pytest


@pytest.fixture(autouse=True)
def _reset_jobs():
    """_jobs/_cancel_events are module-level, in-memory, and shared across
    the whole test process; clear before and after each test so one test's
    job never leaks into another's assertions."""
    from backend.core import jobs
    jobs._jobs.clear()
    jobs._cancel_events.clear()
    yield
    jobs._jobs.clear()
    jobs._cancel_events.clear()


class TestRequestCancel:
    def test_processing_job_flips_to_cancelling_and_sets_the_flag(self):
        """Locks in the cancellation state machine: request_cancel on a live
        'processing' job flips its status and sets the cooperative-cancel
        flag, both readable back from the module's own accessors
        (jobs.get / jobs.cancel_requested), not just the returned dict."""
        from backend.core import jobs
        job_id = jobs.create("upload")

        result = jobs.request_cancel(job_id)

        assert result is not None
        assert result["status"] == "cancelling"
        assert jobs.get(job_id)["status"] == "cancelling"
        assert jobs.cancel_requested(job_id) is True

    def test_already_done_job_is_a_noop(self):
        """Locks in the other half of the state machine: cancellation is not
        retroactive against a job that already reached a terminal state,
        request_cancel must return None and leave the job's state
        untouched (no resurrection, no field mutated)."""
        from backend.core import jobs
        job_id = jobs.create("upload")
        jobs.complete(job_id, result={"ok": True}, message="Finished")
        before = jobs.get(job_id)

        result = jobs.request_cancel(job_id)

        assert result is None
        after = jobs.get(job_id)
        assert after == before
        assert jobs.cancel_requested(job_id) is False


class TestRetentionSweep:
    def test_finished_job_past_retain_seconds_is_dropped_processing_job_is_not(self, monkeypatch):
        """Locks in orphan/retention-sweep correctness via _sweep_locked
        (invoked by both create() and list_recent()): a finished job whose
        updated_at is older than _RETAIN_SECONDS is dropped on the next
        such call, while a processing job is retained regardless of age,
        _sweep_locked only ever considers status != 'processing'."""
        from backend.core import jobs

        t0 = 1_000_000.0
        monkeypatch.setattr(jobs.time, "time", lambda: t0)

        finished_id = jobs.create("upload")
        jobs.complete(finished_id, result={"ok": True})

        processing_id = jobs.create("upload")

        # Advance the clock well past the retention window, no real sleep.
        monkeypatch.setattr(jobs.time, "time", lambda: t0 + jobs._RETAIN_SECONDS + 10)

        remaining = jobs.list_recent()
        remaining_ids = {j["id"] for j in remaining}

        assert finished_id not in remaining_ids
        assert jobs.get(finished_id) is None

        assert processing_id in remaining_ids
        retained = jobs.get(processing_id)
        assert retained is not None
        assert retained["status"] == "processing"
