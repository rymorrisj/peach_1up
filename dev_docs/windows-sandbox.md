# Windows Sandbox

Every emulator launch is wrapped in a Windows
[Job Object](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects), with
[AppContainer](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation)
layered on top where the emulator supports it.

Related: [SECURITY.md](SECURITY.md) (policy rules) · [CHANGELOG.md](../CHANGELOG.md)
(decision history).

## What the Job Object does

| Control | Effect | Waivable |
|---|---|---|
| Kill-on-close | All emulator processes in the job are terminated when the backend exits. No orphans. | No, always applied |
| CPU cap | Threads are throttled past the per-era CPU budget per scheduling interval. Applied as `MaxRate` under `JOB_OBJECT_CPU_RATE_CONTROL_MIN_MAX_RATE`. | `skip_cpu_limit` |
| Memory cap | Per-process cap so a runaway emulator cannot exhaust host RAM. Applied via `JOB_OBJECT_LIMIT_PROCESS_MEMORY`. | `skip_memory_limit` |

**No emulator waives either cap today.** Every descriptor in
[`config/emulators/`](../config/emulators/) sets both flags to `false`, so all three
controls are in force on every launch.

If the Job Object cannot be created, or the emulator cannot be assigned to it, **the
launch is aborted**. There is no fallback to an uncontained launch.

Emulators run under the current user account. A dedicated low-privilege account is not
used; that approach was tried and removed in May 2026.

**What the Job Object does not do:**

- Restrict filesystem access. The emulator can reach any path the current user can reach.
  That is AppContainer's job, not the Job Object's.
- Block network access at the OS level. Network isolation is emulator-native (see
  [SECURITY.md](SECURITY.md) § Network Rules).

## AppContainer status

| Emulator | `container_enabled` | Notes |
|---|---|---|
| DOSBox-X | true | |
| DuckStation | true | |
| Flycast | true | Its own `known_limitations` entry still claims AppContainer is disabled. That text is stale; the flag is authoritative. |
| Mesen | true | |
| PCSX2 | true | |
| Xenia | true | |
| xemu | true | Re-enabled 2026-08-11. The earlier QEMU TCG / `DeviceIoControl` diagnosis was wrong; the real cause was undersized limits colliding with xemu's pre-allocated JIT heap. |
| 86Box | false | Works in some environments and not others. Disabled by default, not hard-capped, so it can be enabled per install. Not being investigated further. |
| RPCS3 | false | JIT recompiler (Cell PPU/SPU and RSX) incompatible with AppContainer's restricted token. `container_permanently_excluded = false` in the TOML, which contradicts the `known_limitations` entry; see the open item in [CHANGELOG.md](../CHANGELOG.md). |
| Project64 | false | `container_permanently_excluded = true`. Crashes on launch under AppContainer (`Main.cpp:99`, `exit_code=1`) even with limits raised. Root cause unknown. No override can turn it on. |

Container monikers are `Peach1UP.<slug>.<scope>`, where `<scope>` is `shared` or the
decimal `user_item_id` for a per-item container. Confirmed examples:
`Peach1UP.duckstation.shared`, `Peach1UP.mesen.shared`.

## Resource caps

Per-era caps live in [`config/eras.yaml`](../config/eras.yaml):

```yaml
dos:
  memory_limit_mb: 512
  cpu_limit_percent: 50
```

| Field | Type | Sets |
|---|---|---|
| `memory_limit_mb` | integer | Per-process memory cap in MB |
| `cpu_limit_percent` | integer 1 to 100 | CPU budget as a percentage of all logical processors per scheduling interval, applied as `MaxRate` |
| `cpu_min_rate_percent` | integer, top-level, default `5` | The `MinRate` scheduling floor shared by every era |

### Current values

| Era | Memory | CPU |
|---|---|---|
| `dos` | 512 MB | 50% |
| `win95` | 2048 MB | 75% |
| `win98` | 2048 MB | 75% |
| `winxp` | 3072 MB | 80% |
| `ps1` | 1024 MB | 60% |
| `ps2` | 4096 MB | 80% |
| `ps3` | 12288 MB | 90% |
| `xbox` | 3072 MB | 75% |
| `xbox360` | 6144 MB | 75% |
| `nes` | 512 MB | 30% |
| `snes` | 768 MB | 50% |
| `n64` | 2048 MB | 60% |
| `dreamcast` | 1024 MB | 60% |

### Hardcoded ceilings

`eras.yaml` values are clamped once, at load time, in
[`eras_config.py`](../backend/service/utils/eras_config.py), so every downstream reader
sees the clamped value with no per-call-site check.

| Ceiling | Value |
|---|---|
| `cpu_limit_percent` | 90 |
| `memory_limit_mb` | 75% of real total physical RAM, queried per process via `GlobalMemoryStatusEx` |

