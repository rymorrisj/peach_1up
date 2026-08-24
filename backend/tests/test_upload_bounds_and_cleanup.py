"""Unit-level tests for backend/service/uploads/core.py's init_session chunk-
count bounds, reassemble's failure-cleanup guarantee, and sweep_orphans.

test_upload.py drives this module through the HTTP route layer and covers
the manifest shape and reassemble's happy path there. These call
init_session/reassemble/sweep_orphans directly, for the chunk-count
arithmetic and the on-failure/on-sweep filesystem cleanup the route-level
tests never reach.

No sleep anywhere: sweep_orphans' TTL comparison is driven by patching
core.time.time, never a real mtime wait.
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
    """_sessions is module-level and shared across the whole test process;
    clear it either side so sessions never leak between tests."""
    from backend.service.uploads import core
    core._sessions.clear()
    yield
    core._sessions.clear()


# ---------------------------------------------------------------------------
# init_session: chunk-count bounds (the exhaustion-guard regression)
# ---------------------------------------------------------------------------

class TestInitSessionChunkCountBounds:
    def test_chunk_count_below_the_floor_is_rejected(self, tmp_path, monkeypatch):
        """Floor: fewer chunks than ceil(size / chunk_max_bytes) cannot carry
        the declared size, since no single chunk may exceed the cap."""
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
        """Ceiling: _MAX_CHUNKS_PER_FILE binds regardless of declared size.
        Size is the absolute cap so that the size-derived ceiling
        (ceil(size/_MIN_CHUNK_BYTES)) is the larger of the two, making the
        constant the term under test."""
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
        """The regression the code comment calls out: dividing by
        chunk_max_bytes for the upper bound too would reject this manifest
        (ceil(50 MB / 8 MB) = 7 vs the 20 declared), and with it every upload
        the bundled frontend produces over 8 MB."""
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
    # init_session's plausibility check rules out a toy size like 20 bytes for
    # 2 chunks, so the declared size/chunk_max_bytes pair below lands exactly
    # on both bounds. The .part files themselves stay tiny: only reassemble's
    # failure paths are under test, not the byte content.
    def _start_session(self, tmp_path, monkeypatch, size: int, chunks: int, chunk_max_bytes: int):
        from backend.service.uploads import core
        _patch_library_path(monkeypatch, tmp_path)
        upload_id = core.init_session(
            "file", "Test", [{"name": "game.iso", "size": size, "chunks": chunks}], chunk_max_bytes,
        )
        session = core.get_session(upload_id)
        return core, upload_id, session["dir"]

    def test_missing_part_file_raises_and_leaves_no_dest_dir_or_staging_dir(self, tmp_path, monkeypatch):
        """A missing .part must abort reassembly and leave neither the partial
        dest_dir nor the staging dir behind."""
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
        """Same cleanup, other failure mode: all chunks present, reassembled
        total disagrees with the declared size."""
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
        # No live session registered for this dir, the crash-lost case
        # sweep_orphans exists for. The clock moves instead of the mtime.
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

    def test_dir_of_a_live_session_is_never_swept_however_old(self, tmp_path, monkeypatch):
        """The sweep runs on a timer against a session that may legitimately
        outlive the TTL (a slow multi-GB upload). Sweeping a live session's
        dir would delete chunks out from under an in-flight transfer."""
        from backend.service.uploads import core
        _patch_library_path(monkeypatch, tmp_path)

        size = 2 * core._MIN_CHUNK_BYTES
        upload_id = core.init_session(
            "file", "Test",
            [{"name": "game.iso", "size": size, "chunks": 2}],
            core._MIN_CHUNK_BYTES,
        )
        live_dir = core.get_session(upload_id)["dir"]

        orphan_dir = core.tmp_root() / "orphan-upload-id"
        orphan_dir.mkdir()

        real_time = core.time.time()
        ttl = 60.0
        monkeypatch.setattr(core.time, "time", lambda: real_time + ttl + 10)

        removed = core.sweep_orphans(ttl)

        assert removed == 1
        assert live_dir.is_dir()
        assert not orphan_dir.exists()

    def test_loose_file_in_the_staging_root_is_not_removed(self, tmp_path, monkeypatch):
        """Only session directories are swept, so a stray file never counts
        toward the removed total or gets deleted as if it were one."""
        from backend.service.uploads import core
        _patch_library_path(monkeypatch, tmp_path)

        root = core.tmp_root()
        root.mkdir(parents=True, exist_ok=True)
        loose = root / "stray.txt"
        loose.write_text("x")

        real_time = core.time.time()
        monkeypatch.setattr(core.time, "time", lambda: real_time + 10_000)

        removed = core.sweep_orphans(60.0)

        assert removed == 0
        assert loose.is_file()


# INTEGRATION TEST NEEDED: store_chunk's cumulative-bytes guard under real
# concurrency. The read-check-write of slot["received_bytes"] is split across
# two _lock acquisitions with the disk write in between, so verifying that
# parallel chunk PUTs for one file cannot overshoot the declared size needs
# real concurrent requests, not a single-threaded call sequence.
