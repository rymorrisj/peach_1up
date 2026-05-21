from __future__ import annotations

import asyncio
from pathlib import Path

import backend.service.utils.sandbox as _sandbox_pkg
from backend.service.utils.sandbox import SandboxConfig, SandboxError, launch
from backend.service.utils.sandbox_checker.results import CheckResult, CheckStatus

_SRC = Path(__file__).parent / "src"

# (name, exe_name, pass_message, affects)
_CHECKS: list[tuple[str, str, str, list[str]]] = [
    (
        "sdl2_d3d11",
        "test_sdl2_d3d11.exe",
        "SDL2 init, WASAPI audio, and D3D11 hardware device all accessible in AppContainer",
        ["dosbox", "pcsx2", "duckstation"],
    ),
    (
        "sdl2_opengl",
        "test_sdl2_opengl.exe",
        "OpenGL 4.5 core context created via WGL inside AppContainer",
        ["dosbox", "mame", "mupen64plus", "retroarch"],
    ),
    (
        "qt_qpa",
        "test_qt_qpa.exe",
        "Qt 5.15 QPA platform plugin loaded and window displayed inside AppContainer",
        ["pcsx2", "rpcs3", "dolphin"],
    ),
]


async def _async_run_one(
    name: str,
    config: SandboxConfig,
    pass_message: str,
    affects: list[str],
) -> CheckResult:
    try:
        handle = launch(config)
    except SandboxError as exc:
        return CheckResult(
            name=name,
            status=CheckStatus.FAIL,
            message=str(exc),
            affects=affects,
        )
    except Exception as exc:
        return CheckResult(
            name=name,
            status=CheckStatus.FAIL,
            message=f"unexpected error launching check: {exc}",
            affects=affects,
        )

    exit_code = handle._proc.returncode
    if exit_code == 0:
        return CheckResult(
            name=name,
            status=CheckStatus.PASS,
            message=pass_message,
            affects=affects,
        )
    return CheckResult(
        name=name,
        status=CheckStatus.FAIL,
        message=(
            f"test exited with code {exit_code} — "
            "AppContainer may be blocking a required API; "
            "disable sandbox for affected emulators"
        ),
        affects=affects,
    )


def _run_one(
    name: str,
    exe_name: str,
    pass_message: str,
    affects: list[str],
) -> CheckResult:
    exe = _SRC / exe_name
    if not exe.exists():
        return CheckResult(
            name=name,
            status=CheckStatus.SKIP,
            message="not built — run build_tests.sh",
            affects=affects,
        )

    config = SandboxConfig(
        moniker=f"Peach1UP.checker.{name}",
        exe_path=str(exe),
        cpu_max_rate=50,
        cpu_min_rate=5,
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_async_run_one(name, config, pass_message, affects))
    finally:
        loop.close()


def run_checks() -> list[CheckResult]:
    # sandbox_host.exe must be built alongside sandbox/ before calling run_checks().
    _sandbox_pkg.EXE_NAME = "sandbox_host.exe"

    results: list[CheckResult] = []
    for name, exe_name, pass_message, affects in _CHECKS:
        results.append(_run_one(name, exe_name, pass_message, affects))
    return results
