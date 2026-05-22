from __future__ import annotations

import asyncio
import json
import os
import subprocess
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from backend.service.utils.sandbox.sandbox_config import DaclGrant, SandboxConfig
from backend.service.utils.sandbox.sandbox_error import SandboxError
from backend.service.utils.sandbox.sandbox_event import (
    SandboxEvent,
    SandboxPayload,
    SandboxStage,
)

EXE_NAME: str = "sandbox_host.exe"

def _exe() -> Path:
    p = Path(__file__).parent / EXE_NAME
    if not p.exists():
        raise RuntimeError(
            f"{EXE_NAME} not found at {p}. Run build.sh to compile it."
        )
    return p

_ACCESS_MASK: dict[str, int] = {
    "r":  0x00120089,  # GENERIC_READ
    "rx": 0x001200A9,  # GENERIC_READ | GENERIC_EXECUTE
    "rw": 0x001201FF,  # GENERIC_READ | GENERIC_WRITE
}


def _build_stdin_payload(config: SandboxConfig) -> dict:
    dacl_grants = []
    for grant in config.dacl_grants:
        dacl_grants.append({
            "path": grant.path,
            "access_mask": _ACCESS_MASK[grant.access],
        })

    return {
        "moniker": config.moniker,
        "exe_path": config.exe_path,
        "args": config.args,
        "working_dir": config.working_dir or "",
        "dacl_grants": dacl_grants,
        "job_config": {
            "cpu_max_rate": config.cpu_max_rate,
            "cpu_min_rate": config.cpu_min_rate,
            "memory_limit_mb": config.memory_limit_mb or 0,
            "skip_memory_limit": config.memory_limit_mb is None,
        },
        "parent_pid": os.getpid(),
    }


def _validate(config: SandboxConfig) -> None:
    errors: list[str] = []

    if not config.moniker:
        errors.append("moniker must not be empty")
    if not config.exe_path:
        errors.append("exe_path must not be empty")
    if not Path(config.exe_path).is_file():
        errors.append(f"exe_path does not exist: {config.exe_path}")
    if not (1 <= config.cpu_max_rate <= 100):
        errors.append("cpu_max_rate must be 1–100")
    if not (1 <= config.cpu_min_rate <= 100):
        errors.append("cpu_min_rate must be 1–100")
    if config.cpu_min_rate > config.cpu_max_rate:
        errors.append("cpu_min_rate must not exceed cpu_max_rate")
    if config.memory_limit_mb is not None and config.memory_limit_mb <= 0:
        errors.append("memory_limit_mb must be a positive integer or None")
    for grant in config.dacl_grants:
        if grant.access not in ("r", "rx", "rw"):
            errors.append(f"invalid access '{grant.access}' for path {grant.path!r}")

    if errors:
        raise SandboxError(
            message="; ".join(errors),
            stage=SandboxStage.CONFIG_VALIDATION,
            suggestions=["Check SandboxConfig fields before calling launch()"],
        )


@dataclass(frozen=True)
class SandboxHandle:
    moniker: str
    container_sid: str
    pid: int
    _callbacks: dict[SandboxEvent, list[Callable[[SandboxPayload], None]]] = field(
        default_factory=lambda: defaultdict(list),
        compare=False,
        hash=False,
    )
    _proc: subprocess.Popen = field(compare=False, hash=False, repr=False,
                                    default=None)  # type: ignore[assignment]

    def on(
        self,
        event: SandboxEvent,
        callback: Callable[[SandboxPayload], None],
    ) -> None:
        self._callbacks[event].append(callback)

    async def terminate(self) -> None:
        loop = asyncio.get_event_loop()
        cleanup_future: asyncio.Future[None] = loop.create_future()

        def _on_cleaned_up(payload: SandboxPayload) -> None:
            if not cleanup_future.done():
                loop.call_soon_threadsafe(cleanup_future.set_result, None)

        self.on(SandboxEvent.CLEANED_UP, _on_cleaned_up)

        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

        await cleanup_future


async def _watch_event(
    event_name: str,
    handle: SandboxHandle,
    proc: subprocess.Popen,
) -> None:
    import ctypes
    import ctypes.wintypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    SYNCHRONIZE = 0x00100000
    EVENT_MODIFY_STATE = 0x0002
    INFINITE = 0xFFFFFFFF
    WAIT_OBJECT_0 = 0x00000000
    WAIT_TIMEOUT = 0x00000102

    h_event = kernel32.OpenEventW(
        SYNCHRONIZE | EVENT_MODIFY_STATE,
        False,
        event_name,
    )
    if not h_event:
        _fire(handle, SandboxEvent.ERROR, SandboxPayload(
            event=SandboxEvent.ERROR,
            moniker=handle.moniker,
            pid=handle.pid,
            exit_code=None,
            error=f"OpenEventW failed for {event_name}: {ctypes.GetLastError()}",
            stage=SandboxStage.WATCHDOG,
        ))
        return

    loop = asyncio.get_event_loop()

    try:
        while True:
            result = await loop.run_in_executor(
                None,
                lambda: kernel32.WaitForSingleObject(h_event, 500),
            )
            if result == WAIT_OBJECT_0:
                break
            if result != WAIT_TIMEOUT:
                break

        rc = proc.wait()

        payload_exited = SandboxPayload(
            event=SandboxEvent.EXITED,
            moniker=handle.moniker,
            pid=handle.pid,
            exit_code=rc,
            error=None,
            stage=None,
        )
        _fire(handle, SandboxEvent.EXITED, payload_exited)

        payload_cleaned = SandboxPayload(
            event=SandboxEvent.CLEANED_UP,
            moniker=handle.moniker,
            pid=handle.pid,
            exit_code=rc,
            error=None,
            stage=SandboxStage.CLEANUP,
        )
        _fire(handle, SandboxEvent.CLEANED_UP, payload_cleaned)

    finally:
        kernel32.CloseHandle(h_event)


