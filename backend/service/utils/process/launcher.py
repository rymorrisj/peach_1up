"""
Emulator launch orchestration for Peach 1UP.

Provides the public entry point ``launch_under_job_object`` which runs an
emulator executable under the current user account inside a Windows Job Object
with memory and CPU limits sourced from eras.yaml.

Processes are launched without CREATE_SUSPENDED and assigned to the Job Object
immediately after CreateProcessW returns.  There is a small race window between
launch and assignment; if Job Object assignment fails the process is terminated
and the launch is aborted — there is no unsandboxed fallback.
"""

import asyncio
import ctypes
import ctypes.wintypes
import os
import subprocess
import yaml
from pathlib import Path

from backend.service.utils.win32_types import (
    _CREATE_BREAKAWAY_FROM_JOB,
    STARTUPINFOW,
    PROCESS_INFORMATION,
)
from backend.core.logger import get_logger
from backend.core.settings import get_base_path
from backend.service.utils.sandbox import sandbox as _sandbox
from backend.service.utils.sandbox.sandbox_config import SandboxConfig
from backend.service.utils.sandbox.sandbox_error import SandboxError
from backend.service.utils.sandbox_process import SandboxProcess
from backend.service.utils.process.job_objects import WindowsJobObject
from backend.service.utils.emulator_catalog import get_skip_memory_limit, get_skip_cpu_limit

logger = get_logger(__name__)

_ERAS_YAML: Path = get_base_path() / "config" / "eras.yaml"


def _load_era_limits(era: str) -> tuple[int, int]:
    """Load memory_limit_mb and cpu_limit_percent for *era* from eras.yaml."""
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
    args: list[str],
    creation_flags: int,
    cwd: str | None = None,
) -> SandboxProcess:
    """Launch a process under the current user account via CreateProcessW."""
    cmd_line = subprocess.list2cmdline([executable_path] + args)
    cmd_buf = ctypes.create_unicode_buffer(cmd_line)

    cwd = cwd if cwd is not None else str(Path(executable_path).parent)

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

    proc = SandboxProcess(
        pid=pi.dwProcessId,
        process_handle=pi.hProcess,
        thread_handle=None,
        args=[executable_path] + args,
    )
    ctypes.windll.kernel32.CloseHandle(pi.hThread)
    return proc


def _launch_process_in_container(
    executable_path: str,
    args: list[str],
    creation_flags: int,
    sandbox_config: SandboxConfig,
    cwd: str | None = None,
) -> SandboxProcess:
    """Launch a process in a Windows AppContainer via the sandbox package."""
    logger.debug(
        "launch_process_in_container: exe=%s cwd=%s flags=%#x args=%s",
        executable_path, cwd, creation_flags, args,
    )

    if cwd is not None:
        sandbox_config.working_dir = cwd

    if creation_flags & _CREATE_BREAKAWAY_FROM_JOB:
        sandbox_config.breakaway = True

    sandbox_handle = _sandbox.launch(sandbox_config)

    PROCESS_ALL_ACCESS = 0x001FFFFF
    win32_handle = ctypes.windll.kernel32.OpenProcess(
        PROCESS_ALL_ACCESS, False, sandbox_handle.pid
    )
    if not win32_handle:
        error_code = ctypes.windll.kernel32.GetLastError()
        try:
            asyncio.run(sandbox_handle.terminate())
        except Exception as te:
            logger.warning(
                "Failed to terminate container pid %d during OpenProcess cleanup: %s",
                sandbox_handle.pid, te,
            )
        raise RuntimeError(
            f"OpenProcess failed for container pid {sandbox_handle.pid} "
            f"(error {error_code}) after sandbox.launch() succeeded."
        )

    return SandboxProcess(
        pid=sandbox_handle.pid,
        process_handle=win32_handle,
        thread_handle=None,
        args=[executable_path] + args,
        sandbox_handle=sandbox_handle,
    )


def launch_under_job_object(
    executable_path: str,
    args: list[str],
    era: str,
    job_name: str,
    slug: str = "",
    cwd: str | None = None,
    container_enabled: bool = False,
    sandbox_config: SandboxConfig | None = None,
) -> tuple[SandboxProcess, "WindowsJobObject"]:
    """Launch an emulator under the current user account in a Windows Job Object."""
    if container_enabled and sandbox_config is None:
        raise RuntimeError(
            "container_enabled is True but sandbox_config is None — "
            "pass a SandboxConfig to launch_under_job_object."
        )

    job_object = None
    process = None
    base_flags = None

    try:
        memory_limit_mb, cpu_limit_percent = _load_era_limits(era)

        job_object = WindowsJobObject(job_name, memory_limit_mb, cpu_limit_percent)
        job_object.create()

        if not get_skip_cpu_limit(slug):
            job_object.set_cpu_limit(job_object.cpu_limit_percent)

        if get_skip_memory_limit(slug):
            job_object.set_kill_on_close()
        else:
            job_object.set_memory_limit(job_object.memory_limit_mb)

        base_flags = subprocess.CREATE_NEW_PROCESS_GROUP

        if container_enabled:
            process = _launch_process_in_container(
                executable_path, args, base_flags, sandbox_config, cwd=cwd
            )
        else:
            process = _launch_process(executable_path, args, base_flags, cwd=cwd)

    except SandboxError:
        if job_object:
            try:
                job_object.teardown()
            except Exception:
                pass
        raise
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
                job_object.teardown()
            except Exception as ce:
                cleanup_errors.append(str(ce))
        msg = f"Failed to launch {executable_path} under job object: {str(e)}"
        if cleanup_errors:
            msg += f" (Cleanup errors: {'; '.join(cleanup_errors)})"
        raise RuntimeError(msg)

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
                job_object.teardown()
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
            if container_enabled:
                process = _launch_process_in_container(
                    executable_path, args,
                    base_flags | _CREATE_BREAKAWAY_FROM_JOB,
                    sandbox_config, cwd=cwd
                )
            else:
                process = _launch_process(
                    executable_path, args, base_flags | _CREATE_BREAKAWAY_FROM_JOB, cwd=cwd
                )
        except SandboxError:
            try:
                job_object.teardown()
            except Exception:
                pass
            raise
        except Exception as exc2:
            try:
                job_object.teardown()
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
                job_object.teardown()
            except Exception:
                pass
            raise RuntimeError(
                f"Failed to assign breakaway process to job object: {exc3}"
            )

    # pi.hThread was closed in _launch_process immediately after process creation.
    # pi.hProcess is kept open so SandboxProcess.poll() can call GetExitCodeProcess.
    # _close_handles() (called from poll() on exit) closes it exactly once.
    return (process, job_object)
