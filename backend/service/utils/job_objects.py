"""
Windows Job Objects wrapper for Peach 1UP.

Provides process isolation, memory limits, and network blocking for emulator
processes running natively on the Windows host.  Each emulator launch gets its
own named Job Object so multiple profiles can run without interfering with each
other.

Network blocking is implemented via Windows Firewall COM rules rather than
Job Object flags because Job Objects have no built-in network-restriction API.
Rules are named ``Peach1UP_Block_<process>_<pid>_in`` and
``Peach1UP_Block_<process>_<pid>_out`` and are removed on clean exit.
"""

import subprocess
import ctypes
import ctypes.wintypes
from typing import List, Tuple
from pathlib import Path
import os
import yaml

# Win32 CREATE_SUSPENDED flag — avoids a hard dependency on pywin32 at module import time.
_CREATE_SUSPENDED = 0x00000004

# Anchor eras.yaml to the project root regardless of CWD.
# job_objects.py lives at backend/service/utils/ — 4 parents up is the project root.
_ERAS_YAML = Path(__file__).resolve().parent.parent.parent.parent / "config" / "eras.yaml"

# CREATE_BREAKAWAY_FROM_JOB: child process escapes the parent's Job Object so
# it can be cleanly assigned to our own.  Used when the launcher is already
# inside a Windows Job Object (common on Windows 11).
_CREATE_BREAKAWAY_FROM_JOB = 0x01000000


# Windows API structures for job object limits
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