def _fire(
    handle: SandboxHandle,
    event: SandboxEvent,
    payload: SandboxPayload,
) -> None:
    for cb in handle._callbacks.get(event, []):
        try:
            cb(payload)
        except Exception:
            pass


def launch(config: SandboxConfig) -> SandboxHandle:
    _validate(config)

    stdin_data = json.dumps(_build_stdin_payload(config)).encode()

    try:
        proc = subprocess.Popen(
            [str(_exe())],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise SandboxError(
            message=f"Failed to spawn peach_sandbox.exe: {exc}",
            stage=SandboxStage.PROCESS_CREATE,
            suggestions=["Ensure peach_sandbox.exe is built and accessible"],
        ) from exc

    try:
        proc.stdin.write(stdin_data)
        proc.stdin.flush()
        proc.stdin.close()
    except OSError as exc:
        proc.kill()
        raise SandboxError(
            message=f"Failed to write to peach_sandbox.exe stdin: {exc}",
            stage=SandboxStage.PROCESS_CREATE,
            suggestions=[],
        ) from exc

    _timed_out = threading.Event()

    def _kill_on_timeout() -> None:
        _timed_out.set()
        proc.kill()

    _timer = threading.Timer(15.0, _kill_on_timeout)
    _timer.start()
    try:
        stdout_line = proc.stdout.readline()
    except OSError as exc:
        raise SandboxError(
            message=f"Communication with peach_sandbox.exe failed: {exc}",
            stage=SandboxStage.PROCESS_CREATE,
            suggestions=[],
        ) from exc
    finally:
        _timer.cancel()

    if _timed_out.is_set():
        raise SandboxError(
            message="peach_sandbox.exe did not respond within 15 seconds",
            stage=SandboxStage.PROCESS_CREATE,
            suggestions=["Check for AppContainer provisioning delays or permission issues"],
        )

    if not stdout_line:
        proc.kill()
        raise SandboxError(
            message="peach_sandbox.exe produced no output",
            stage=SandboxStage.PROCESS_CREATE,
            suggestions=["Run peach_sandbox.exe manually to debug startup"],
        )

    first_line = stdout_line.strip()
    try:
        response = json.loads(first_line)
    except json.JSONDecodeError as exc:
        raise SandboxError(
            message=f"Invalid JSON from peach_sandbox.exe: {exc}",
            stage=SandboxStage.PROCESS_CREATE,
            suggestions=[],
        ) from exc

    required = {"sid", "pid", "event_name", "stage"}
    missing = required - response.keys()
    if missing:
        raise SandboxError(
            message=f"peach_sandbox.exe response missing fields: {missing}",
            stage=SandboxStage.PROCESS_CREATE,
            suggestions=[],
        )

    if response.get("stage") == "error":
        raise SandboxError(
            message=response.get("error", "Unknown error from peach_sandbox.exe"),
            stage=SandboxStage[response.get("error_stage", "PROCESS_CREATE").upper()],
            suggestions=response.get("suggestions", []),
            disable_sandbox=response.get("disable_sandbox", False),
        )

    handle = SandboxHandle(
        moniker=config.moniker,
        container_sid=response["sid"],
        pid=response["pid"],
        _callbacks=defaultdict(list),
        _proc=proc,
    )

    started_payload = SandboxPayload(
        event=SandboxEvent.STARTED,
        moniker=config.moniker,
        pid=response["pid"],
        exit_code=None,
        error=None,
        stage=None,
    )
    _fire(handle, SandboxEvent.STARTED, started_payload)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _run_watcher() -> None:
        try:
            loop.run_until_complete(
                _watch_event(response["event_name"], handle, proc)
            )
        finally:
            loop.close()

    threading.Thread(target=_run_watcher, daemon=True).start()

    return handle


def reset_container(moniker: str) -> None:
    if not moniker:
        raise SandboxError(
            message="moniker must not be empty",
            stage=SandboxStage.CONTAINER_PROVISION,
            suggestions=["Pass the emulator moniker string, e.g. 'Peach1UP.dosbox'"],
        )

    try:
        proc = subprocess.run(
            [str(_exe()), "--reset", moniker],
            capture_output=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        raise SandboxError(
            message=f"reset_container timed out for moniker '{moniker}'",
            stage=SandboxStage.CONTAINER_PROVISION,
            suggestions=["Check if AppContainer delete is stuck"],
        )
    except OSError as exc:
        raise SandboxError(
            message=f"Failed to invoke peach_sandbox.exe --reset: {exc}",
            stage=SandboxStage.CONTAINER_PROVISION,
            suggestions=[],
        ) from exc

    if proc.returncode != 0:
        stderr_text = proc.stderr.decode(errors="replace").strip()
        raise SandboxError(
            message=f"reset_container failed for '{moniker}': {stderr_text}",
            stage=SandboxStage.CONTAINER_PROVISION,
            suggestions=["Moniker may not exist; this is safe to ignore on first run"],
        )
