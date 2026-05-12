"""
Regression tests for the Windows sandbox isolation layer (P6-7).

Coverage:
  _load_era_limits      — eras.yaml parsing and all error paths
  WindowsJobObject      — constructor, pre-create error guards, Win32 lifecycle
  SandboxProcess        — attribute/state paths that do not call Win32 APIs
  _verify_sandbox_user  — non-Windows skip, missing script, script failure, success
  _get_sandbox_credentials — password absent and present paths

Tests marked @requires_windows call Win32 APIs and must run on Windows 10/11.
Tests marked @pytest.mark.skip(reason="manual: ...") require a live Windows
environment with the peach_sandbox account present and an emulator binary on disk.
They cannot be run in automated CI.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

WINDOWS = sys.platform == "win32"
requires_windows = pytest.mark.skipif(not WINDOWS, reason="Windows only")


# ---------------------------------------------------------------------------
# _load_era_limits
# ---------------------------------------------------------------------------

class TestLoadEraLimits:
    def test_reads_dos_values_from_real_eras_yaml(self):
        from backend.service.utils.job_objects import _load_era_limits
        memory_mb, cpu_pct = _load_era_limits("dos")
        assert memory_mb == 256
        assert cpu_pct == 50

    def test_reads_win95_values_from_real_eras_yaml(self):
        from backend.service.utils.job_objects import _load_era_limits
        memory_mb, cpu_pct = _load_era_limits("win95")
        assert memory_mb == 512
        assert cpu_pct == 75

    def test_reads_winxp_values_from_real_eras_yaml(self):
        from backend.service.utils.job_objects import _load_era_limits
        memory_mb, cpu_pct = _load_era_limits("winxp")
        assert memory_mb == 1024
        assert cpu_pct == 80

    def test_unknown_era_raises_runtime_error(self):
        from backend.service.utils.job_objects import _load_era_limits
        with pytest.raises(RuntimeError, match="not found in eras.yaml"):
            _load_era_limits("nonexistent_era_xyz")

    def test_missing_file_raises_file_not_found(self, monkeypatch, tmp_path):
        import backend.service.utils.job_objects as jo
        monkeypatch.setattr(jo, "_ERAS_YAML", tmp_path / "missing.yaml")
        with pytest.raises(FileNotFoundError):
            jo._load_era_limits("dos")

    def test_missing_memory_field_raises_runtime_error(self, monkeypatch, tmp_path):
        import yaml
        import backend.service.utils.job_objects as jo
        data = {"dos": {"cpu_limit_percent": 50}}
        p = tmp_path / "eras.yaml"
        p.write_text(yaml.safe_dump(data), encoding="utf-8")
        monkeypatch.setattr(jo, "_ERAS_YAML", p)
        with pytest.raises(RuntimeError, match="memory_limit_mb not defined"):
            jo._load_era_limits("dos")

    def test_missing_cpu_field_raises_runtime_error(self, monkeypatch, tmp_path):
        import yaml
        import backend.service.utils.job_objects as jo
        data = {"dos": {"memory_limit_mb": 256}}
        p = tmp_path / "eras.yaml"
        p.write_text(yaml.safe_dump(data), encoding="utf-8")
        monkeypatch.setattr(jo, "_ERAS_YAML", p)
        with pytest.raises(RuntimeError, match="cpu_limit_percent not defined"):
            jo._load_era_limits("dos")

    def test_returns_integers_not_strings(self):
        from backend.service.utils.job_objects import _load_era_limits
        memory_mb, cpu_pct = _load_era_limits("dos")
        assert isinstance(memory_mb, int)
        assert isinstance(cpu_pct, int)


# ---------------------------------------------------------------------------
# WindowsJobObject — pre-create error guards (no Win32 calls, any OS)
# ---------------------------------------------------------------------------

class TestWindowsJobObjectPreCreate:
    def test_init_stores_attributes(self):
        from backend.service.utils.job_objects import WindowsJobObject
        job = WindowsJobObject("test_job", 512, 75)
        assert job.name == "test_job"
        assert job.memory_limit_mb == 512
        assert job.cpu_limit_percent == 75
        assert job.job_handle is None
        assert job.pid is None

    def test_is_active_before_create_returns_false(self):
        from backend.service.utils.job_objects import WindowsJobObject
        job = WindowsJobObject("test_job", 256, 50)
        assert job.is_active() is False

    def test_set_memory_limit_before_create_raises(self):
        from backend.service.utils.job_objects import WindowsJobObject
        job = WindowsJobObject("test_job", 256, 50)
        with pytest.raises(RuntimeError, match="Job object not created"):
            job.set_memory_limit(256)

    def test_set_cpu_limit_before_create_raises(self):
        from backend.service.utils.job_objects import WindowsJobObject
        job = WindowsJobObject("test_job", 256, 50)
        with pytest.raises(RuntimeError, match="Job object not created"):
            job.set_cpu_limit(50)

    def test_add_process_before_create_raises(self):
        from backend.service.utils.job_objects import WindowsJobObject, SandboxProcess
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
        from backend.service.utils.job_objects import WindowsJobObject
        job = WindowsJobObject("PeachTest_Create", 256, 50)
        job.create()
        try:
            assert job.job_handle is not None
        finally:
            job.terminate_all()

    @requires_windows
    def test_is_active_returns_true_after_create(self):
        from backend.service.utils.job_objects import WindowsJobObject
        job = WindowsJobObject("PeachTest_IsActive", 256, 50)
        job.create()
        try:
            assert job.is_active() is True
        finally:
            job.terminate_all()

    @requires_windows
    def test_memory_limit_reapplied_without_error(self):
        from backend.service.utils.job_objects import WindowsJobObject
        job = WindowsJobObject("PeachTest_MemLimit", 512, 50)
        job.create()
        try:
            job.set_memory_limit(768)
        finally:
            job.terminate_all()

    @requires_windows
    def test_cpu_limit_reapplied_without_error(self):
        from backend.service.utils.job_objects import WindowsJobObject
        job = WindowsJobObject("PeachTest_CpuLimit", 256, 75)
        job.create()
        try:
            job.set_cpu_limit(60)
        finally:
            job.terminate_all()

    @requires_windows
    def test_terminate_all_sets_handle_to_none(self):
        from backend.service.utils.job_objects import WindowsJobObject
        job = WindowsJobObject("PeachTest_Terminate", 256, 50)
        job.create()
        job.terminate_all()
        assert job.job_handle is None

    @requires_windows
    def test_is_active_returns_false_after_terminate(self):
        from backend.service.utils.job_objects import WindowsJobObject
        job = WindowsJobObject("PeachTest_PostTerminate", 256, 50)
        job.create()
        job.terminate_all()
        assert job.is_active() is False

    @requires_windows
    def test_terminate_all_is_idempotent(self):
        from backend.service.utils.job_objects import WindowsJobObject
        job = WindowsJobObject("PeachTest_Idempotent", 256, 50)
        job.create()
        job.terminate_all()
        job.terminate_all()  # no handle — must not raise

    @requires_windows
    def test_create_applies_era_limits_from_eras_yaml(self):
        """End-to-end: limits from eras.yaml are applied to a real Job Object."""
        from backend.service.utils.job_objects import WindowsJobObject, _load_era_limits
        memory_mb, cpu_pct = _load_era_limits("dos")
        job = WindowsJobObject("PeachTest_EraLimits", memory_mb, cpu_pct)
        job.create()
        try:
            assert job.is_active() is True
            assert job.memory_limit_mb == memory_mb
            assert job.cpu_limit_percent == cpu_pct
        finally:
            job.terminate_all()


# ---------------------------------------------------------------------------
# SandboxProcess — pure Python paths, no Win32 calls (any OS)
# ---------------------------------------------------------------------------

class TestSandboxProcess:
    def test_init_stores_attributes(self):
        from backend.service.utils.job_objects import SandboxProcess
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
        from backend.service.utils.job_objects import SandboxProcess
        proc = SandboxProcess(pid=1, process_handle=None, thread_handle=None, args=["x.exe"])
        proc.returncode = 0
        assert proc.poll() == 0

    def test_poll_with_closed_handle_returns_none_when_returncode_unset(self):
        from backend.service.utils.job_objects import SandboxProcess
        proc = SandboxProcess(pid=1, process_handle=None, thread_handle=None, args=["x.exe"])
        assert proc.poll() is None

    def test_poll_is_idempotent_after_handle_closed(self):
        from backend.service.utils.job_objects import SandboxProcess
        proc = SandboxProcess(pid=1, process_handle=None, thread_handle=None, args=["x.exe"])
        proc.returncode = 1
        assert proc.poll() == 1
        assert proc.poll() == 1

    def test_resume_raises_when_thread_handle_is_none(self):
        from backend.service.utils.job_objects import SandboxProcess
        proc = SandboxProcess(pid=1234, process_handle=None, thread_handle=None, args=["x.exe"])
        with pytest.raises(RuntimeError, match="Thread handle is not open"):
            proc.resume()

    def test_returncode_is_none_on_fresh_instance(self):
        from backend.service.utils.job_objects import SandboxProcess
        proc = SandboxProcess(pid=42, process_handle=None, thread_handle=None, args=[])
        assert proc.returncode is None


# ---------------------------------------------------------------------------
# _verify_sandbox_user — fully mock-based, runs on any OS
# ---------------------------------------------------------------------------

class TestVerifySandboxUser:
    def test_skips_on_non_windows(self):
        import backend.core.lifespan as lifespan
        with patch("backend.core.lifespan.platform.system", return_value="Linux"):
            lifespan._verify_sandbox_user()  # must not raise

    def test_raises_if_script_missing(self, tmp_path):
        import backend.core.lifespan as lifespan
        missing = tmp_path / "no_such_script.ps1"
        with patch("backend.core.lifespan.platform.system", return_value="Windows"), \
             patch("backend.core.lifespan._SANDBOX_SCRIPT", missing):
            with pytest.raises(RuntimeError, match="Sandbox setup script not found"):
                lifespan._verify_sandbox_user()

    def test_raises_on_script_nonzero_exit(self, tmp_path):
        import backend.core.lifespan as lifespan
        script = tmp_path / "create_sandbox_user.ps1"
        script.write_text("# stub", encoding="utf-8")
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "[peach_sandbox] error line"
        mock_result.stderr = ""
        with patch("backend.core.lifespan.platform.system", return_value="Windows"), \
             patch("backend.core.lifespan._SANDBOX_SCRIPT", script), \
             patch("backend.service.utils.settings.get_or_generate_sandbox_password", return_value="pw"), \
             patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="Sandbox user setup failed"):
                lifespan._verify_sandbox_user()

    def test_succeeds_on_script_zero_exit(self, tmp_path):
        import backend.core.lifespan as lifespan
        script = tmp_path / "create_sandbox_user.ps1"
        script.write_text("# stub", encoding="utf-8")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "[peach_sandbox] Ready."
        mock_result.stderr = ""
        with patch("backend.core.lifespan.platform.system", return_value="Windows"), \
             patch("backend.core.lifespan._SANDBOX_SCRIPT", script), \
             patch("backend.service.utils.settings.get_or_generate_sandbox_password", return_value="pw"), \
             patch("subprocess.run", return_value=mock_result):
            lifespan._verify_sandbox_user()  # must not raise

    def test_password_passed_via_env_not_args(self, tmp_path):
        """PEACH_SANDBOX_PASSWORD must be in env, never on the command line."""
        import backend.core.lifespan as lifespan
        script = tmp_path / "create_sandbox_user.ps1"
        script.write_text("# stub", encoding="utf-8")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        captured = {}
        def capture_run(*args, **kwargs):
            captured["cmd"] = args[0] if args else kwargs.get("args", [])
            captured["env"] = kwargs.get("env", {})
            return mock_result
        with patch("backend.core.lifespan.platform.system", return_value="Windows"), \
             patch("backend.core.lifespan._SANDBOX_SCRIPT", script), \
             patch("backend.service.utils.settings.get_or_generate_sandbox_password", return_value="secret_pw"), \
             patch("subprocess.run", side_effect=capture_run):
            lifespan._verify_sandbox_user()
        assert "secret_pw" not in " ".join(str(a) for a in captured.get("cmd", []))
        assert captured.get("env", {}).get("PEACH_SANDBOX_PASSWORD") == "secret_pw"


# ---------------------------------------------------------------------------
# _get_sandbox_credentials — mock-based
# ---------------------------------------------------------------------------

class TestGetSandboxCredentials:
    def test_returns_peach_sandbox_username(self):
        from backend.service.utils.job_objects import _get_sandbox_credentials
        with patch("backend.service.utils.settings.get_or_generate_sandbox_password", return_value="secure123"):
            username, _ = _get_sandbox_credentials()
        assert username == "peach_sandbox"

    def test_returns_configured_password(self):
        from backend.service.utils.job_objects import _get_sandbox_credentials
        with patch("backend.service.utils.settings.get_or_generate_sandbox_password", return_value="secure123"):
            _, password = _get_sandbox_credentials()
        assert password == "secure123"

    def test_raises_when_password_is_empty_string(self):
        from backend.service.utils.job_objects import _get_sandbox_credentials
        with patch("backend.service.utils.settings.get_or_generate_sandbox_password", return_value=""):
            with pytest.raises(RuntimeError, match="peach_sandbox account password is not configured"):
                _get_sandbox_credentials()

    def test_raises_when_password_is_none(self):
        from backend.service.utils.job_objects import _get_sandbox_credentials
        with patch("backend.service.utils.settings.get_or_generate_sandbox_password", return_value=None):
            with pytest.raises(RuntimeError, match="peach_sandbox account password is not configured"):
                _get_sandbox_credentials()


# ---------------------------------------------------------------------------
# Manual verification tests — cannot run in automated CI
# ---------------------------------------------------------------------------

@pytest.mark.skip(
    reason=(
        "manual: requires admin privileges and a live Windows 10/11 environment. "
        "Steps: (1) Start the backend so lifespan._verify_sandbox_user() runs. "
        "(2) Open an admin PowerShell and run: "
        "Get-LocalUser -Name peach_sandbox; "
        "Get-LocalGroupMember -Group Administrators | Where-Object { $_.Name -like '*peach_sandbox*' }. "
        "Expected: account exists and is Enabled; account is NOT in Administrators group."
    )
)
def test_manual_sandbox_user_exists_and_not_admin():
    pass


@pytest.mark.skip(
    reason=(
        "manual: requires the peach_sandbox account to exist, a real emulator binary "
        "at DOSBOX_PATH, and Windows 10/11. "
        "Steps: (1) Ensure the backend has started once. "
        "(2) Call launch_under_job_object(dosbox_path, [], [], 'dos', 'PeachManualTest'). "
        "(3) Verify process.pid > 0 and job.is_active() is True. "
        "(4) Call job.terminate_all() and verify the process is gone. "
        "Expected: no RuntimeError; pid > 0; job active after launch; inactive after terminate."
    )
)
def test_manual_launch_under_job_object_real_process():
    pass


@pytest.mark.skip(
    reason=(
        "manual: requires Windows 10/11 with peach_sandbox account absent. "
        "Steps: (1) Delete the peach_sandbox account if it exists: Remove-LocalUser peach_sandbox. "
        "(2) Start the backend — _verify_sandbox_user() must create the account. "
        "(3) Verify Get-LocalUser -Name peach_sandbox shows the account as Enabled. "
        "Expected: account created automatically on first backend start."
    )
)
def test_manual_sandbox_user_created_on_first_start():
    pass
