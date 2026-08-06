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
    SandboxConfig, BrokerFile,
    SandboxEvent, SandboxPayload,
    SandboxError, SandboxStage,
)

config = SandboxConfig(
    moniker="myapp.worker",       # stable identifier — reused across launches
    exe_path="C:/apps/worker.exe",
    args=["--headless"],
    working_dir="C:/data/jobs",
    broker_files=[
        BrokerFile(path="C:/data/jobs", access="rw", mode="grant"),
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

## Broker files

`broker_files` is how the sandboxed process is given access to anything outside the
AppContainer's own storage. Each `BrokerFile` has three fields, all required:

| Field    | Values                              | Meaning                                                                    |
| -------- | ----------------------------------- | -------------------------------------------------------------------------- |
| `path`   | absolute path                       | The file or directory to broker.                                            |
| `access` | `"r"`, `"rw"`, `"x"`                | Read, read/write, or traverse-only (`FILE_TRAVERSE | FILE_READ_ATTRIBUTES`). |
| `mode`   | `"grant"`, `"secure"`, `"inherit"`  | How access is handed over. See below.                                       |

- **`grant`** applies an inheritable ACE for the container SID to a directory and
  propagates it across the existing tree, so files already present are covered as
  well as files created later.
- **`secure`** applies a single non-inheriting ACE to one existing file. Use this
  when only one specific file should be reachable, not its whole directory.
- **`inherit`** opens the file in the host and passes the inheritable handle to the
  child instead of touching any ACL. The handle value is exposed to the child in the
  environment variable `SANDBOX_HANDLE_<i>`, where `<i>` is the entry's index in
  `broker_files`. The target executable has to know to read it.

Every entry is mandatory: if any grant fails, the launch aborts with a
`SandboxError` at the `DACL_GRANT` stage rather than starting a process that cannot
reach its own data.

## Configuration reference

| Field             | Default  | Notes                                                                  |
| ----------------- | -------- | ---------------------------------------------------------------------- |
| `moniker`         | required | AppContainer profile name. Stable per process role.                    |
| `exe_path`        | required | Absolute path to the target executable.                                |
| `args`            | `[]`     | Command-line arguments.                                                |
| `working_dir`     | `None`   | Working directory. `None` inherits from parent process.                |
| `broker_files`    | `[]`     | `BrokerFile(path, access, mode)` entries. See Broker files below.      |
| `breakaway`       | `False`  | `True` adds `CREATE_BREAKAWAY_FROM_JOB` so the target escapes the host's own job before being assigned to its sandbox job. The host retries with this set automatically when job assignment fails with `ERROR_ACCESS_DENIED`. |
| `cpu_max_rate`    | `50`     | Max CPU rate, percent (1–100). Applied via `MIN_MAX_RATE`.             |
| `cpu_min_rate`    | `5`      | Floor CPU rate. Prevents audio starvation under sustained load.        |
| `skip_cpu_limit`  | `False`  | `True` leaves CPU rate control off entirely. `cpu_max_rate`/`cpu_min_rate` stay populated and validated either way; the flag governs application, not validity.     |
| `memory_limit_mb` | `None`   | `None` disables the cap. See Known Constraints.                        |

## Dependencies

- **GCC (MSYS2 UCRT64)**: `pacman -S mingw-w64-ucrt-x86_64-gcc`
- **json_parse.h**: bundled single-header JSON parser; no external dependencies

## Known constraints

- **Windows only.** The host process uses Win32 AppContainer and Job Object APIs.
  The Python wrapper calls `ctypes.windll` at runtime and will fail on non-Windows hosts.
- **DACL grants are permanent on the path.** The `grant` and `secure` broker modes
  modify the filesystem ACL and do not revert on process exit. `grant` additionally
  propagates its ACE across the existing tree under `path`. Broker only what the
  sandboxed process requires, and prefer `secure` or `inherit` over `grant` when a
  single file is enough.
- **Container profiles are never deleted automatically.** A profile provisioned for a
  moniker persists across launches and reboots by design. Call `reset_container` to
  remove one. Per-moniker ACEs granted to a deleted profile's SID are not cleaned up.
- **Qt platform plugin fails under memory caps.** Processes that use the Qt platform
  plugin allocate a large heap at startup and abort if the Job Object memory limit is
  hit before the window appears. Pass `memory_limit_mb=None` for these processes; the
  Job Object is still created and CPU limits still apply.
