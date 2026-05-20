"""
Windows Job Object wrapper for Peach 1UP.

Provides process isolation and resource limits for emulator processes running
natively on the Windows host.  Each emulator launch gets its own named Job
Object so multiple profiles can run without interfering with each other.

All emulator processes are launched under the current user account via
``CreateProcessW``.  If the Job Object cannot be created, the launch is
aborted.  There is no unsandboxed fallback.

Resource limits (memory cap, CPU hard cap, kill-on-close) are sourced
exclusively from eras.yaml.  There is no per-profile override path.

Network isolation is handled at the emulator level — each backend disables
its network adapter when enable_networking is false on the active profile.
"""

import ctypes
import ctypes.wintypes
import os

from backend.service.utils.win32_types import (
    _JOB_OBJECT_LIMIT_PROCESS_MEMORY,
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    _JOB_OBJECT_CPU_RATE_CONTROL_ENABLE,
    _JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP,
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
    JOBOBJECT_CPU_RATE_CONTROL_INFORMATION,
    JOBOBJECT_BASIC_ACCOUNTING_INFORMATION,
    THREADENTRY32,
)
from backend.core.logger import get_logger
from backend.service.utils.sandbox_process import SandboxProcess

logger = get_logger(__name__)


def _process_in_job(pid: int) -> bool:
    """Return True if the process with *pid* is inside any Windows Job Object.

    Opens the process with ``PROCESS_QUERY_INFORMATION`` (0x0400), calls
    ``IsProcessInJob``, then closes the handle.  Returns ``False`` on any
    error rather than raising so callers can treat it as a safe boolean check.
    """

    # SAFETY: handle is closed by wait(); do not call add_process after kill/wait
    handle = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)
    if not handle:
        return False
    try:
        in_job = ctypes.wintypes.BOOL(False)
        ctypes.windll.kernel32.IsProcessInJob(handle, None, ctypes.byref(in_job))
        return bool(in_job)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


