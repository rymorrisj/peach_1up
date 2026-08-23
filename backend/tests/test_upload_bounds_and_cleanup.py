"""Unit-level tests for backend/service/uploads/core.py's init_session chunk-
count bounds, reassemble's failure-cleanup guarantee, and sweep_orphans.

Created as a separate file from test_upload.py rather than extending it:
that file exercises this module exclusively through the HTTP route layer
(POST .../init -> PUT .../chunks -> POST .../complete), and already covers
init_session's basic manifest shape (missing files, oversized total) and
reassemble's happy path at that level. The tests here call
init_session/reassemble/sweep_orphans directly, a different (unit) altitude
aimed specifically at the chunk-count arithmetic and the on-failure/on-sweep
filesystem cleanup, neither of which the route-level tests exercise.

No real subprocess/thread/sleep anywhere: sweep_orphans' TTL comparison is
driven by monkeypatching core.time.time, never a real filesystem mtime wait.
"""

import pytest


class _FakeSettings:
    def __init__(self, env: dict):
        self._env = env

    def get_env_var(self, key):
        return self._env.get(key, "")

    def get(self, key, default=None):
        return self._env.get(key, default)


def _patch_library_path(monkeypatch, tmp_path):
    import backend.core.settings as settings_mod
    monkeypatch.setattr(settings_mod, "get_settings", lambda: _FakeSettings({"LIBRARY_PATH": str(tmp_path)}))


@pytest.fixture(autouse=True)
def _reset_upload_sessions():
    """core.py's _sessions dict is module-level, in-memory, and shared across
    the whole test process (matching core.jobs' own _jobs dict), clear it
    before and after each test so one test's session never leaks into
    another's assertions."""
    from backend.service.uploads import core
    core._sessions.clear()
    yield
    core._sessions.clear()


# ---------------------------------------------------------------------------
# init_session: chunk-count bounds (the exhaustion-guard regression)
# ---------------------------------------------------------------------------

class TestInitSessionChunkCountBounds:
    def test_chunk_count_below_the_floor_is_rejected(self, tmp_path, monkeypatch):
        """Locks in the chunk-exhaustion floor: a declared chunk count that
        physically cannot carry the declared size within the per-chunk
        ceiling (fewer chunks than ceil(size / chunk_max_bytes)) is
        rejected as an impossible declaration."""
        import math
        from backend.service.uploads import core
        _patch_library_path(monkeypatch, tmp_path)

        chunk_max_bytes = 1024
        size = 5000
        min_required = math.ceil(size / chunk_max_bytes)
        assert min_required == 5

        with pytest.raises(ValueError, match="too low to carry its declared size"):
            core.init_session(
                "file", "Test",
                [{"name": "big.iso", "size": size, "chunks": min_required - 1}],
                chunk_max_bytes,
            )

    def test_chunk_count_above_max_chunks_per_file_is_rejected(self, tmp_path, monkeypatch):
        """Locks in the chunk-exhaustion ceiling: a declared chunk count
        above the real _MAX_CHUNKS_PER_FILE constant is rejected regardless
        of declared size. Size is picked (the 25 GB absolute cap) large
        enough that the size-derived ceiling (ceil(size/_MIN_CHUNK_BYTES))
        exceeds _MAX_CHUNKS_PER_FILE, so the constant itself, not the size
        term, is what's confirmed to bind here."""
        from backend.service.uploads import core
        from backend.service.utils.upload_utils import DEFAULT_MAX_BYTES
        _patch_library_path(monkeypatch, tmp_path)

        assert core._MAX_CHUNKS_PER_FILE == 100_000
        size = DEFAULT_MAX_BYTES
        chunk_max_bytes = 8 * 1024 * 1024

        with pytest.raises(ValueError, match=r"\(max 100000\)"):
            core.init_session(
                "file", "Test",
                [{"name": "big.iso", "size": size, "chunks": core._MAX_CHUNKS_PER_FILE + 1}],
                chunk_max_bytes,
            )

    def test_realistic_frontend_manifest_finer_than_the_cap_is_accepted(self, tmp_path, monkeypatch):
        """The exact regression the code comment calls out: the previous
        revision divided by chunk_max_bytes for the UPPER bound too, which
        would reject this exact manifest (ceil(50 MB / 8 MB) = 7, but this
        declares 20 chunks, chunked finer than the server's 8 MB per-chunk
        ceiling, well under _MIN_CHUNK_BYTES-derived absurdity territory).
        A real client chunking finer than the cap must be accepted, not
        rejected as if it were exhausting staging entries."""
        from backend.service.uploads import core
        _patch_library_path(monkeypatch, tmp_path)

        size = 50 * 1024 * 1024
        chunk_max_bytes = 8 * 1024 * 1024
        chunks = 20  # ~2.5 MB per chunk

        upload_id = core.init_session(
            "file", "Test", [{"name": "game.iso", "size": size, "chunks": chunks}], chunk_max_bytes,
        )

        session = core.get_session(upload_id)
        assert session is not None
        assert session["files"][0]["chunks"] == chunks


