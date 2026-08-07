"""
Emulator launch orchestration for Peach 1UP.

Provides the public entry point ``launch_under_job_object``, which resolves
per-launch resource limits from eras.yaml and the emulator catalog, then
delegates to sandbox/process.py for the actual launch and Job Object
lifecycle:

  * ``launch_suspended`` starts the emulator suspended, natively or inside an
    AppContainer.
  * ``run_under_job`` creates the Job Object, applies limits (or not, for
    container launches, see its docstring), assigns the process (retrying
    with CREATE_BREAKAWAY_FROM_JOB if needed), and resumes it.

If Job Object assignment fails the process is terminated and the launch is
aborted, there is no unsandboxed fallback.
"""

import subprocess
import yaml
from pathlib import Path

from backend.core.logger import get_logger
from backend.core.settings import get_base_path
from backend.service.utils.eras_config import get_eras, get_cpu_min_rate
from sandbox.sandbox_config import SandboxConfig
from sandbox.sandbox_process import SandboxProcess
from sandbox.job import WindowsJobObject
from sandbox.process import launch_suspended, run_under_job
from backend.service.utils.emulator_catalog import get_skip_memory_limit, get_skip_cpu_limit

logger = get_logger(__name__)

_ERAS_YAML: Path = get_base_path() / "config" / "eras.yaml"


def _load_era_limits(era: str) -> tuple[int, int]:
    """Load memory_limit_mb and cpu_limit_percent for *era* from eras.yaml."""
    try:
        eras_config = get_eras()
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


def launch_under_job_object(
    executable_path: str,
    args: list[str],
    era: str,
    job_name_prefix: str,
    slug: str = "",
    cwd: str | None = None,
    container_enabled: bool = False,
    sandbox_config: SandboxConfig | None = None,
) -> tuple[SandboxProcess, "WindowsJobObject"]:
    """Launch an emulator under the current user account in a Windows Job Object.

    The Job Object name is ``job_name_prefix`` plus the launched process's PID,
    so the name can only be finalized once the process exists, the process is
    therefore launched first and the Job Object is created and configured
    second, immediately before assignment. The PID makes the name unique per
    launch (OS-guaranteed for live processes); the alternative of naming the
    job before the process exists has no such guarantee and risks
    CreateJobObjectW silently handing back a handle to a same-named job from
    an unrelated launch.
    """
    if container_enabled and sandbox_config is None:
        raise RuntimeError(
            "container_enabled is True but sandbox_config is None, "
            "pass a SandboxConfig to launch_under_job_object."
        )

    base_flags = subprocess.CREATE_NEW_PROCESS_GROUP

    memory_limit_mb, cpu_limit_percent = _load_era_limits(era)
    skip_cpu_limit = get_skip_cpu_limit(slug)
    skip_memory_limit = get_skip_memory_limit(slug)
    cpu_min_rate_percent = get_cpu_min_rate(era)

    if container_enabled:
        # sandbox_host.exe applies these via its own Job Object
        # (main.cpp/job.cpp) before the emulator ever runs, the resolved
        # era numbers must reach it through sandbox_config, otherwise it
        # silently falls back to SandboxConfig's inert defaults (50% CPU, no
        # memory cap). run_under_job is called below with
        # apply_limits=False for this reason: the Python-side Job Object
        # created there exists only as the teardown handle and for
        # launch-history reporting (coordinator.py), not as an enforcer.
        sandbox_config.cpu_max_rate = cpu_limit_percent
        sandbox_config.cpu_min_rate = cpu_min_rate_percent
        sandbox_config.skip_cpu_limit = skip_cpu_limit
        sandbox_config.memory_limit_mb = None if skip_memory_limit else memory_limit_mb

    process = launch_suspended(
        executable_path, args, base_flags, cwd,
        sandbox_config if container_enabled else None,
    )

    job_name = f"{job_name_prefix}_{process.pid}"

    return run_under_job(
        executable_path, args, base_flags, cwd,
        process, job_name,
        memory_limit_mb, cpu_limit_percent,
        apply_limits=not container_enabled,
        cpu_min_rate_percent=cpu_min_rate_percent,
        skip_cpu_limit=skip_cpu_limit,
        skip_memory_limit=skip_memory_limit,
        sandbox_config=sandbox_config if container_enabled else None,
    )
