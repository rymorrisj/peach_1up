"""
Windows Job Objects wrapper for Peach 1UP
Provides process isolation, memory limits, and network blocking for emulator processes.
"""

import subprocess
import ctypes
import ctypes.wintypes
import win32com.client
import win32process
from typing import List, Tuple
import os
import yaml


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
    """Windows Job Object wrapper for emulator process isolation."""

    def __init__(self, name: str, memory_limit_mb: int):
        """
        Initialize job object with name and memory limit.

        Args:
            name: Unique name for the job object
            memory_limit_mb: Memory limit in MB from eras.yaml
        """
        self.name = name
        self.memory_limit_mb = memory_limit_mb
        self.job_handle = None
        self.firewall_rules = []  # Track rules for cleanup
        self.process_name = None
        self.pid = None

    def create(self) -> None:
        """
        Create the Windows Job Object.

        Raises:
            RuntimeError: If job object creation fails
        """
        # Create job object using Windows API
        self.job_handle = ctypes.windll.kernel32.CreateJobObjectW(
            None,  # Security attributes
            ctypes.c_wchar_p(self.name)  # Job object name as Unicode
        )

        if not self.job_handle:
            error_code = ctypes.windll.kernel32.GetLastError()
            raise RuntimeError(f"Failed to create Job Object '{self.name}'. Error code: {error_code}")

        # Set memory limit immediately after creation
        self.set_memory_limit(self.memory_limit_mb)

    def set_memory_limit(self, limit_mb: int) -> None:
        """
        Set memory limit via JOB_OBJECT_EXTENDED_LIMIT_INFORMATION.

        Args:
            limit_mb: Memory limit in megabytes

        Raises:
            RuntimeError: If setting memory limit fails
        """
        if not self.job_handle:
            raise RuntimeError("Job object not created. Call create() first.")

        # Set up limit information
        limit_info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limit_info.BasicLimitInformation.LimitFlags = 0x00000100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
        limit_info.ProcessMemoryLimit = limit_mb * 1024 * 1024  # Convert MB to bytes

        # Apply the memory limit
        result = ctypes.windll.kernel32.SetInformationJobObject(
            self.job_handle,
            ctypes.wintypes.DWORD(9),  # JobObjectExtendedLimitInformation
            ctypes.byref(limit_info),
            ctypes.sizeof(limit_info)
        )

        if not result:
            error_code = ctypes.windll.kernel32.GetLastError()
            raise RuntimeError(f"Failed to set memory limit to {limit_mb}MB. Error code: {error_code}")

    def add_process(self, process: subprocess.Popen) -> None:
        """
        Add process to job object and apply all restrictions.

        Args:
            process: The subprocess.Popen object to add to job object

        Raises:
            RuntimeError: If adding process to job object fails
        """
        if not self.job_handle:
            raise RuntimeError("Job object not created. Call create() first.")

        if not process or not process.pid:
            raise RuntimeError("Invalid process or process not started.")

        # Store process info for firewall rule naming
        self.pid = process.pid
        # Extract process name from executable path
        if hasattr(process, 'args') and process.args:
            executable_path = process.args[0] if isinstance(process.args, list) else str(process.args)
            self.process_name = os.path.basename(executable_path).replace('.exe', '')
        else:
            self.process_name = f"process_{self.pid}"

        # Get proper process handle using OpenProcess
        process_handle = ctypes.windll.kernel32.OpenProcess(
            0x001F0FFF,  # PROCESS_ALL_ACCESS
            # TODO P2: Reduce to minimal required access mask for hardening
            False,
            process.pid
        )

        if not process_handle:
            error_code = ctypes.windll.kernel32.GetLastError()
            raise RuntimeError(f"Failed to open process {self.pid}. Error code: {error_code}")

        try:
            # Add process to job object
            result = ctypes.windll.kernel32.AssignProcessToJobObject(
                self.job_handle,
                process_handle
            )

            if not result:
                error_code = ctypes.windll.kernel32.GetLastError()
                raise RuntimeError(f"Failed to add process {self.pid} to job object. Error code: {error_code}")

        finally:
            # Always close the process handle
            ctypes.windll.kernel32.CloseHandle(process_handle)

        # Apply network restrictions via Windows Firewall
        executable_full_path = process.args[0] if isinstance(process.args, list) else str(process.args)
        self.block_network_access(executable_full_path, self.pid)

    def block_network_access(self, executable_path: str, pid: int) -> None:
        """
        Create Windows Firewall rules to block both inbound and outbound network access.
        Rules: Peach1UP_Block_{process_name}_{pid}_out and Peach1UP_Block_{process_name}_{pid}_in

        Args:
            executable_path: Full path to the executable
            pid: Process ID for rule naming

        Raises:
            RuntimeError: If firewall rule creation fails
        """
        try:
            # Initialize Windows Firewall COM objects
            fw_policy = win32com.client.Dispatch("HNetCfg.FwPolicy2")

            # Create outbound rule
            fw_rule_out = win32com.client.Dispatch("HNetCfg.FWRule")
            rule_name_out = f"Peach1UP_Block_{self.process_name}_{pid}_out"
            fw_rule_out.Name = rule_name_out
            fw_rule_out.ApplicationName = executable_path
            fw_rule_out.Direction = 2  # NET_FW_RULE_DIR_OUT (outbound)
            fw_rule_out.Action = 0     # NET_FW_ACTION_BLOCK
            fw_rule_out.Enabled = True
            fw_rule_out.Profiles = 0x7FFFFFFF  # All network profiles (domain, private, public)
            fw_policy.Rules.Add(fw_rule_out)
            self.firewall_rules.append(rule_name_out)

            # Create inbound rule
            fw_rule_in = win32com.client.Dispatch("HNetCfg.FWRule")
            rule_name_in = f"Peach1UP_Block_{self.process_name}_{pid}_in"
            fw_rule_in.Name = rule_name_in
            fw_rule_in.ApplicationName = executable_path
            fw_rule_in.Direction = 1   # NET_FW_RULE_DIR_IN (inbound)
            fw_rule_in.Action = 0      # NET_FW_ACTION_BLOCK
            fw_rule_in.Enabled = True
            fw_rule_in.Profiles = 0x7FFFFFFF  # All network profiles (domain, private, public)
            fw_policy.Rules.Add(fw_rule_in)
            self.firewall_rules.append(rule_name_in)

        except Exception as e:
            # If any rule creation fails, attempt cleanup of any created rules
            if self.firewall_rules:
                self._cleanup_partial_firewall_rules()
            raise RuntimeError(f"Failed to create firewall rules for {self.process_name}_{pid}. Error: {str(e)}")

    def _cleanup_partial_firewall_rules(self) -> None:
        """
        Helper to clean up partially created firewall rules on failure.

        Raises:
            RuntimeError: If any cleanup operations fail
        """
        cleanup_errors = []

        try:
            fw_policy = win32com.client.Dispatch("HNetCfg.FwPolicy2")
            for rule_name in self.firewall_rules[:]:  # Copy list to avoid modification during iteration
                try:
                    fw_policy.Rules.Remove(rule_name)
                    self.firewall_rules.remove(rule_name)
                except Exception as e:
                    cleanup_errors.append(f"Failed to remove rule {rule_name}: {str(e)}")

        except Exception as e:
            cleanup_errors.append(f"Failed to initialize firewall policy for cleanup: {str(e)}")

        # Raise combined error if any cleanup operations failed
        if cleanup_errors:
            raise RuntimeError(f"Firewall rule cleanup errors: {'; '.join(cleanup_errors)}")

    def cleanup_firewall_rule(self, process_name: str, pid: int) -> None:
        """
        Delete firewall rules on clean process exit.

        Args:
            process_name: Process name for rule identification (legacy parameter - uses self.firewall_rules)
            pid: Process ID for rule identification (legacy parameter - uses self.firewall_rules)

        Raises:
            RuntimeError: If cleanup operations fail
        """
        if not self.firewall_rules:
            return  # No rules to clean up

        cleanup_errors = []
        failed_rules = []

        try:
            fw_policy = win32com.client.Dispatch("HNetCfg.FwPolicy2")

            # Attempt to remove all tracked firewall rules
            for rule_name in self.firewall_rules[:]:  # Copy list to avoid modification during iteration
                try:
                    fw_policy.Rules.Remove(rule_name)
                    self.firewall_rules.remove(rule_name)  # Only remove if successful
                except Exception as e:
                    cleanup_errors.append(f"Failed to remove rule {rule_name}: {str(e)}")
                    failed_rules.append(rule_name)

        except Exception as e:
            cleanup_errors.append(f"Failed to initialize firewall policy for cleanup: {str(e)}")
            failed_rules.extend(self.firewall_rules)  # All rules failed due to policy init failure

        # Raise combined error if any cleanup operations failed
        if cleanup_errors:
            raise RuntimeError(f"Firewall rule cleanup failed for {self.process_name}_{self.pid}. "
                             f"Manual cleanup required in Windows Firewall Advanced Security. "
                             f"Failed rules: {', '.join(failed_rules)}. "
                             f"Errors: {'; '.join(cleanup_errors)}")

    def terminate_all(self) -> None:
        """
        Terminate all processes in the job object and clean up resources.
        Collects all errors and raises combined RuntimeError at the end if any occur.

        Raises:
            RuntimeError: If any termination or cleanup operations fail
        """
        termination_errors = []

        # Step 1: Clean up firewall rules first (while we still have process info)
        if self.process_name and self.pid:
            try:
                self.cleanup_firewall_rule(self.process_name, self.pid)
            except Exception as e:
                termination_errors.append(f"Firewall cleanup error: {str(e)}")

        # Step 2: Terminate all processes in the job object
        if self.job_handle:
            try:
                result = ctypes.windll.kernel32.TerminateJobObject(
                    self.job_handle,
                    1  # Exit code for terminated processes
                )

                if not result:
                    error_code = ctypes.windll.kernel32.GetLastError()
                    termination_errors.append(f"TerminateJobObject failed with error code: {error_code}")

            except Exception as e:
                termination_errors.append(f"Exception during job termination: {str(e)}")

            # Step 3: Close the job handle
            try:
                ctypes.windll.kernel32.CloseHandle(self.job_handle)
            except Exception as e:
                termination_errors.append(f"Failed to close job handle: {str(e)}")

        # Step 4: Always reset job handle to None regardless of success/failure
        self.job_handle = None

        # Step 5: Raise combined error if any operations failed
        if termination_errors:
            raise RuntimeError(f"Job object termination encountered errors for {self.name}. "
                             f"Some resources may require manual cleanup. "
                             f"Errors: {'; '.join(termination_errors)}")

    def is_active(self) -> bool:
        """
        Check if job object is active and handle is still valid.

        Returns:
            bool: True if job object exists and handle is valid, False otherwise

        Notes:
            - Safe to call at any point including before create() is called
            - Never raises exceptions - returns False on any failure
            - Uses lightweight Windows API check to verify handle validity
        """
        # First check: do we have a handle at all?
        if not self.job_handle:
            return False

        try:
            # Lightweight API check: query basic accounting information
            # This will fail if the handle is invalid/closed without modifying anything
            accounting_info = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION()

            result = ctypes.windll.kernel32.QueryInformationJobObject(
                self.job_handle,
                ctypes.wintypes.DWORD(1),  # JobObjectBasicAccountingInformation
                ctypes.byref(accounting_info),
                ctypes.sizeof(accounting_info),
                None  # Return length not needed
            )

            return bool(result)

        except Exception:
            # Any exception means the handle is invalid or we can't query it
            return False

    def _resume_suspended_process(self, process: subprocess.Popen) -> None:
        """Resume the main thread of a suspended process."""
        # Constants
        TH32CS_SNAPTHREAD = 0x00000004
        THREAD_SUSPEND_RESUME = 0x0002

        # Create snapshot of threads
        snapshot = ctypes.windll.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
        if snapshot == -1:
            raise RuntimeError("Failed to create thread snapshot")

        try:
            te32 = THREADENTRY32()
            te32.dwSize = ctypes.sizeof(THREADENTRY32)

            # Find main thread for our process
            main_thread_id = None
            if ctypes.windll.kernel32.Thread32First(snapshot, ctypes.byref(te32)):
                while True:
                    if te32.th32OwnerProcessID == process.pid:
                        main_thread_id = te32.th32ThreadID
                        break  # First thread found is typically the main thread
                    if not ctypes.windll.kernel32.Thread32Next(snapshot, ctypes.byref(te32)):
                        break

            if not main_thread_id:
                raise RuntimeError(f"Could not find main thread for process {process.pid}")

            # Resume the main thread
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


