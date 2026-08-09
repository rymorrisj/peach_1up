# Windows Sandbox

Peach 1UP wraps each emulator launch in a Windows [Job Object](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
with per-era CPU and memory limits available. This page explains what the Job Object
does and how to adjust the resource caps.

Related: [SECURITY.md](SECURITY.md) for policy rules, [DECISIONS.md](DECISIONS.md) for
the decision log.

---

## What the Job Object does

Every emulator launched on Windows is placed inside a Job Object before it runs. The
Job Object supports:

| Limit         | Effect                                                                                                                                    |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Kill-on-close | When the Peach 1UP backend exits, all emulator processes in the job are terminated automatically. No orphaned processes. Always applied.   |
| CPU cap       | Threads are throttled when the emulator exceeds its per-era CPU budget per scheduling interval. Waived per emulator via `skip_cpu_limit`.  |
| Memory cap    | Per-process memory is capped so a runaway emulator cannot exhaust host RAM. Waived per emulator via `skip_memory_limit`.                   |

> **Every emulator descriptor in [`config/emulators/`](../config/emulators/) currently
> sets both `skip_memory_limit = true` and `skip_cpu_limit = true`.** Kill-on-close is
> therefore the only Job Object control actually in force today. The per-era numbers
> below are the values that would apply if a descriptor re-enabled either cap; they are
> not being enforced as shipped. See the `skip_cpu_limit` and Qt-memory-cap entries in
> [SECURITY.md](SECURITY.md) for why each was waived.

If the Job Object cannot be created or the emulator cannot be assigned to it, **the
launch is aborted**. There is no fallback to an uncontained launch.

Emulators run under the current user account. A dedicated low-privilege user account is
not used. [AppContainer](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation)
isolation is an additional layer applied on top of Job Objects when
`container_enabled = true` in the emulator descriptor. Seven emulators have it enabled
(DOSBox-X, DuckStation, Flycast, Mesen, PCSX2, Project64, Xenia). 86Box, RPCS3, and xemu
remain Job-Object-only; RPCS3 and xemu are additionally marked
`container_permanently_excluded`, so a profile-level override cannot turn AppContainer on
for them. See [SECURITY.md](SECURITY.md) § Windows-specific process rules for the reasons.

**What the Job Object does not do:**

- It does not restrict filesystem access. The emulator can reach any path the current
  user can reach.
- It does not apply AppContainer-level isolation or filesystem virtualisation.
- It does not block all network access at the OS level. Network isolation is handled by
  disabling the emulated network adapter inside each emulator (see the network section
  in [SECURITY.md](SECURITY.md)).
- It does not apply on Linux. Linux support is out of scope ([DECISIONS.md](DECISIONS.md)
  2026-07-17).

---

## Resource caps and eras.yaml

CPU and memory limits for each emulator era are defined in
[`config/eras.yaml`](../config/eras.yaml). Each era entry has two fields that control the
Job Object:

```yaml
dos:
  memory_limit_mb: 512
  cpu_limit_percent: 50
```

| Field               | Type            | What it sets                                                                                                                                          |
| ------------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `memory_limit_mb`   | integer         | Per-process memory cap in megabytes. Applied via `JOB_OBJECT_LIMIT_PROCESS_MEMORY`.                                                                     |
| `cpu_limit_percent` | integer (1–100) | CPU budget as a percentage of all logical processors across a scheduling interval. Applied as `MaxRate` under `JOB_OBJECT_CPU_RATE_CONTROL_MIN_MAX_RATE`. |

A third top-level key, `cpu_min_rate_percent` (default `5`), sets the `MinRate`
scheduling floor shared by every era.

### Current defaults

| Era        | eras.yaml key | Memory cap | CPU cap |
| ---------- | ------------- | ---------- | ------- |
| DOS        | `dos`         | 512 MB     | 50%     |
| Windows 95 | `win95`       | 2048 MB    | 75%     |
| Windows 98 | `win98`       | 2048 MB    | 75%     |
| Windows XP | `winxp`       | 3072 MB    | 80%     |
| PS1        | `ps1`         | 1024 MB    | 60%     |
| PS2        | `ps2`         | 4096 MB    | 80%     |
| PS3        | `ps3`         | 12288 MB   | 90%     |
| Xbox OG    | `xbox`        | 3072 MB    | 75%     |
| Xbox 360   | `xbox360`     | 6144 MB    | 75%     |
| Dreamcast  | `dreamcast`   | 1024 MB    | 60%     |
| NES        | `nes`         | 512 MB     | 30%     |
| SNES       | `snes`        | 256 MB     | 50%     |
| N64        | `n64`         | 1024 MB    | 60%     |

### How to adjust caps

Open [`config/eras.yaml`](../config/eras.yaml) in any text editor and change
`memory_limit_mb` or `cpu_limit_percent` for the era you want to adjust. Restart the
backend; changes take effect on the next launch. Because every descriptor currently
waives both caps, an era edit has no effect until `skip_cpu_limit` or
`skip_memory_limit` is also cleared for the emulator in question.

**CPU cap notes:**

- `cpu_limit_percent: 100` gives the job unrestricted CPU access across all logical
  processors. This removes throttling but does not disable kill-on-close or memory
  limits.
- The cap is spread across all logical processors. On an 8-thread machine,
  `cpu_limit_percent: 50` allows the equivalent of 4 threads' worth of CPU time per
  scheduling interval.
- `MIN_MAX_RATE` rate control requires Windows 10 1607 (build 14393) or later. Below
  that build, and on a `SetInformationJobObject` failure, the Job Object wrapper falls
  back to `JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP`.
- On the `MIN_MAX_RATE` path a value at or below `cpu_min_rate_percent` is clamped up to
  that floor and a warning is logged. On the `HARD_CAP` fallback the floor is 1/10000 of
  a percent instead.

**Memory cap notes:**

- The cap is per-process, not per-job. Child processes spawned by the emulator each have
  the same cap applied individually.
- Setting the cap too low for a resource-intensive era (e.g. PS2 or Xbox) will cause the
  emulator to crash or fail to load large games. Raise the cap if you see out-of-memory
  errors.

---

## Troubleshooting

**Emulator crashes immediately with no error**

The memory cap for the era may be too low. Raise `memory_limit_mb` in
[`config/eras.yaml`](../config/eras.yaml) for the affected era and restart the backend.

**Job Object assignment fails on Windows 11 (nested job retry)**

Windows 11 pre-assigns new child processes to an OS-managed Job Object. Attempting to
assign such a process to a second Job Object fails with error code 5 (access denied)
unless the process was launched with `CREATE_BREAKAWAY_FROM_JOB`.

The launcher handles this automatically:

1. The emulator is launched suspended (`CREATE_NEW_PROCESS_GROUP | CREATE_SUSPENDED`)
   without `CREATE_BREAKAWAY_FROM_JOB`, so it cannot execute before limits are in force.
2. If `AssignProcessToJobObject` fails with error 5, the launcher kills the still
   suspended process and relaunches with `CREATE_BREAKAWAY_FROM_JOB` set, then assigns it
   to the Peach Job Object normally.

If the breakaway relaunch also fails (e.g. the process is inside a non-breakaway job set
by a third-party tool or a debugger), **the launch is aborted** and the error is surfaced
to the user. There is no unsandboxed fallback.

Launch and Job Object lifecycle live in the vendored
[`wincage`](../services/vendor/wincage/) package (`wincage/process.py`, `wincage/job.py`);
Peach 1UP's era-limit resolution wrapper is
[`backend/service/utils/platform/windows/process/launcher.py`](../backend/service/utils/platform/windows/process/launcher.py).

---

## DOSBox-X specifics

`write_launch_conf()` in
[`backend/service/backends/dosbox.py`](../backend/service/backends/dosbox.py) builds a
complete `dosbox-x.conf` for each launch: it takes the bundled
`library/system/templates/dosbox-x/base.conf`, strips any `[autoexec]` section, and
appends a generated `[autoexec]` block (drive mounts, then profile- and item-level launch
commands). The result is written to a private per-launch temp directory created with
`tempfile.mkdtemp(prefix="peach1up_dosbox_")`. Environment launches use the parallel
`write_environment_launch_conf()` with prefix `peach1up_dosbox_env_`.

The command line passes `-noconfig` (so DOSBox-X ignores any user config), an optional
`-set ne2000=false` when networking is disabled for the profile, and `-conf <path>`
pointing at the generated conf. After the process exits, `_cleanup_temp_dir_on_exit()`
removes the temp directory.

Within the generated `[autoexec]` block, paths are passed to `MOUNT`/`IMGMOUNT` as raw
absolute Windows paths, double-quoted only when they contain whitespace. Forward slashes
and 8.3 short path conversion are not used; the DOSBox-X autoexec tokeniser treats a
forward slash as a DOS switch character and would truncate the argument.

**History:** Prior to PX-2-8, DOSBox-X wrote its launch conf to a single shared location,
which a concurrent second launch could overwrite mid-read by the first. This was fixed by
writing each launch's conf to its own `tempfile.mkdtemp()` directory as described above.

---

## xemu

`container_enabled = false` is hard-capped for xemu in
[`config/emulators/xemu.toml`](../config/emulators/xemu.toml) via
`container_permanently_excluded = true`, and cannot be overridden per profile.

**Reason:** xemu is built on QEMU's TCG backend, which calls `DeviceIoControl` to query
disk geometry for `qcow2` images. AppContainer blocks this call, causing a fatal block
driver assertion at launch. This is a QEMU platform limitation, not a Peach 1UP
configuration gap.

Job Object isolation is the only isolation layer available for xemu on Windows, and since
xemu also sets `skip_cpu_limit = true` and `skip_memory_limit = true`, kill-on-close is
the only control that remains active on it.

`skip_memory_limit = true` is set because xemu's pre-allocated JIT heap triggers the same
`STATUS_STACK_BUFFER_OVERRUN` fast-fail as the Qt-based emulators. See "Qt emulator
process memory cap waived" in [SECURITY.md](SECURITY.md).
