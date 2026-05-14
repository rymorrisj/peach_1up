"""
Windows Job Objects wrapper for Peach 1UP.

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

import logging
import subprocess
import ctypes
import ctypes.wintypes
from typing import List, Tuple
from pathlib import Path
import os
import yaml

logger = logging.getLogger(__name__)

# Win32 CREATE_SUSPENDED flag — avoids a hard dependency on pywin32 at module import time.
_CREATE_SUSPENDED = 0x00000004

# Anchor eras.yaml to the project root regardless of CWD.
# job_objects.py lives at backend/service/utils/ — 4 parents up is the project root.
_ERAS_YAML = Path(__file__).resolve().parent.parent.parent.parent / "config" / "eras.yaml"

# CREATE_BREAKAWAY_FROM_JOB: child process escapes the parent's Job Object so
# it can be cleanly assigned to our own.  Used when the launcher is already
# inside a Windows Job Object (common on Windows 11).
_CREATE_BREAKAWAY_FROM_JOB = 0x01000000

# LimitFlags values used in JOBOBJECT_BASIC_LIMIT_INFORMATION.LimitFlags
_JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

# ControlFlags values used in JOBOBJECT_CPU_RATE_CONTROL_INFORMATION.ControlFlags
_JOB_OBJECT_CPU_RATE_CONTROL_ENABLE   = 0x1
_JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP = 0x4  # requires Windows 8.1+

# GetExitCodeProcess sentinel — process has not yet exited.
_STILL_ACTIVE = 259


# ---------------------------------------------------------------------------
# Windows API structures
# ---------------------------------------------------------------------------

class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.wintypes.LARGE_INTEGER),
        ("PerJobUserTimeLimit", ctypes.wintypes.LARGE_INTEGER),
        ("LimitFlags", ctypes.wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.wintypes.DWORD),
        ("Affinity", ctypes.POINTER(ctypes.wintypes.ULONG)),
        ("PriorityClass", ctypes.wintypes.DWORD),
        ("SchedulingClass", ctypes.wintypes.DWORD),
    ]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.wintypes.ULARGE_INTEGER),
        ("WriteOperationCount", ctypes.wintypes.ULARGE_INTEGER),
        ("OtherOperationCount", ctypes.wintypes.ULARGE_INTEGER),
        ("ReadTransferCount", ctypes.wintypes.ULARGE_INTEGER),
        ("WriteTransferCount", ctypes.wintypes.ULARGE_INTEGER),
        ("OtherTransferCount", ctypes.wintypes.ULARGE_INTEGER),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class JOBOBJECT_CPU_RATE_CONTROL_INFORMATION(ctypes.Structure):
    """Maps to the Win32 structure of the same name (hard-cap variant).

    ``CpuRate`` occupies the first DWORD of the union field.  When
    ``_JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP`` is set in ``ControlFlags``,
    this field holds the per-scheduling-interval CPU budget expressed as
    cycles per 10,000 across all logical processors (10,000 == 100%).
    """
    _fields_ = [
        ("ControlFlags", ctypes.wintypes.DWORD),
        ("CpuRate",      ctypes.wintypes.DWORD),
    ]


class JOBOBJECT_BASIC_ACCOUNTING_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.wintypes.LARGE_INTEGER),
        ("TotalKernelTime", ctypes.wintypes.LARGE_INTEGER),
        ("ThisPeriodTotalUserTime", ctypes.wintypes.LARGE_INTEGER),
        ("ThisPeriodTotalKernelTime", ctypes.wintypes.LARGE_INTEGER),
        ("TotalPageFaultCount", ctypes.wintypes.DWORD),
        ("TotalProcesses", ctypes.wintypes.DWORD),
        ("ActiveProcesses", ctypes.wintypes.DWORD),
        ("TotalTerminatedProcesses", ctypes.wintypes.DWORD),
    ]


class THREADENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.wintypes.DWORD),
        ("cntUsage", ctypes.wintypes.DWORD),
        ("th32ThreadID", ctypes.wintypes.DWORD),
        ("th32OwnerProcessID", ctypes.wintypes.DWORD),
        ("tpBasePri", ctypes.wintypes.LONG),
        ("tpDeltaPri", ctypes.wintypes.LONG),
        ("dwFlags", ctypes.wintypes.DWORD),
    ]


class STARTUPINFOW(ctypes.Structure):
    """Maps to the Win32 STARTUPINFOW structure."""
    _fields_ = [
        ("cb",              ctypes.wintypes.DWORD),
        ("lpReserved",      ctypes.wintypes.LPWSTR),
        ("lpDesktop",       ctypes.wintypes.LPWSTR),
        ("lpTitle",         ctypes.wintypes.LPWSTR),
        ("dwX",             ctypes.wintypes.DWORD),
        ("dwY",             ctypes.wintypes.DWORD),
        ("dwXSize",         ctypes.wintypes.DWORD),
        ("dwYSize",         ctypes.wintypes.DWORD),
        ("dwXCountChars",   ctypes.wintypes.DWORD),
        ("dwYCountChars",   ctypes.wintypes.DWORD),
        ("dwFillAttribute", ctypes.wintypes.DWORD),
        ("dwFlags",         ctypes.wintypes.DWORD),
        ("wShowWindow",     ctypes.wintypes.WORD),
        ("cbReserved2",     ctypes.wintypes.WORD),
        ("lpReserved2",     ctypes.c_char_p),
        ("hStdInput",       ctypes.wintypes.HANDLE),
        ("hStdOutput",      ctypes.wintypes.HANDLE),
        ("hStdError",       ctypes.wintypes.HANDLE),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    """Maps to the Win32 PROCESS_INFORMATION structure."""
    _fields_ = [
        ("hProcess",    ctypes.wintypes.HANDLE),
        ("hThread",     ctypes.wintypes.HANDLE),
        ("dwProcessId", ctypes.wintypes.DWORD),
        ("dwThreadId",  ctypes.wintypes.DWORD),
    ]


# ---------------------------------------------------------------------------
# SandboxProcess
# ---------------------------------------------------------------------------

class SandboxProcess:
    """Lightweight process handle returned by _launch_process.

    Provides the interface expected by ``WindowsJobObject.add_process()``,
    ``process_registry``, and the teardown paths in
    ``launch_under_job_object``.

    Attributes:
        pid: Process ID.
        args: Command-line as a list; ``args[0]`` is the executable path.
        returncode: Exit code once the process has exited, ``None`` while running.
    """

    def __init__(
        self,
        pid: int,
        process_handle,
        thread_handle,
        args: list,
    ):
        self.pid = pid
        self._process_handle = process_handle
        self._thread_handle = thread_handle
        self.args = args
        self.returncode = None
        self.handle: int | None = process_handle

    def poll(self):
        """Return exit code if the process has exited, ``None`` if still running.

        Closes OS handles when the process exits to release resources.
        Safe to call multiple times after exit.
        """
        if self._process_handle is None:
            return self.returncode
        exit_code = ctypes.wintypes.DWORD(_STILL_ACTIVE)
        ctypes.windll.kernel32.GetExitCodeProcess(
            self._process_handle, ctypes.byref(exit_code)
        )
        if exit_code.value == _STILL_ACTIVE:
            return None
        self.returncode = exit_code.value
        self._close_handles()
        return self.returncode

    def terminate(self) -> None:
        """Send a termination signal to the process."""
        if self._process_handle:
            ctypes.windll.kernel32.TerminateProcess(self._process_handle, 1)

    def kill(self) -> None:
        """Terminate the process immediately (same as terminate on Windows)."""
        self.terminate()

    def wait(self) -> int:
        """Wait for the process to exit and return its exit code.

        Blocks indefinitely until the process terminates.  Closes OS handles
        on return regardless of success.
        """
        if self._process_handle:
            ctypes.windll.kernel32.WaitForSingleObject(
                self._process_handle,
                ctypes.wintypes.DWORD(0xFFFFFFFF),  # INFINITE
            )
            exit_code = ctypes.wintypes.DWORD(0)
            ctypes.windll.kernel32.GetExitCodeProcess(
                self._process_handle, ctypes.byref(exit_code)
            )
            self.returncode = exit_code.value
        self._close_handles()
        return self.returncode

    def resume(self) -> None:
        """Resume the suspended main thread using the stored thread handle.

        Uses the thread handle from ``PROCESS_INFORMATION`` returned by
        ``CreateProcessW`` — no thread snapshot required.  The thread
        handle is closed immediately after the resume call.

        Raises:
            RuntimeError: If the thread handle is already closed or
                ``ResumeThread`` reports failure.
        """
        if not self._thread_handle:
            raise RuntimeError(
                f"Thread handle is not open for process {self.pid}. "
                "resume() must be called exactly once after process creation."
            )
        result = ctypes.windll.kernel32.ResumeThread(self._thread_handle)
        ctypes.windll.kernel32.CloseHandle(self._thread_handle)
        self._thread_handle = None
        if result == -1:
            error_code = ctypes.windll.kernel32.GetLastError()
            raise RuntimeError(
                f"ResumeThread failed for process {self.pid}. Error code: {error_code}"
            )

    def _close_handles(self) -> None:
        """Close process and thread handles to release OS resources."""
        if self._thread_handle:
            ctypes.windll.kernel32.CloseHandle(self._thread_handle)
            self._thread_handle = None
        if self._process_handle:
            ctypes.windll.kernel32.CloseHandle(self._process_handle)
            self._process_handle = None
            self.handle = None  # same OS handle value — prevent use-after-close


# ---------------------------------------------------------------------------
# WindowsJobObject
# ---------------------------------------------------------------------------

class WindowsJobObject:
    """Windows Job Object wrapper for emulator process isolation.

    Wraps a named Win32 Job Object with memory cap, CPU hard cap, and
    kill-on-close semantics.  The expected call sequence is:

        job = WindowsJobObject(name, memory_limit_mb, cpu_limit_percent)
        job.create()
        job.add_process(sandbox_process)
        # ... emulator runs ...
        job.terminate_all()

    ``launch_under_job_object`` in this module handles this sequence and is
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
        """Create the Win32 Job Object and apply memory and CPU limits.

        Raises:
            RuntimeError: If ``CreateJobObjectW`` fails or either limit
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

        self.set_memory_limit(self.memory_limit_mb)
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


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

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


def _load_era_limits(era: str) -> Tuple[int, int]:
    """Load memory_limit_mb and cpu_limit_percent for *era* from eras.yaml.

    Returns:
        (memory_limit_mb, cpu_limit_percent)

    Raises:
        FileNotFoundError: If eras.yaml is missing.
        RuntimeError: If parsing fails, the era is unknown, or either
            required field is absent.
    """
    try:
        with _ERAS_YAML.open('r') as f:
            eras_config = yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"eras.yaml not found at {_ERAS_YAML}")
    except yaml.YAMLError as exc:
        raise RuntimeError(f"Failed to parse eras.yaml: {exc}")

    if era not in eras_config:
        raise RuntimeError(
            f"Era '{era}' not found in eras.yaml. Available: {list(eras_config.keys())}"
        )

    era_cfg = eras_config[era]

    memory_limit_mb = era_cfg.get('memory_limit_mb')
    if memory_limit_mb is None:
        raise RuntimeError(
            f"memory_limit_mb not defined for era '{era}' in eras.yaml"
        )

    cpu_limit_percent = era_cfg.get('cpu_limit_percent')
    if cpu_limit_percent is None:
        raise RuntimeError(
            f"cpu_limit_percent not defined for era '{era}' in eras.yaml"
        )

    return int(memory_limit_mb), int(cpu_limit_percent)


def _launch_process(
    executable_path: str,
    args: List[str],
    creation_flags: int,
) -> SandboxProcess:
    """Launch a process under the current user account via CreateProcessW.

    The process is created with ``creation_flags`` — callers pass
    ``CREATE_SUSPENDED`` so the process can be assigned to a Job Object
    before any code runs.

    Args:
        executable_path: Full path to the emulator executable.
        args: Additional command-line arguments.
        creation_flags: Windows process creation flags.

    Returns:
        ``SandboxProcess`` with pid, process handle, and thread handle.

    Raises:
        RuntimeError: If ``CreateProcessW`` fails.
    """
    cmd_line = subprocess.list2cmdline([executable_path] + args)
    cmd_buf = ctypes.create_unicode_buffer(cmd_line)

    cwd = str(Path(executable_path).parent)

    si = STARTUPINFOW()
    si.cb = ctypes.sizeof(STARTUPINFOW)
    pi = PROCESS_INFORMATION()

    logger.debug(
        "launch_process: exe=%s cwd=%s flags=%#x args=%s cmd=%s",
        executable_path, cwd, creation_flags, args, cmd_line,
    )

    result = ctypes.windll.kernel32.CreateProcessW(
        ctypes.c_wchar_p(executable_path),
        cmd_buf,
        None,
        None,
        False,
        ctypes.wintypes.DWORD(creation_flags),
        None,
        ctypes.c_wchar_p(cwd) if cwd else None,
        ctypes.byref(si),
        ctypes.byref(pi),
    )

    if not result:
        error_code = ctypes.windll.kernel32.GetLastError()
        raise RuntimeError(
            f"Failed to launch '{os.path.basename(executable_path)}'. "
            f"Error code: {error_code}."
        )

    return SandboxProcess(
        pid=pi.dwProcessId,
        process_handle=pi.hProcess,
        thread_handle=pi.hThread,
        args=[executable_path] + args,
    )


def launch_under_job_object(
    executable_path: str,
    args: List[str],
    media_paths: List[str],
    era: str,
    job_name: str
) -> Tuple[SandboxProcess, "WindowsJobObject"]:
    """Launch an emulator under the current user account in a Windows Job Object.

    Orchestrates the full startup sequence:
      1. Load memory_limit_mb and cpu_limit_percent for ``era`` from eras.yaml.
      2. Create a ``WindowsJobObject`` and apply both limits plus kill-on-close.
      3. Launch the emulator as the current user in a suspended state
         (prevents a race between process start and job assignment).
      4. Assign the process to the job object.
      5. Resume the process.

    The launch is aborted and an error surfaced if:
      - ``CreateProcessW`` fails for any reason.
      - Job Object creation or assignment fails.

    There is no unsandboxed fallback.

    Args:
        executable_path: Full path to the emulator executable.
        args: Additional command-line arguments for the emulator.
        media_paths: Media paths passed to the emulator (informational only —
            Job Objects cannot restrict filesystem access on Windows).
        era: Era key (e.g. ``"dos"``) used to look up limits in ``eras.yaml``.
        job_name: Unique name for the Win32 Job Object.

    Returns:
        ``(process, job_object)`` — the running ``SandboxProcess`` and the
        ``WindowsJobObject`` that owns it.  The caller must call
        ``job_object.terminate_all()`` when the emulator exits.

    Raises:
        FileNotFoundError: If ``eras.yaml`` is not found.
        RuntimeError: If any step in the startup sequence fails.
    """
    job_object = None
    process = None
    base_flags = None

    # --- Phase 1: config, job creation, initial process launch ---
    # Any failure here tears down whatever was created and raises a clean RuntimeError.
    try:
        memory_limit_mb, cpu_limit_percent = _load_era_limits(era)

        job_object = WindowsJobObject(job_name, memory_limit_mb, cpu_limit_percent)
        job_object.create()

        base_flags = subprocess.CREATE_NEW_PROCESS_GROUP | _CREATE_SUSPENDED

        process = _launch_process(executable_path, args, base_flags)

        # Windows 11 pre-assigns child processes to an OS-managed job object.
        # Detect this on the child itself after launch, then kill and re-launch
        # with CREATE_BREAKAWAY_FROM_JOB so it escapes the OS job and can be
        # cleanly assigned to ours.
        if _process_in_job(process.pid):
            try:
                process.kill()
                process.wait()
            except Exception:
                pass
            process = _launch_process(
                executable_path, args, base_flags | _CREATE_BREAKAWAY_FROM_JOB
            )

    except Exception as e:
        cleanup_errors = []
        if process:
            try:
                process.kill()
                process.wait()
            except Exception:
                pass
        if job_object:
            try:
                job_object.terminate_all()
            except Exception as ce:
                cleanup_errors.append(str(ce))
        msg = f"Failed to launch {executable_path} under job object: {str(e)}"
        if cleanup_errors:
            msg += f" (Cleanup errors: {'; '.join(cleanup_errors)})"
        raise RuntimeError(msg)

    # --- Phase 2: assign to job, breakaway retry if needed, resume ---
    # Runs entirely outside Phase 1's except handler.  retry_with_breakaway is caught
    # and handled here — it never reaches Phase 1's cleanup block.  Each error path
    # below performs its own teardown before raising a clean RuntimeError.

    # SAFETY: handle is closed by wait(); do not call add_process after kill/wait
    _needs_breakaway_retry = False
    try:
        job_object.add_process(process)
    except RuntimeError as exc:
        if "retry_with_breakaway" not in str(exc):
            try:
                process.kill()
                process.wait()
            except Exception:
                pass
            try:
                job_object.terminate_all()
            except Exception:
                pass
            raise RuntimeError(f"Failed to assign process to job object: {exc}")
        _needs_breakaway_retry = True

    if _needs_breakaway_retry:
        try:
            process.kill()
            process.wait()
        except Exception:
            pass
        try:
            process = _launch_process(
                executable_path, args, base_flags | _CREATE_BREAKAWAY_FROM_JOB
            )
        except Exception as exc2:
            try:
                job_object.terminate_all()
            except Exception:
                pass
            raise RuntimeError(
                f"Cannot launch '{os.path.basename(executable_path)}': "
                f"CREATE_BREAKAWAY_FROM_JOB failed after assignment error 5 ({exc2})."
            )
        try:
            job_object.add_process(process)
        except Exception as exc3:
            try:
                process.kill()
                process.wait()
            except Exception:
                pass
            try:
                job_object.terminate_all()
            except Exception:
                pass
            raise RuntimeError(
                f"Failed to assign breakaway process to job object: {exc3}"
            )

    try:
        process.resume()
    except Exception as exc:
        try:
            process.kill()
            process.wait()
        except Exception:
            pass
        try:
            job_object.terminate_all()
        except Exception:
            pass
        raise RuntimeError(f"Failed to resume suspended process: {exc}")

    # pi.hThread was closed inside resume(). pi.hProcess is kept open so that
    # SandboxProcess.poll() can call GetExitCodeProcess to detect exit.
    # _close_handles() (called from poll() on exit) closes it exactly once.
    return (process, job_object)
