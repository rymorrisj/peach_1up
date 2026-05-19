"""
Emulator launch orchestration for Peach 1UP.

Provides the public entry point ``launch_under_job_object`` which runs an
emulator executable under the current user account inside a Windows Job Object
with memory and CPU limits sourced from eras.yaml.
"""

import ctypes
import ctypes.wintypes
import logging
import os
import subprocess
import yaml
from pathlib import Path
from typing import List, Tuple

from backend.service.utils.win32_types import (
    _CREATE_SUSPENDED,
    _CREATE_BREAKAWAY_FROM_JOB,
    STARTUPINFOW,
    PROCESS_INFORMATION,
)
from backend.core.settings import get_base_path
from backend.service.utils.sandbox_process import SandboxProcess
from backend.service.utils.job_objects import WindowsJobObject, _process_in_job

logger = logging.getLogger(__name__)


def _load_era_limits(era: str) -> Tuple[int, int]:
    """Load memory_limit_mb and cpu_limit_percent for *era* from eras.yaml.

    Returns:
        (memory_limit_mb, cpu_limit_percent)

    Raises:
        FileNotFoundError: If eras.yaml is missing.
        RuntimeError: If parsing fails, the era is unknown, or either
            required field is absent.
    """
    _eras_yaml = get_base_path() / "config" / "eras.yaml"
    try:
        with _eras_yaml.open('r') as f:
            eras_config = yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"eras.yaml not found at {_eras_yaml}")
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
            logger.debug(
                "Windows 11 job pre-assignment detected, relaunching with breakaway"
            )
            try:
                process.kill()
                process.wait()
            except Exception as exc:
                logger.error("kill failed for pid=%s during breakaway pre-check teardown: %s", process.pid, exc)
            process = _launch_process(
                executable_path, args, base_flags | _CREATE_BREAKAWAY_FROM_JOB
            )

    except Exception as e:
        cleanup_errors = []
        if process:
            try:
                process.kill()
                process.wait()
            except Exception as exc:
                logger.error("kill failed for pid=%s during phase 1 cleanup: %s", process.pid, exc)
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
            except Exception as exc2:
                logger.error("kill failed for pid=%s during job assignment cleanup: %s", process.pid, exc2)
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
        except Exception as exc:
            logger.error("kill failed for pid=%s during breakaway retry teardown: %s", process.pid, exc)
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
            except Exception as exc4:
                logger.error("kill failed for pid=%s during post-breakaway assignment cleanup: %s", process.pid, exc4)
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
        except Exception as kill_exc:
            logger.error("kill failed for pid=%s during resume failure cleanup: %s", process.pid, kill_exc)
        try:
            job_object.terminate_all()
        except Exception:
            pass
        raise RuntimeError(f"Failed to resume suspended process: {exc}")

    # pi.hThread was closed inside resume(). pi.hProcess is kept open so that
    # SandboxProcess.poll() can call GetExitCodeProcess to detect exit.
    # _close_handles() (called from poll() on exit) closes it exactly once.
    return (process, job_object)