class WindowsJobObject:
    """Windows Job Object wrapper for emulator process isolation.

    Wraps a named Win32 Job Object and the associated Windows Firewall rules
    that block network access for the emulator process.  The expected call
    sequence is:

        job = WindowsJobObject(name, memory_limit_mb)
        job.create()
        job.add_process(popen_process)   # assigns process + creates firewall rules
        # ... emulator runs ...
        job.terminate_all()              # terminates process + removes rules

    ``launch_under_job_object`` in this module handles this sequence and is
    the preferred entry point for callers outside this file.

    Attributes:
        name: Unique name for the Win32 Job Object.
        memory_limit_mb: Per-process memory cap applied at creation.
        job_handle: Raw Win32 handle; ``None`` until ``create()`` is called.
        firewall_rule_names: Names of Windows Firewall rules created for the
            current process; used for cleanup on exit.
        process_name: Basename of the emulator executable (no extension).
        pid: PID of the emulator process added via ``add_process``.
    """

    def __init__(self, name: str, memory_limit_mb: int):
        """
        Args:
            name: Unique name for the job object.
            memory_limit_mb: Memory limit in MB (sourced from eras.yaml).
        """
        self.name = name
        self.memory_limit_mb = memory_limit_mb
        self.job_handle = None
        self.firewall_rule_names: list[str] = []  # names of active firewall rules for cleanup
        self.process_name = None
        self.pid = None

    def create(self) -> None:
        """Create the Win32 Job Object and apply the configured memory limit.

        Raises:
            RuntimeError: If ``CreateJobObjectW`` fails or the memory limit
                cannot be set.
        """
        # CreateJobObjectW returns a handle, or NULL on failure
        self.job_handle = ctypes.windll.kernel32.CreateJobObjectW(
            None,                       # default security attributes
            ctypes.c_wchar_p(self.name) # job object name (Unicode)
        )

        if not self.job_handle:
            error_code = ctypes.windll.kernel32.GetLastError()
            raise RuntimeError(f"Failed to create Job Object '{self.name}'. Error code: {error_code}")

        self.set_memory_limit(self.memory_limit_mb)

    def set_memory_limit(self, limit_mb: int) -> None:
        """Set the per-process memory cap via ``JOBOBJECT_EXTENDED_LIMIT_INFORMATION``.

        Args:
            limit_mb: Memory limit in megabytes.

        Raises:
            RuntimeError: If the job handle is not open or
                ``SetInformationJobObject`` fails.
        """
        if not self.job_handle:
            raise RuntimeError("Job object not created. Call create() first.")

        limit_info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limit_info.BasicLimitInformation.LimitFlags = 0x00000100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
        limit_info.ProcessMemoryLimit = limit_mb * 1024 * 1024    # MB → bytes

        result = ctypes.windll.kernel32.SetInformationJobObject(
            self.job_handle,
            ctypes.wintypes.DWORD(9),   # JobObjectExtendedLimitInformation
            ctypes.byref(limit_info),
            ctypes.sizeof(limit_info)
        )

        if not result:
            error_code = ctypes.windll.kernel32.GetLastError()
            raise RuntimeError(f"Failed to set memory limit to {limit_mb}MB. Error code: {error_code}")

    def add_process(self, process: subprocess.Popen) -> None:
        """Assign a process to the job object and create its firewall block rules.

        Opens the process with ``OpenProcess``, calls
        ``AssignProcessToJobObject``, then calls ``block_network_access``.
        The process handle is closed immediately after assignment; the job
        object retains its own reference.

        Args:
            process: A ``subprocess.Popen`` instance that has already been launched.

        Raises:
            RuntimeError: If the job handle is not open, the process is
                invalid, ``OpenProcess`` fails, ``AssignProcessToJobObject``
                fails, or firewall rule creation fails.
        """
        if not self.job_handle:
            raise RuntimeError("Job object not created. Call create() first.")

        if not process or not process.pid:
            raise RuntimeError("Invalid process or process not started.")

        self.pid = process.pid
        # Derive a short name for firewall rule naming from the executable basename
        if hasattr(process, 'args') and process.args:
            executable_path = process.args[0] if isinstance(process.args, list) else str(process.args)
            self.process_name = os.path.basename(executable_path).replace('.exe', '')
        else:
            self.process_name = f"process_{self.pid}"
        # Perviously was using 0x001F0FFF which requests every possible permission on the process. Updated to use minimal permissions
        process_handle = ctypes.windll.kernel32.OpenProcess(
            0x0201,  # PROCESS_SET_QUOTA | PROCESS_TERMINATE — minimum for AssignProcessToJobObject
            False,
            process.pid
        )

        if not process_handle:
            error_code = ctypes.windll.kernel32.GetLastError()
            raise RuntimeError(f"Failed to open process {self.pid}. Error code: {error_code}")

        try:
            # Informational check — captured to produce a richer error message
            # if AssignProcessToJobObject still fails after the breakaway re-launch
            # performed in launch_under_job_object().
            _in_job = ctypes.wintypes.BOOL(False)
            ctypes.windll.kernel32.IsProcessInJob(
                process_handle, None, ctypes.byref(_in_job)
            )
            already_in_job = bool(_in_job)

            result = ctypes.windll.kernel32.AssignProcessToJobObject(
                self.job_handle,
                process_handle
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
            # Always close the process handle — the job object retains its own reference
            ctypes.windll.kernel32.CloseHandle(process_handle)

        executable_full_path = process.args[0] if isinstance(process.args, list) else str(process.args)
        self.block_network_access(executable_full_path, self.pid)

    def block_network_access(self, executable_path: str, pid: int) -> None:
        """Create Windows Firewall rules blocking all inbound and outbound traffic
        for the emulator executable.

        Rules are named ``Peach1UP_Block_<process_name>_<pid>_out`` and
        ``Peach1UP_Block_<process_name>_<pid>_in`` and apply across all
        network profiles (domain, private, public).  Both rule names are
        appended to ``self.firewall_rule_names`` so they can be removed on
        exit.  If either rule fails to be created, any partially added rules
        are removed before raising.

        Args:
            executable_path: Full path to the emulator executable.
            pid: PID of the emulator process (used in rule naming only).

        Raises:
            RuntimeError: If firewall rule creation fails.
        """
        try:
            try:
                import win32com.client
            except ImportError:
                raise RuntimeError(
                    "Windows Firewall COM interface not available. "
                    "Ensure pywin32 is installed and the Python COM bindings are present. "
                    "Run: pip install pywin32"
                )
            fw_policy = win32com.client.Dispatch("HNetCfg.FwPolicy2")

            # Outbound block rule
            fw_rule_out = win32com.client.Dispatch("HNetCfg.FWRule")
            rule_name_out = f"Peach1UP_Block_{self.process_name}_{pid}_out"
            fw_rule_out.Name = rule_name_out
            fw_rule_out.ApplicationName = executable_path
            fw_rule_out.Direction = 2       # NET_FW_RULE_DIR_OUT
            fw_rule_out.Action = 0          # NET_FW_ACTION_BLOCK
            fw_rule_out.Enabled = True
            fw_rule_out.Profiles = 0x7FFFFFFF  # all network profiles (domain, private, public)
            fw_policy.Rules.Add(fw_rule_out)
            self.firewall_rule_names.append(rule_name_out)
            self._verify_firewall_rule(fw_policy, rule_name_out, "outbound")

            # Inbound block rule
            fw_rule_in = win32com.client.Dispatch("HNetCfg.FWRule")  # noqa: F821 — imported above
            rule_name_in = f"Peach1UP_Block_{self.process_name}_{pid}_in"
            fw_rule_in.Name = rule_name_in
            fw_rule_in.ApplicationName = executable_path
            fw_rule_in.Direction = 1        # NET_FW_RULE_DIR_IN
            fw_rule_in.Action = 0           # NET_FW_ACTION_BLOCK
            fw_rule_in.Enabled = True
            fw_rule_in.Profiles = 0x7FFFFFFF  # all network profiles (domain, private, public)
            fw_policy.Rules.Add(fw_rule_in)
            self.firewall_rule_names.append(rule_name_in)
            self._verify_firewall_rule(fw_policy, rule_name_in, "inbound")

        except RuntimeError:
            if self.firewall_rule_names:
                self._cleanup_partial_firewall_rules()
            raise
        except Exception as e:
            if self.firewall_rule_names:
                self._cleanup_partial_firewall_rules()
            raise RuntimeError(f"Failed to create firewall rules for {self.process_name}_{pid}. Error: {str(e)}")

    def _verify_firewall_rule(self, fw_policy, rule_name: str, direction: str) -> None:
        """Verify that a Windows Firewall rule is active immediately after creation.

        Queries ``fw_policy.Rules.Item()`` to confirm the rule exists and is
        enabled.  Called after each ``Rules.Add()`` in ``block_network_access``
        before the emulator process is resumed.

        Args:
            fw_policy: The ``HNetCfg.FwPolicy2`` COM dispatch object.
            rule_name: Name of the rule to verify.
            direction: ``"inbound"`` or ``"outbound"`` — used in the error message only.

        Raises:
            RuntimeError: If the rule cannot be retrieved or is not enabled,
                formatted for display via the TUI error screen.
        """
        _options = (
            "Options:\n"
            "A) Open Windows Firewall Advanced Security (wf.msc), search for Peach1UP "
            "rules, remove any orphaned entries manually, then retry.\n"
            "B) Confirm Peach 1UP is running as Administrator — firewall rule creation "
            "requires elevated privileges.\n"
            "Awaiting your decision."
        )

        try:
            verified = fw_policy.Rules.Item(rule_name)
        except Exception as e:
            raise RuntimeError(
                f"❌ Error: Firewall rule verification failed\n"
                f"Cause: {direction.capitalize()} block rule '{rule_name}' was added but could not be "
                f"confirmed active — Windows Firewall did not return it on query: {e}\n"
                f"{_options}"
            )

        if not verified or not getattr(verified, 'Enabled', False):
            raise RuntimeError(
                f"❌ Error: Firewall rule verification failed\n"
                f"Cause: {direction.capitalize()} block rule '{rule_name}' was returned by Windows Firewall "
                f"but is not marked as enabled.\n"
                f"{_options}"
            )

    def _cleanup_partial_firewall_rules(self) -> None:
        """Remove any firewall rules already added to ``self.firewall_rule_names``.

        Called only when ``block_network_access`` fails mid-way through rule
        creation to prevent orphaned rules.  Errors during cleanup are
        collected and re-raised together rather than silently swallowed.

        # NAMING: this method and ``cleanup_firewall_rules`` contain identical
        # logic.  The distinction is context: this one is called on partial
        # creation failure; the public one is called on clean exit.  They should
        # be merged into a single private helper at the next refactor pass.

        Raises:
            RuntimeError: If any rule removal fails.
        """
        cleanup_errors = []

        try:
            try:
                import win32com.client as _win32com
            except ImportError:
                raise RuntimeError(
                    "Windows Firewall COM interface not available. "
                    "Ensure pywin32 is installed and the Python COM bindings are present. "
                    "Run: pip install pywin32"
                )
            fw_policy = _win32com.Dispatch("HNetCfg.FwPolicy2")
            for rule_name in self.firewall_rule_names[:]:  # copy to avoid mutation during iteration
                try:
                    fw_policy.Rules.Remove(rule_name)
                    self.firewall_rule_names.remove(rule_name)
                except Exception as e:
                    cleanup_errors.append(f"Failed to remove rule {rule_name}: {str(e)}")

        except Exception as e:
            cleanup_errors.append(f"Failed to initialize firewall policy for cleanup: {str(e)}")

        if cleanup_errors:
            raise RuntimeError(f"Firewall rule cleanup errors: {'; '.join(cleanup_errors)}")

    def cleanup_firewall_rules(self) -> None:
        """Remove all Windows Firewall rules tracked in ``self.firewall_rule_names``.

        Called on clean process exit (from ``terminate_all``) to remove the
        block rules created by ``block_network_access``.  Each rule is removed
        individually so a single stuck rule does not prevent the rest from
        being cleaned up.  All failures are collected and reported together.

        Raises:
            RuntimeError: If any rule removal fails.  The error message includes
                all failed rule names and instructs the user to clean up manually
                via Windows Firewall Advanced Security.
        """
        if not self.firewall_rule_names:
            return

        cleanup_errors = []
        failed_rules = []

        try:
            try:
                import win32com.client as _win32com
            except ImportError:
                raise RuntimeError(
                    "Windows Firewall COM interface not available. "
                    "Ensure pywin32 is installed and the Python COM bindings are present. "
                    "Run: pip install pywin32"
                )
            fw_policy = _win32com.Dispatch("HNetCfg.FwPolicy2")

            for rule_name in self.firewall_rule_names[:]:  # copy to avoid mutation during iteration
                try:
                    fw_policy.Rules.Remove(rule_name)
                    self.firewall_rule_names.remove(rule_name)
                except Exception as e:
                    cleanup_errors.append(f"Failed to remove rule {rule_name}: {str(e)}")
                    failed_rules.append(rule_name)

        except Exception as e:
            cleanup_errors.append(f"Failed to initialize firewall policy for cleanup: {str(e)}")
            failed_rules.extend(self.firewall_rule_names)

        if cleanup_errors:
            raise RuntimeError(
                f"Firewall rule cleanup failed for {self.process_name}_{self.pid}. "
                f"Manual cleanup required in Windows Firewall Advanced Security. "
                f"Failed rules: {', '.join(failed_rules)}. "
                f"Errors: {'; '.join(cleanup_errors)}"
            )

    # NAMING: terminate_all also removes firewall rules and closes the job handle —
    # it is a full resource teardown, not just process termination.  Consider
    # renaming to shutdown() or teardown() at the next refactor pass.
    def terminate_all(self) -> None:
        """Terminate all processes in the job object and release all associated resources.

        Performs three cleanup steps in order, collecting errors from each so
        that a failure in one step does not skip the rest:

          1. Remove Windows Firewall rules (while process info is still available).
          2. Call ``TerminateJobObject`` to kill all processes in the job.
          3. Close the job object handle.

        ``self.job_handle`` is set to ``None`` regardless of success or failure
        so that ``is_active()`` returns ``False`` after this call.

        Raises:
            RuntimeError: If any step fails.  The error message lists all
                failures and notes that manual cleanup may be required.
        """
        termination_errors = []

        # Step 1: Remove firewall rules while process info is still valid
        if self.process_name and self.pid:
            try:
                self.cleanup_firewall_rules()
            except Exception as e:
                termination_errors.append(f"Firewall cleanup error: {str(e)}")

        # Step 2: Terminate all processes in the job
        if self.job_handle:
            try:
                result = ctypes.windll.kernel32.TerminateJobObject(
                    self.job_handle,
                    1  # exit code for terminated processes
                )

                if not result:
                    error_code = ctypes.windll.kernel32.GetLastError()
                    termination_errors.append(f"TerminateJobObject failed with error code: {error_code}")

            except Exception as e:
                termination_errors.append(f"Exception during job termination: {str(e)}")

            # Step 3: Close job handle regardless of termination result
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
            # Any exception means the handle is invalid or unqueryable
            return False

    def _resume_suspended_process(self, process: subprocess.Popen) -> None:
        """Resume the main thread of a process launched in a suspended state.

        ``launch_under_job_object`` starts the emulator with
        ``CREATE_SUSPENDED`` so it can be assigned to the job object before
        any code runs.  This method finds the first thread belonging to the
        process in a system-wide thread snapshot and calls ``ResumeThread``.

        Args:
            process: The suspended ``subprocess.Popen`` instance to resume.

        Raises:
            RuntimeError: If the thread snapshot fails, the main thread cannot
                be found, ``OpenThread`` fails, or ``ResumeThread`` fails.
        """
        TH32CS_SNAPTHREAD = 0x00000004
        THREAD_SUSPEND_RESUME = 0x0002

        # Snapshot all threads system-wide to find ours by owner PID
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
                raise RuntimeError(f"Could not find main thread for process {process.pid}")

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


def _process_in_job(pid: int) -> bool:
    """Return True if the process with *pid* is inside any Windows Job Object.

    Opens the process with ``PROCESS_QUERY_INFORMATION`` (0x0400), calls
    ``IsProcessInJob``, then closes the handle.  Returns ``False`` on any
    error rather than raising so callers can treat it as a safe boolean check.
    """
    handle = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)
    if not handle:
        return False
    try:
        in_job = ctypes.wintypes.BOOL(False)
        ctypes.windll.kernel32.IsProcessInJob(handle, None, ctypes.byref(in_job))
        return bool(in_job)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def launch_direct(
    executable_path: str,
    args: List[str],
    era: str,
    job_name: str,
) -> Tuple[subprocess.Popen, WindowsJobObject]:
    """Launch emulator with firewall rules only, bypassing Job Object isolation.

    Creates a WindowsJobObject stub for firewall management so cleanup remains
    identical to the full job path. The stub has no job_handle, so terminate_all
    skips process termination (only firewall rules are cleaned up).

    # Error 5 (ACCESS_DENIED) on Windows 11 blocks job assignment regardless of
    # CREATE_BREAKAWAY_FROM_JOB. Firewall rules still apply via the stub handle.

    Args:
        executable_path: Full path to the emulator executable.
        args: Additional command-line arguments for the emulator.
        era: Era key used to look up memory_limit_mb in eras.yaml.
        job_name: Unique name passed through to the WindowsJobObject stub.

    Returns:
        (process, stub) — running Popen and a WindowsJobObject with firewall
        rules applied. Caller must call stub.terminate_all() on exit.

    Raises:
        FileNotFoundError: If eras.yaml is missing.
        RuntimeError: If the process cannot be launched or firewall setup fails.
    """
    try:
        with _ERAS_YAML.open('r') as f:
            eras_config = yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"eras.yaml not found at {_ERAS_YAML}")
    except yaml.YAMLError as exc:
        raise RuntimeError(f"Failed to parse eras.yaml: {exc}")

    if era not in eras_config:
        raise RuntimeError(f"Era '{era}' not found in eras.yaml. Available: {list(eras_config.keys())}")

    memory_limit_mb = eras_config[era].get('memory_limit_mb', 512)

    try:
        process = subprocess.Popen(
            [executable_path] + args,
            cwd=os.path.dirname(executable_path) or None,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    except OSError as exc:
        raise RuntimeError(f"Failed to launch '{os.path.basename(executable_path)}': {exc}") from exc

    stub = WindowsJobObject(job_name, memory_limit_mb)
    stub.pid = process.pid
    stub.process_name = os.path.basename(executable_path).replace('.exe', '')
    try:
        stub.block_network_access(executable_path, process.pid)
    except Exception as exc:
        try:
            process.kill()
            process.wait()
        except Exception:
            pass
        raise RuntimeError(f"Failed to create firewall rules: {exc}") from exc

    return process, stub


def launch_under_job_object(
    executable_path: str,
    args: List[str],
    media_paths: List[str],
    era: str,
    job_name: str
) -> Tuple[subprocess.Popen, WindowsJobObject]:
    """Launch an emulator under a Windows Job Object with era-specific resource limits.

    Orchestrates the full startup sequence:
      1. Load the memory limit for ``era`` from ``config/eras.yaml``.
      2. Create a ``WindowsJobObject`` and apply the memory limit.
      3. Launch the emulator in a suspended state (prevents a race between
         process start and job assignment).
      4. Assign the process to the job object (triggers firewall rule creation).
      5. Resume the process.

    On any failure, all resources created up to that point are torn down
    before the exception propagates.

    Args:
        executable_path: Full path to the emulator executable.
        args: Additional command-line arguments for the emulator.
        media_paths: Media paths passed to the emulator.  Read-only enforcement
            is the caller's responsibility — Job Objects cannot restrict
            filesystem access on Windows.
        era: Era key (e.g. ``"dos"``) used to look up ``memory_limit_mb`` in
            ``eras.yaml``.
        job_name: Unique name for the Win32 Job Object.

    Returns:
        ``(process, job_object)`` — the running ``Popen`` instance and the
        ``WindowsJobObject`` that owns it.  The caller must call
        ``job_object.terminate_all()`` when the emulator exits.

    Raises:
        FileNotFoundError: If ``eras.yaml`` is not found.
        RuntimeError: If config loading, job creation, process launch, or job
            assignment fails.  Any cleanup errors are appended to the message.

    Notes:
        KNOWN LIMITATION: Job Objects cannot enforce read-only filesystem access
        on Windows.  Read-only enforcement must be handled at the media path
        level when constructing the emulator command line.
    """
    job_object = None
    process = None
    base_flags = None
    launch_args = None
    launch_cwd = None

    # --- Phase 1: config, job creation, initial process launch ---
    # Any failure here tears down whatever was created and raises a clean RuntimeError.
    try:
        try:
            with _ERAS_YAML.open('r') as f:
                eras_config = yaml.safe_load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"eras.yaml not found at {_ERAS_YAML}")
        except yaml.YAMLError as e:
            raise RuntimeError(f"Failed to parse eras.yaml: {str(e)}")

        if era not in eras_config:
            raise RuntimeError(f"Era '{era}' not found in eras.yaml. Available: {list(eras_config.keys())}")

        memory_limit_mb = eras_config[era].get('memory_limit_mb')
        if memory_limit_mb is None:
            raise RuntimeError(f"memory_limit_mb not defined for era '{era}' in eras.yaml")

        job_object = WindowsJobObject(job_name, memory_limit_mb)
        job_object.create()

        base_flags = subprocess.CREATE_NEW_PROCESS_GROUP | _CREATE_SUSPENDED
        launch_args = [executable_path] + args
        launch_cwd = os.path.dirname(executable_path)

        process = subprocess.Popen(
            launch_args,
            cwd=launch_cwd,
            creationflags=base_flags,
        )

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
            try:
                process = subprocess.Popen(
                    launch_args,
                    cwd=launch_cwd,
                    creationflags=base_flags | _CREATE_BREAKAWAY_FROM_JOB,
                )
            except OSError as exc:
                raise RuntimeError(
                    f"Cannot launch '{os.path.basename(executable_path)}': the process "
                    f"was pre-assigned to a Windows job object and "
                    f"CREATE_BREAKAWAY_FROM_JOB was denied ({exc}). "
                    f"Run Peach 1UP outside a restricted or sandboxed environment."
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
    # Runs entirely outside Phase 1's except handler. retry_with_breakaway is caught
    # and handled here — it never reaches Phase 1's cleanup block. Each error path
    # below performs its own teardown before raising a clean RuntimeError.

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
            raise RuntimeError(
                f"Failed to assign process to job object: {exc}"
            )
        _needs_breakaway_retry = True

    if _needs_breakaway_retry:
        try:
            process.kill()
            process.wait()
        except Exception:
            pass
        try:
            process = subprocess.Popen(
                launch_args,
                cwd=launch_cwd,
                creationflags=base_flags | _CREATE_BREAKAWAY_FROM_JOB,
            )
        except OSError as exc2:
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
        job_object._resume_suspended_process(process)
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

    return (process, job_object)