def launch_under_job_object(
    executable_path: str,
    args: List[str],
    media_paths: List[str],
    era: str,
    job_name: str
) -> Tuple[subprocess.Popen, WindowsJobObject]:
    """
    Launch emulator under Job Object with era-specific memory limits.

    Args:
        executable_path: Full path to emulator executable
        args: Command line arguments for emulator
        media_paths: List of media file paths (for read-only enforcement comment)
        era: Era name to look up memory limit in eras.yaml
        job_name: Unique name for the job object

    Returns:
        Tuple of (subprocess.Popen process, WindowsJobObject instance)

    Raises:
        RuntimeError: If eras.yaml loading, job creation, or process launch fails
        FileNotFoundError: If eras.yaml or executable not found

    Notes:
        # KNOWN LIMITATION: Job Objects cannot enforce read-only filesystem access on Windows.
        # Read-only enforcement must be handled at the media path level when passing to emulator.
        # See CLAUDE.md Known Gotchas for details.
    """
    job_object = None
    process = None

    try:
        # Step 1: Load memory limit from eras.yaml
        try:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'eras.yaml')
            with open(config_path, 'r') as f:
                eras_config = yaml.safe_load(f)

            if era not in eras_config:
                raise RuntimeError(f"Era '{era}' not found in eras.yaml. Available: {list(eras_config.keys())}")

            memory_limit_mb = eras_config[era].get('memory_limit_mb')
            if memory_limit_mb is None:
                raise RuntimeError(f"memory_limit_mb not defined for era '{era}' in eras.yaml")

        except FileNotFoundError:
            raise FileNotFoundError(f"eras.yaml not found at {config_path}")
        except yaml.YAMLError as e:
            raise RuntimeError(f"Failed to parse eras.yaml: {str(e)}")

        # Step 2: Create and configure job object
        job_object = WindowsJobObject(job_name, memory_limit_mb)
        job_object.create()

        # Step 3: Launch emulator process in suspended state to prevent race condition
        process = subprocess.Popen(
            args=[executable_path] + args,
            cwd=os.path.dirname(executable_path),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | win32process.CREATE_SUSPENDED
        )

        # Step 4: Add process to job object (includes firewall rule creation)
        job_object.add_process(process)

        # Step 5: Resume process now that it's safely in the job object
        job_object._resume_suspended_process(process)

        return (process, job_object)

    except Exception as e:
        # Cleanup on any failure - never leave orphaned resources
        cleanup_errors = []

        if job_object:
            try:
                job_object.terminate_all()  # This handles both process and job cleanup
            except Exception as cleanup_e:
                cleanup_errors.append(f"Job object cleanup failed: {str(cleanup_e)}")

        # Raise original error with cleanup errors included in message if any occurred
        error_message = f"Failed to launch {executable_path} under job object: {str(e)}"
        if cleanup_errors:
            error_message += f" (Cleanup errors: {'; '.join(cleanup_errors)})"

        raise RuntimeError(error_message)