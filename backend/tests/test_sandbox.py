"""
Regression tests for the Windows Job Object isolation layer.

Coverage:
  _load_era_limits      — eras.yaml parsing and all error paths
  WindowsJobObject      — constructor, pre-create error guards, Win32 lifecycle
  SandboxProcess        — attribute/state paths that do not call Win32 APIs

Tests marked @requires_windows call Win32 APIs and must run on Windows 10/11.
"""

import sys

import pytest

WINDOWS = sys.platform == "win32"
requires_windows = pytest.mark.skipif(not WINDOWS, reason="Windows only")


# ---------------------------------------------------------------------------
# _load_era_limits
# ---------------------------------------------------------------------------

class TestLoadEraLimits:
    def test_reads_dos_values_from_real_eras_yaml(self):
        from backend.service.utils.platform.windows.process.launcher import _load_era_limits
        memory_mb, cpu_pct = _load_era_limits("dos")
        assert memory_mb == 512
        assert cpu_pct == 50

    def test_reads_win95_values_from_real_eras_yaml(self):
        from backend.service.utils.platform.windows.process.launcher import _load_era_limits
        memory_mb, cpu_pct = _load_era_limits("win95")
        assert memory_mb == 2048
        assert cpu_pct == 75

    def test_reads_winxp_values_from_real_eras_yaml(self):
        from backend.service.utils.platform.windows.process.launcher import _load_era_limits
        memory_mb, cpu_pct = _load_era_limits("winxp")
        assert memory_mb == 3072
        assert cpu_pct == 80

    def test_unknown_era_raises_runtime_error(self):
        from backend.service.utils.platform.windows.process.launcher import _load_era_limits
        with pytest.raises(RuntimeError, match="not found in eras.yaml"):
            _load_era_limits("nonexistent_era_xyz")

    def test_missing_file_raises_file_not_found(self, monkeypatch, tmp_path):
        import backend.service.utils.platform.windows.process.launcher as jo
        monkeypatch.setattr(jo, "_ERAS_YAML", tmp_path / "missing.yaml")

        with pytest.raises(FileNotFoundError):
            jo._load_era_limits("dos")

    def test_missing_memory_field_raises_runtime_error(self, monkeypatch, tmp_path):
        import yaml
        import backend.service.utils.platform.windows.process.launcher as jo
        data = {"dos": {"cpu_limit_percent": 50}}
        p = tmp_path / "eras.yaml"
        p.write_text(yaml.safe_dump(data), encoding="utf-8")
        monkeypatch.setattr(jo, "_ERAS_YAML", p)
        with pytest.raises(RuntimeError, match="memory_limit_mb not defined"):
            jo._load_era_limits("dos")

    def test_missing_cpu_field_raises_runtime_error(self, monkeypatch, tmp_path):
        import yaml
        import backend.service.utils.platform.windows.process.launcher as jo
        data = {"dos": {"memory_limit_mb": 256}}
        p = tmp_path / "eras.yaml"
        p.write_text(yaml.safe_dump(data), encoding="utf-8")
        monkeypatch.setattr(jo, "_ERAS_YAML", p)
        with pytest.raises(RuntimeError, match="cpu_limit_percent not defined"):
            jo._load_era_limits("dos")

    def test_returns_integers_not_strings(self):
        from backend.service.utils.platform.windows.process.launcher import _load_era_limits
        memory_mb, cpu_pct = _load_era_limits("dos")
        assert isinstance(memory_mb, int)
        assert isinstance(cpu_pct, int)


# ---------------------------------------------------------------------------
# WindowsJobObject — pre-create error guards (no Win32 calls, any OS)
# ---------------------------------------------------------------------------

class TestWindowsJobObjectPreCreate:
    def test_init_stores_attributes(self):
        from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject
        job = WindowsJobObject("test_job", 512, 75)
        assert job.name == "test_job"
        assert job.memory_limit_mb == 512
        assert job.cpu_limit_percent == 75
        assert job.job_handle is None
        assert job.pid is None

    def test_handle_is_open_before_create_returns_false(self):
        from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject
        job = WindowsJobObject("test_job", 256, 50)
        assert job.handle_is_open() is False

    def test_set_memory_limit_before_create_raises(self):
        from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject
        job = WindowsJobObject("test_job", 256, 50)
        with pytest.raises(RuntimeError, match="Job object not created"):
            job.set_memory_limit(256)

    def test_set_cpu_limit_before_create_raises(self):
        from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject
        job = WindowsJobObject("test_job", 256, 50)
        with pytest.raises(RuntimeError, match="Job object not created"):
            job.set_cpu_limit(50)

    def test_add_process_before_create_raises(self):
        from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject
        from backend.service.utils.platform.windows.sandbox_process import SandboxProcess
        job = WindowsJobObject("test_job", 256, 50)
        proc = SandboxProcess(pid=1234, process_handle=None, thread_handle=None, args=["x.exe"])
        with pytest.raises(RuntimeError, match="Job object not created"):
            job.add_process(proc)


# ---------------------------------------------------------------------------
# WindowsJobObject — Win32 lifecycle (Windows-only, no admin required)
# ---------------------------------------------------------------------------