class WindowsJobObject:
    """Windows Job Object wrapper for emulator process isolation.

    Wraps a named Win32 Job Object with memory cap, CPU hard cap, and
    kill-on-close semantics.  The expected call sequence is:

        job = WindowsJobObject(name, memory_limit_mb, cpu_limit_percent)
        job.create()
        job.add_process(sandbox_process)
        # ... emulator runs ...
        job.terminate_all()

    ``launch_under_job_object`` in launcher.py handles this sequence and is
    the preferred entry point for callers outside this file.

    Attributes:
        name: Unique name for the Win32 Job Object.
        memory_limit_mb: Per-process memory cap in MB, applied at creation.
        cpu_limit_percent: CPU hard cap as a percentage of all logical
            processors (1–100), applied at creation.
        job_handle: Raw Win32 handle; ``None`` until ``create()`` is called.
        process_name: Basename of the emulator executable (no extension).
        pid: PID of the emulator process added via ``add_process``.
    """

    def __init__(self, name: str, memory_limit_mb: int, cpu_limit_percent: int):
        """
        Args:
            name: Unique name for the job object.
            memory_limit_mb: Memory limit in MB (sourced from eras.yaml).
            cpu_limit_percent: CPU hard cap as a percentage of all logical
                processors (sourced from eras.yaml).  Must be 1–100.
        """
        self.name = name
        self.memory_limit_mb = memory_limit_mb
        self.cpu_limit_percent = cpu_limit_percent
        self.job_handle = None
        self.process_name = None
        self.pid = None

    def create(self) -> None:
        """Create the Win32 Job Object and apply the CPU rate cap.

        Memory limit and kill-on-close are applied by the launcher after
        creation, conditionally on the emulator slug.

        Raises:
            RuntimeError: If ``CreateJobObjectW`` fails or the CPU limit
                cannot be set.
        """
        self.job_handle = ctypes.windll.kernel32.CreateJobObjectW(
            None,                        # default security attributes
            ctypes.c_wchar_p(self.name)  # job object name (Unicode)
        )

        if not self.job_handle:
            error_code = ctypes.windll.kernel32.GetLastError()
            raise RuntimeError(
                f"Failed to create Job Object '{self.name}'. Error code: {error_code}"
            )

        self.set_cpu_limit(self.cpu_limit_percent)

    def set_memory_limit(self, limit_mb: int) -> None:
        """Set the per-process memory cap and enable kill-on-close.

        Applies ``JOB_OBJECT_LIMIT_PROCESS_MEMORY`` and
        ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` together via a single
        ``SetInformationJobObject`` call.  Kill-on-close guarantees the
        entire emulator process tree is terminated if the backend exits.

        Args:
            limit_mb: Memory limit in megabytes.

        Raises:
            RuntimeError: If the job handle is not open or
                ``SetInformationJobObject`` fails.
        """
        if not self.job_handle:
            raise RuntimeError("Job object not created. Call create() first.")

        limit_info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limit_info.BasicLimitInformation.LimitFlags = (
            _JOB_OBJECT_LIMIT_PROCESS_MEMORY | _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        limit_info.ProcessMemoryLimit = limit_mb * 1024 * 1024  # MB → bytes

        result = ctypes.windll.kernel32.SetInformationJobObject(
            self.job_handle,
            ctypes.wintypes.DWORD(9),   # JobObjectExtendedLimitInformation
            ctypes.byref(limit_info),
            ctypes.sizeof(limit_info)
        )

        if not result:
            error_code = ctypes.windll.kernel32.GetLastError()
            raise RuntimeError(
                f"Failed to set memory limit to {limit_mb}MB. Error code: {error_code}"
            )

    def set_kill_on_close(self) -> None:
        """Set kill-on-close without a process memory cap.

        Used when ``JOB_OBJECT_LIMIT_PROCESS_MEMORY`` must be skipped (e.g.
        Qt-based emulators that fast-fail on that flag) while still ensuring
        the process tree is torn down when the backend exits.

        Raises:
            RuntimeError: If the job handle is not open or
                ``SetInformationJobObject`` fails.
        """
        if not self.job_handle:
            raise RuntimeError("Job object not created. Call create() first.")

        limit_info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limit_info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        result = ctypes.windll.kernel32.SetInformationJobObject(
            self.job_handle,
            ctypes.wintypes.DWORD(9),   # JobObjectExtendedLimitInformation
            ctypes.byref(limit_info),
            ctypes.sizeof(limit_info)
        )

        if not result:
            error_code = ctypes.windll.kernel32.GetLastError()
            raise RuntimeError(
                f"Failed to set kill-on-close for '{self.name}'. Error code: {error_code}"
            )

    def set_cpu_limit(self, cpu_limit_percent: int) -> None:
        """Apply a hard CPU rate cap via ``JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP``.

        ``CpuRate`` is expressed as cycles per 10,000 across all logical
        processors, so a 50% cap on an 8-thread machine allows the job to
        consume the equivalent of 4 threads' worth of CPU time per scheduling
        interval.  Threads are throttled (not killed) when the budget is
        exhausted within an interval.

        Requires Windows 8.1 or later (KB2898600 for Windows 8.0).

        Args:
            cpu_limit_percent: CPU budget as a percentage of all logical
                processors.  Clamped to [1, 100].

        Raises:
            RuntimeError: If the job handle is not open or
                ``SetInformationJobObject`` fails.
        """
        if not self.job_handle:
            raise RuntimeError("Job object not created. Call create() first.")

        # CpuRate: units of 1/100 of a percent (10,000 == 100% of all CPUs).
        cpu_rate = max(1, min(10000, cpu_limit_percent * 100))

        cpu_rate_info = JOBOBJECT_CPU_RATE_CONTROL_INFORMATION()
        cpu_rate_info.ControlFlags = (
            _JOB_OBJECT_CPU_RATE_CONTROL_ENABLE | _JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP
        )
        cpu_rate_info.CpuRate = cpu_rate

        result = ctypes.windll.kernel32.SetInformationJobObject(
            self.job_handle,
            ctypes.wintypes.DWORD(15),  # JobObjectCpuRateControlInformation
            ctypes.byref(cpu_rate_info),
            ctypes.sizeof(cpu_rate_info)
        )

        if not result:
            error_code = ctypes.windll.kernel32.GetLastError()
            raise RuntimeError(
                f"Failed to set CPU limit to {cpu_limit_percent}%. Error code: {error_code}"
            )

    def add_process(self, process: "SandboxProcess") -> None:
        """Assign a process to the job object.

        If ``process.handle`` is set (populated by ``_launch_process``),
        it is used directly for ``AssignProcessToJobObject`` — no ``OpenProcess``
        or ``CloseHandle`` call is made; handle lifecycle is managed by the
        caller via ``launch_under_job_object``.  If ``process.handle`` is
        ``None``, falls back to opening a minimal-permission handle.

        Args:
            process: A ``SandboxProcess`` instance that has already been launched.

        Raises:
            RuntimeError: If the job handle is not open, the process is
                invalid, ``OpenProcess`` fails, or ``AssignProcessToJobObject``
                fails.
        """
        if not self.job_handle:
            raise RuntimeError("Job object not created. Call create() first.")

        if not process or not process.pid:
            raise RuntimeError("Invalid process or process not started.")

        self.pid = process.pid
        if hasattr(process, 'args') and process.args:
            executable_path = process.args[0] if isinstance(process.args, list) else str(process.args)
            self.process_name = os.path.basename(executable_path).replace('.exe', '')
        else:
            self.process_name = f"process_{self.pid}"

        using_stored_handle = process.handle is not None

        if using_stored_handle:
            proc_handle = process.handle
        else:
            # Fallback: process handle was not retained by the caller.
            proc_handle = ctypes.windll.kernel32.OpenProcess(
                0x0201,  # PROCESS_SET_QUOTA | PROCESS_TERMINATE — minimum for AssignProcessToJobObject
                False,
                process.pid
            )
            if not proc_handle:
                error_code = ctypes.windll.kernel32.GetLastError()
                raise RuntimeError(
                    f"Failed to open process {self.pid}. Error code: {error_code}"
                )

        try:
            # Informational check — captured to produce a richer error message
            # if AssignProcessToJobObject still fails after the breakaway re-launch
            # performed in launch_under_job_object().
            _in_job = ctypes.wintypes.BOOL(False)
            ctypes.windll.kernel32.IsProcessInJob(
                proc_handle, None, ctypes.byref(_in_job)
            )
            already_in_job = bool(_in_job)

            result = ctypes.windll.kernel32.AssignProcessToJobObject(
                self.job_handle,
                proc_handle
            )

            if not result:
                error_code = ctypes.windll.kernel32.GetLastError()
                if error_code == 5:
                    raise RuntimeError(
                        f"Failed to add process {self.pid} to job object."
                        f" Error code: 5. retry_with_breakaway"
                    )
                extra = (
                    " The process is still inside an OS-managed job object — "
                    "nested assignment failed. This should not occur on Windows 8+; "
                    "check for third-party job managers or restricted environments."
                    if already_in_job else ""
                )
                raise RuntimeError(
                    f"Failed to add process {self.pid} to job object."
                    f" Error code: {error_code}.{extra}"
                )
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Unexpected error assigning process {self.pid} to job object: {exc}"
            ) from exc
        finally:
            # Only close if we opened the handle ourselves; stored handle lifecycle
            # is managed by launch_under_job_object after resume() completes.
            if not using_stored_handle:
                ctypes.windll.kernel32.CloseHandle(proc_handle)

    # NAMING: terminate_all also closes the job handle — it is a full resource
    # teardown, not just process termination.  Consider renaming to shutdown()
    # or teardown() at the next refactor pass.
    def terminate_all(self) -> None:
        """Terminate all processes in the job object and release all associated resources.

        Performs two cleanup steps in order, collecting errors from each so
        that a failure in one step does not skip the rest:

          1. Call ``TerminateJobObject`` to kill all processes in the job.
          2. Close the job object handle.

        ``self.job_handle`` is set to ``None`` regardless of success or failure
        so that ``is_active()`` returns ``False`` after this call.

        Raises:
            RuntimeError: If any step fails.  The error message lists all
                failures and notes that manual cleanup may be required.
        """
        termination_errors = []

        if self.job_handle:
            try:
                result = ctypes.windll.kernel32.TerminateJobObject(
                    self.job_handle,
                    1  # exit code for terminated processes
                )
                if not result:
                    error_code = ctypes.windll.kernel32.GetLastError()
                    termination_errors.append(
                        f"TerminateJobObject failed with error code: {error_code}"
                    )
            except Exception as e:
                termination_errors.append(f"Exception during job termination: {str(e)}")

            try:
                ctypes.windll.kernel32.CloseHandle(self.job_handle)
            except Exception as e:
                termination_errors.append(f"Failed to close job handle: {str(e)}")

        # Always null the handle so callers relying on is_active() get False after teardown
        self.job_handle = None

        if termination_errors:
            raise RuntimeError(
                f"Job object termination encountered errors for {self.name}. "
                f"Some resources may require manual cleanup. "
                f"Errors: {'; '.join(termination_errors)}"
            )

    def close(self) -> None:
        """Close the job object handle without terminating any processes.

        Use this when the process has already exited and the handle only needs
        to be released.  Does not call ``TerminateJobObject``.  Safe to call
        multiple times — no-op if the handle is already closed.
        """
        if self.job_handle:
            ctypes.windll.kernel32.CloseHandle(self.job_handle)
            self.job_handle = None

    # NAMING: is_active checks only that the job handle is open and queryable —
    # it does NOT check whether any processes are currently running in the job.
    # A handle can be valid with zero live processes.  The name implies otherwise.
    def is_active(self) -> bool:
        """Check whether the job object handle is open and queryable.

        Uses a lightweight ``QueryInformationJobObject`` call to verify handle
        validity without modifying any state.  Returns ``False`` before
        ``create()`` is called, after ``terminate_all()``, or if the handle
        has been closed externally.

        Returns:
            ``True`` if the handle is valid and queryable; ``False`` otherwise.

        Notes:
            Never raises — returns ``False`` on any error so callers can use
            this as a simple boolean guard.
        """
        if not self.job_handle:
            return False

        try:
            accounting_info = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION()
            result = ctypes.windll.kernel32.QueryInformationJobObject(
                self.job_handle,
                ctypes.wintypes.DWORD(1),   # JobObjectBasicAccountingInformation
                ctypes.byref(accounting_info),
                ctypes.sizeof(accounting_info),
                None  # return length not needed
            )
            return bool(result)
        except Exception:
            return False

    def _resume_suspended_process(self, process) -> None:
        """Resume the main thread of a process launched in a suspended state.

        Finds the first thread belonging to the process in a system-wide
        thread snapshot and calls ``ResumeThread``.  Used as a fallback for
        process types that do not expose a thread handle directly.

        Args:
            process: An object with a ``pid`` attribute.

        Raises:
            RuntimeError: If the thread snapshot fails, the main thread cannot
                be found, ``OpenThread`` fails, or ``ResumeThread`` fails.
        """
        TH32CS_SNAPTHREAD = 0x00000004
        THREAD_SUSPEND_RESUME = 0x0002

        snapshot = ctypes.windll.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
        if snapshot == -1:
            raise RuntimeError("Failed to create thread snapshot")

        try:
            te32 = THREADENTRY32()
            te32.dwSize = ctypes.sizeof(THREADENTRY32)

            main_thread_id = None
            if ctypes.windll.kernel32.Thread32First(snapshot, ctypes.byref(te32)):
                while True:
                    if te32.th32OwnerProcessID == process.pid:
                        main_thread_id = te32.th32ThreadID
                        break  # first thread found is the main thread
                    if not ctypes.windll.kernel32.Thread32Next(snapshot, ctypes.byref(te32)):
                        break

            if not main_thread_id:
                raise RuntimeError(
                    f"Could not find main thread for process {process.pid}"
                )

            thread_handle = ctypes.windll.kernel32.OpenThread(
                THREAD_SUSPEND_RESUME,
                False,
                main_thread_id
            )
            if not thread_handle:
                raise RuntimeError(f"Failed to open main thread {main_thread_id}")

            try:
                result = ctypes.windll.kernel32.ResumeThread(thread_handle)
                if result == -1:
                    raise RuntimeError("Failed to resume main thread")
            finally:
                ctypes.windll.kernel32.CloseHandle(thread_handle)

        finally:
            ctypes.windll.kernel32.CloseHandle(snapshot)
