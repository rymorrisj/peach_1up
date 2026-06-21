# sandbox

Self-contained Windows process sandbox. Launches an executable inside an AppContainer
with a Job Object for CPU and memory limits. Implemented as a C++ host process
(`sandbox_host.exe` by default) with a thin Python wrapper.

## Design rationale

**AppContainer over a dedicated low-privilege account**

Running a process under a separate Windows account loses the launching user's audio
session, GPU adapter selection, and desktop window station access — all three fail
silently. AppContainer confines the process to a derived SID without changing identity,
so those subsystems continue to work.

**AppContainer over Job Objects alone**

Job Objects provide resource limits (CPU rate, memory cap, kill-on-close). They add
no security containment. AppContainer adds filesystem, network, and inter-process
isolation on top of those limits.

**Regular AppContainer, not LPAC**

Less Privileged AppContainer (LPAC) removes `ALL APPLICATION PACKAGES` from the
token. This breaks OpenGL ICD loading from DriverStore and reproduces the same silent
failures as the low-privilege account approach. Regular AppContainer is used instead.

## Building

Requires GCC from MSYS2 UCRT64:

```sh
pacman -S mingw-w64-ucrt-x86_64-gcc
```

From an MSYS2 UCRT64 terminal, run `build.sh` from the package directory:

```sh
bash build.sh
```

Outputs `sandbox_host.exe` into the package directory. To use a different name:

```sh
OUT_NAME=myhost.exe bash build.sh
```

## Usage

```python
import sandbox

# Override the host executable name before the first call to launch().
# Default is "sandbox_host.exe", located next to this package's __init__.py.
sandbox.EXE_NAME = "myhost.exe"

from sandbox import (
    launch, reset_container,
    SandboxConfig, DaclGrant,
    SandboxEvent, SandboxPayload,
    SandboxError, SandboxStage,
)

config = SandboxConfig(
    moniker="myapp.worker",       # stable identifier — reused across launches
    exe_path="C:/apps/worker.exe",
    args=["--headless"],
    working_dir="C:/data/jobs",
    dacl_grants=[
        DaclGrant(path="C:/data/jobs", access="rw"),
    ],
    cpu_max_rate=60,
    cpu_min_rate=5,
    memory_limit_mb=512,
)

handle = launch(config)   # synchronous; raises SandboxError on failure

handle.on(SandboxEvent.EXITED, lambda p: print(f"exited: {p.exit_code}"))
handle.on(SandboxEvent.ERROR,  lambda p: print(f"error: {p.error}"))

# Terminate and wait for cleanup:
await handle.terminate()  # resolves when CLEANED_UP fires
```

`launch()` returns a `SandboxHandle` after the child process starts. Callbacks are
fired from an asyncio task — call `launch()` from within a running event loop, or
register callbacks on the returned handle at any point before the event fires.

To delete a container profile (e.g. after a corrupted session):

```python
reset_container("myapp.worker")
```

## Moniker

The `moniker` field in `SandboxConfig` names the AppContainer profile. It must be
stable across launches for the same logical process, the profile is created once and
reused. There is no required prefix or format; any non-empty string is valid. Choose
something that uniquely identifies the process role within your application.

If left unset the default is `""`, which will raise a `SandboxError` at
`CONFIG_VALIDATION` stage: moniker is required.

## Configuration reference

| Field             | Default  | Notes                                                                  |
| ----------------- | -------- | ---------------------------------------------------------------------- |
| `moniker`         | required | AppContainer profile name. Stable per process role.                    |
| `exe_path`        | required | Absolute path to the target executable.                                |
| `args`            | `[]`     | Command-line arguments.                                                |
| `working_dir`     | `None`   | Working directory. `None` inherits from parent process.                |
| `dacl_grants`     | `[]`     | `DaclGrant(path, access)` entries. `access`: `"r"`, `"rx"`, or `"rw"`. |
| `cpu_max_rate`    | `50`     | Max CPU rate, percent (1–100). Applied via `MIN_MAX_RATE`.             |
| `cpu_min_rate`    | `5`      | Floor CPU rate. Prevents audio starvation under sustained load.        |
| `memory_limit_mb` | `None`   | `None` disables the cap. See Known Constraints.                        |

## Dependencies

- **GCC (MSYS2 UCRT64)**: `pacman -S mingw-w64-ucrt-x86_64-gcc`
- **json_parse.h**: bundled single-header JSON parser; no external dependencies

## Known constraints

- **Windows only.** The host process uses Win32 AppContainer and Job Object APIs.
  The Python wrapper calls `ctypes.windll` at runtime and will fail on non-Windows hosts.
- **DACL grants are permanent on the path.** `grant_path` modifies the filesystem ACL
  and does not revert on process exit. Grant only what the sandboxed process requires.
- **Qt platform plugin fails under memory caps.** Processes that use the Qt platform
  plugin allocate a large heap at startup and abort if the Job Object memory limit is
  hit before the window appears. Pass `memory_limit_mb=None` for these processes; the
  Job Object is still created and CPU limits still apply.