class TestWindowsJobObjectLifecycle:
    @requires_windows
    def test_create_succeeds_and_handle_is_set(self):
        from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject
        job = WindowsJobObject("PeachTest_Create", 256, 50)
        job.create()
        try:
            assert job.job_handle is not None
        finally:
            job.teardown()

    @requires_windows
    def test_handle_is_open_returns_true_after_create(self):
        from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject
        job = WindowsJobObject("PeachTest_IsActive", 256, 50)
        job.create()
        try:
            assert job.handle_is_open() is True
        finally:
            job.teardown()

    @requires_windows
    def test_memory_limit_reapplied_without_error(self):
        from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject
        job = WindowsJobObject("PeachTest_MemLimit", 512, 50)
        job.create()
        try:
            job.set_memory_limit(768)
        finally:
            job.teardown()

    @requires_windows
    def test_cpu_limit_reapplied_without_error(self):
        from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject
        job = WindowsJobObject("PeachTest_CpuLimit", 256, 75)
        job.create()
        try:
            job.set_cpu_limit(60)
        finally:
            job.teardown()

    @requires_windows
    def test_teardown_sets_handle_to_none(self):
        from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject
        job = WindowsJobObject("PeachTest_Terminate", 256, 50)
        job.create()
        job.teardown()
        assert job.job_handle is None

    @requires_windows
    def test_handle_is_open_returns_false_after_terminate(self):
        from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject
        job = WindowsJobObject("PeachTest_PostTerminate", 256, 50)
        job.create()
        job.teardown()
        assert job.handle_is_open() is False

    @requires_windows
    def test_teardown_is_idempotent(self):
        from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject
        job = WindowsJobObject("PeachTest_Idempotent", 256, 50)
        job.create()
        job.teardown()
        job.teardown()  # no handle — must not raise

    @requires_windows
    def test_create_applies_era_limits_from_eras_yaml(self):
        """End-to-end: limits from eras.yaml are applied to a real Job Object."""
        from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject
        from backend.service.utils.platform.windows.process.launcher import _load_era_limits
        memory_mb, cpu_pct = _load_era_limits("dos")
        job = WindowsJobObject("PeachTest_EraLimits", memory_mb, cpu_pct)
        job.create()
        try:
            assert job.handle_is_open() is True
            assert job.memory_limit_mb == memory_mb
            assert job.cpu_limit_percent == cpu_pct
        finally:
            job.teardown()


# ---------------------------------------------------------------------------
# SandboxProcess — pure Python paths, no Win32 calls (any OS)
# ---------------------------------------------------------------------------

class TestSandboxProcess:
    def test_init_stores_attributes(self):
        from backend.service.utils.platform.windows.sandbox_process import SandboxProcess
        proc = SandboxProcess(
            pid=9999,
            process_handle=None,
            thread_handle=None,
            args=["dosbox.exe", "-conf", "game.conf"],
        )
        assert proc.pid == 9999
        assert proc.args == ["dosbox.exe", "-conf", "game.conf"]
        assert proc.returncode is None
        assert proc._process_handle is None
        assert proc._thread_handle is None

    def test_poll_with_closed_handle_returns_stored_returncode(self):
        from backend.service.utils.platform.windows.sandbox_process import SandboxProcess
        proc = SandboxProcess(pid=1, process_handle=None, thread_handle=None, args=["x.exe"])
        proc.returncode = 0
        assert proc.poll() == 0

    def test_poll_with_closed_handle_returns_none_when_returncode_unset(self):
        from backend.service.utils.platform.windows.sandbox_process import SandboxProcess
        proc = SandboxProcess(pid=1, process_handle=None, thread_handle=None, args=["x.exe"])
        assert proc.poll() is None

    def test_poll_is_idempotent_after_handle_closed(self):
        from backend.service.utils.platform.windows.sandbox_process import SandboxProcess
        proc = SandboxProcess(pid=1, process_handle=None, thread_handle=None, args=["x.exe"])
        proc.returncode = 1
        assert proc.poll() == 1
        assert proc.poll() == 1

    def test_resume_raises_when_thread_handle_is_none(self):
        from backend.service.utils.platform.windows.sandbox_process import SandboxProcess
        proc = SandboxProcess(pid=1234, process_handle=None, thread_handle=None, args=["x.exe"])
        with pytest.raises(RuntimeError, match="Thread handle is not open"):
            proc.resume()

    def test_returncode_is_none_on_fresh_instance(self):
        from backend.service.utils.platform.windows.sandbox_process import SandboxProcess
        proc = SandboxProcess(pid=42, process_handle=None, thread_handle=None, args=[])
        assert proc.returncode is None


# ---------------------------------------------------------------------------
# Manual verification test — cannot run in automated CI
# ---------------------------------------------------------------------------

@pytest.mark.skip(
    reason=(
        "manual: requires a real emulator binary at DOSBOX_PATH and Windows 10/11. "
        "Steps: (1) Call launch_under_job_object(dosbox_path, [], [], 'dos', 'PeachManualTest'). "
        "(2) Verify process.pid > 0 and job.handle_is_open() is True. "
        "(3) Call job.teardown() and verify the process is gone. "
        "Expected: no RuntimeError; pid > 0; job active after launch; inactive after terminate."
    )
)
def test_manual_launch_under_job_object_real_process():
    pass