An over-ceiling value logs a warning and uses the ceiling for that run. It never raises: a
resource-tuning mistake should degrade loudly, not take startup down. There is no
`eras.yaml` key, settings entry, or UI control for either ceiling; moving them requires a
code change.

### Adjusting caps

Edit `memory_limit_mb` or `cpu_limit_percent` for the era in
[`config/eras.yaml`](../config/eras.yaml) and restart the backend. Changes take effect on
the next launch. There is no UI or settings field for these values; hand-editing the YAML
is the only mechanism.

**CPU notes**

- The cap spreads across all logical processors. On an 8-thread machine,
  `cpu_limit_percent: 50` allows the equivalent of 4 threads of CPU time per interval.
- `MIN_MAX_RATE` needs Windows 10 1607 (build 14393) or later. Below that, and on any
  `SetInformationJobObject` failure, the wrapper falls back to
  `JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP`.
- On `MIN_MAX_RATE`, a value at or below `cpu_min_rate_percent` is clamped up to that
  floor with a warning. On the `HARD_CAP` fallback the floor is 1/10000 of a percent.
- `HARD_CAP` starves threads to zero CPU at interval end, which mutes the host WASAPI
  audio session. That is why `MIN_MAX_RATE` with a non-zero `MinRate` is the primary path.

**Memory notes**

- The cap is per-process, not per-job. Child processes each get the same cap individually.
- Setting it too low for a heavy era causes the emulator to crash or fail to load large
  games. xemu specifically needs the `xbox` cap above 2048 MB or it exits immediately with
  a paging file error.

## Launch sequence

```
launch suspended (CREATE_NEW_PROCESS_GROUP | CREATE_SUSPENDED)
  → create Job Object, named with the launched process PID for per-launch uniqueness
  → apply limits
  → AssignProcessToJobObject
  → on error 5: kill the still-suspended process, relaunch with
    CREATE_BREAKAWAY_FROM_JOB, reassign
  → ResumeThread
```

Launching suspended means the emulator cannot execute before limits are in force. A
process that fails at any step is terminated while still suspended rather than resumed.

For AppContainer-enabled emulators, process creation is delegated to `sandbox_host.exe`,
which handles `SECURITY_CAPABILITIES`,
`CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT`, and `ResumeThread`. Its own Job Object
applies the numeric limits before the process resumes, so the Python-side job is created
with `apply_limits=False` and exists only as a teardown handle and for launch-history
reporting. The resolved era numbers reach it through `SandboxConfig`; without that it
silently falls back to inert defaults (50% CPU, no memory cap).

Job Object and process lifecycle live in the vendored
[`wincage`](../services/vendor/wincage/) package (`wincage/process.py`, `wincage/job.py`,
`wincage/sandbox.py`). Peach 1UP's era-limit resolution wrapper is
[`launcher.py`](../backend/service/utils/platform/windows/process/launcher.py).

## Troubleshooting

**Emulator crashes immediately with no error**

The era memory cap is probably too low. Raise `memory_limit_mb` in `eras.yaml` and restart
the backend.

**Job Object assignment fails with error 5 on Windows 11**

Windows 11 pre-assigns new child processes to an OS-managed Job Object, and a second
assignment fails with access denied unless the process was launched with
`CREATE_BREAKAWAY_FROM_JOB`. The launcher handles this automatically via the breakaway
retry above. If the retry also fails (the process is inside a non-breakaway job set by a
third-party tool or debugger) **the launch is aborted** and the error surfaces to the user.

## DOSBox-X specifics

`write_launch_conf()` in [`dosbox.py`](../backend/service/backends/dosbox.py) builds a
complete `dosbox-x.conf` per launch: it takes
`library/system/templates/dosbox-x/base.conf`, strips any `[autoexec]` section, and
appends a generated one (drive mounts, then profile-level and item-level launch commands).
The result is written to a private per-launch directory created with
`tempfile.mkdtemp(prefix="peach1up_dosbox_")`. Environment launches use
`write_environment_launch_conf()` with prefix `peach1up_dosbox_env_`.
`_cleanup_temp_dir_on_exit()` removes the directory after the process exits.

The command line passes `-noconfig` (so DOSBox-X ignores any user config), `-conf <path>`
pointing at the generated file, and an optional `-set ne2000=false` when networking is
disabled for the profile.

Inside the generated `[autoexec]` block, paths reach `MOUNT` and `IMGMOUNT` as raw
absolute Windows paths, double-quoted only when they contain whitespace. Forward slashes
and 8.3 short-path conversion are not used: the DOSBox-X autoexec tokeniser reads a
forward slash as a DOS switch character and truncates the argument.

Before PX-2, all launches wrote their conf to one shared location, which a concurrent
second launch could overwrite mid-read. The per-launch temp directory is the fix.