# ---------------------------------------------------------------------------
# reassemble: disk-leak-on-failure prevention
# ---------------------------------------------------------------------------

class TestReassembleFailureCleanup:
    # init_session's plausibility check (_MIN_CHUNK_BYTES) rejects a declared
    # size/chunk-count pair that couldn't come from a real client, so these
    # tests can't use a toy size like 20 bytes for 2 chunks. Use a declared
    # size/chunk_max_bytes pair that lands exactly on both bounds instead
    # (2 chunks required and allowed); the actual bytes written to each
    # .part file stay tiny since only reassemble's failure paths, not the
    # byte content, are under test here.
    def _start_session(self, tmp_path, monkeypatch, size: int, chunks: int, chunk_max_bytes: int):
        from backend.service.uploads import core
        _patch_library_path(monkeypatch, tmp_path)
        upload_id = core.init_session(
            "file", "Test", [{"name": "game.iso", "size": size, "chunks": chunks}], chunk_max_bytes,
        )
        session = core.get_session(upload_id)
        return core, upload_id, session["dir"]

    def test_missing_part_file_raises_and_leaves_no_dest_dir_or_staging_dir(self, tmp_path, monkeypatch):
        """Locks in disk-leak-on-failure prevention: a missing .part file
        must abort reassembly and leave neither the partial dest_dir nor
        the staging dir behind."""
        from backend.service.uploads import core as core_mod
        size = 2 * core_mod._MIN_CHUNK_BYTES
        core, upload_id, session_dir = self._start_session(
            tmp_path, monkeypatch, size=size, chunks=2, chunk_max_bytes=core_mod._MIN_CHUNK_BYTES,
        )
        file_dir = session_dir / "0"
        file_dir.mkdir(parents=True)
        (file_dir / "0.part").write_bytes(b"x" * 10)
        # chunk 1's .part is deliberately never written.

        domain_root = tmp_path / "domain"

        with pytest.raises(ValueError, match="Missing chunk 1"):
            core.reassemble(upload_id, domain_root)

        assert domain_root.is_dir()  # created for real, but must end up empty
        assert list(domain_root.iterdir()) == []
        assert not session_dir.exists()
        assert core.get_session(upload_id) is None

    def test_size_mismatch_raises_and_leaves_no_dest_dir_or_staging_dir(self, tmp_path, monkeypatch):
        """Same cleanup guarantee, triggered by the other failure mode: all
        chunks present, but the reassembled total disagrees with the
        declared size."""
        from backend.service.uploads import core as core_mod
        size = 2 * core_mod._MIN_CHUNK_BYTES
        core, upload_id, session_dir = self._start_session(
            tmp_path, monkeypatch, size=size, chunks=2, chunk_max_bytes=core_mod._MIN_CHUNK_BYTES,
        )
        file_dir = session_dir / "0"
        file_dir.mkdir(parents=True)
        (file_dir / "0.part").write_bytes(b"x" * 10)
        (file_dir / "1.part").write_bytes(b"x" * 5)  # 15 total, declared `size`

        domain_root = tmp_path / "domain"

        with pytest.raises(ValueError, match=f"is 15 bytes, expected {size} bytes"):
            core.reassemble(upload_id, domain_root)

        assert domain_root.is_dir()
        assert list(domain_root.iterdir()) == []
        assert not session_dir.exists()
        assert core.get_session(upload_id) is None


# ---------------------------------------------------------------------------
# sweep_orphans: orphan-sweep correctness
# ---------------------------------------------------------------------------

class TestSweepOrphans:
    def test_staging_dir_older_than_ttl_is_removed(self, tmp_path, monkeypatch):
        from backend.service.uploads import core
        _patch_library_path(monkeypatch, tmp_path)

        root = core.tmp_root()
        root.mkdir(parents=True, exist_ok=True)
        orphan_dir = root / "orphan-upload-id"
        orphan_dir.mkdir()

        real_time = core.time.time()
        ttl = 60.0
        # No live session was ever registered for this dir (simulates a
        # crash-lost session, sweep_orphans' documented target); push the
        # clock forward instead of sleeping so its real mtime reads as
        # older than ttl_seconds.
        monkeypatch.setattr(core.time, "time", lambda: real_time + ttl + 10)

        removed = core.sweep_orphans(ttl)

        assert removed == 1
        assert not orphan_dir.exists()

    def test_staging_dir_younger_than_ttl_is_left_alone(self, tmp_path, monkeypatch):
        from backend.service.uploads import core
        _patch_library_path(monkeypatch, tmp_path)

        root = core.tmp_root()
        root.mkdir(parents=True, exist_ok=True)
        young_dir = root / "young-upload-id"
        young_dir.mkdir()

        real_time = core.time.time()
        ttl = 3600.0
        monkeypatch.setattr(core.time, "time", lambda: real_time + 1)

        removed = core.sweep_orphans(ttl)

        assert removed == 0
        assert young_dir.is_dir()
