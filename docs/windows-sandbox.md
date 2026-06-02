# Windows Sandbox

Peach 1UP wraps each emulator launch in a Windows Job Object with CPU and memory
limits enforced per era. This page explains what the Job Object does and how to
adjust the resource caps.

---

## What the Job Object does

Every emulator launched on Windows is placed inside a Windows Job Object before it
runs. The Job Object enforces:

| Limit         | Effect                                                                                                                                     |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Kill-on-close | When the Peach 1UP backend exits, all emulator processes in the job are terminated automatically. No orphaned processes.                   |
| CPU hard cap  | Threads are throttled when the emulator exceeds its per-era CPU budget per scheduling interval. Prevents thermal spikes and runaway usage. |
| Memory cap    | Per-process memory is capped. A runaway emulator cannot exhaust host RAM.                                                                  |

If the Job Object cannot be created or the emulator cannot be assigned to it, **the
launch is aborted**. There is no fallback to an uncontained launch.

Emulators run under the current user account. AppContainer isolation (P9) is an
additional layer applied on top of Job Objects when `container_enabled = true` in
the emulator descriptor. Currently only DOSBox-X has AppContainer enabled. A dedicated
low-privilege user account is not used.

**What the Job Object does not do:**

- It does not restrict filesystem access — the emulator can reach any path the
  current user can reach.
- It does not apply AppContainer-level isolation or filesystem virtualisation.
- It does not block all network access at the OS level — network isolation is handled
  by disabling the emulated network adapter inside each emulator (see the network
  section in SECURITY.md).
- It does not apply on Linux. Linux isolation is planned for P8.

---

## Resource caps and eras.yaml

CPU and memory limits for each emulator era are defined in `config/eras.yaml`. Each
era entry has two fields that control the Job Object:

```yaml
dos:
  memory_limit_mb: 256
  cpu_limit_percent: 50
```

| Field               | Type            | What it sets                                                                                                                                                                |
| ------------------- | --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `memory_limit_mb`   | integer         | Per-process memory cap in megabytes. Applied via `JOB_OBJECT_LIMIT_PROCESS_MEMORY`.                                                                                         |
| `cpu_limit_percent` | integer (1–100) | CPU budget as a percentage of all logical processors across a scheduling interval. Applied as a hard cap — threads are throttled, not killed, when the budget is exhausted. |

### Current defaults

| Era         | Memory cap | CPU cap |
| ----------- | ---------- | ------- |
| DOS         | 512 MB     | 50%     |
| Windows 3.1 | 512 MB     | 50%     |
| Windows 95  | 2048 MB    | 75%     |
| Windows 98  | 2048 MB    | 75%     |
| Windows XP  | 3072 MB    | 80%     |
| PS1         | 1024 MB    | 60%     |
| PS2         | 4096 MB    | 80%     |
| Xbox OG     | 3072 MB    | 75%     |
| Dreamcast   | 1024 MB    | 60%     |
| NES         | 512 MB     | 30%     |
| N64         | 1024 MB    | 60%     |

### How to adjust caps

Open `config/eras.yaml` in any text editor and change `memory_limit_mb` or
`cpu_limit_percent` for the era you want to adjust. Restart the backend — changes
take effect on the next launch.

**CPU cap notes:**

- `cpu_limit_percent: 100` gives the job unrestricted CPU access across all logical
  processors. This removes throttling but does not disable kill-on-close or memory
  limits.
- The cap is spread across all logical processors. On an 8-thread machine,
  `cpu_limit_percent: 50` allows the equivalent of 4 threads' worth of CPU time per
  scheduling interval.
- CPU rate control requires Windows 8.1 or later (KB2898600 for Windows 8.0).
- Setting the value below 1 is clamped to 1 by the Job Object wrapper.

**Memory cap notes:**

- The cap is per-process, not per-job. Child processes spawned by the emulator each
  have the same cap applied individually.
- Setting the cap too low for a resource-intensive era (e.g. PS2 or Xbox) will cause
  the emulator to crash or fail to load large games. Raise the cap if you see
  out-of-memory errors.

---

## Troubleshooting

**Emulator crashes immediately with no error**

The memory cap for the era may be too low. Raise `memory_limit_mb` in
`config/eras.yaml` for the affected era and restart the backend.

**Job Object assignment fails on Windows 11 (nested job retry)**

Windows 11 pre-assigns new child processes to an OS-managed Job Object. Attempting
to assign such a process to a second Job Object fails with error code 5 (access
denied) unless the process was launched with `CREATE_BREAKAWAY_FROM_JOB`.

The launcher handles this automatically:

1. The emulator is launched suspended without `CREATE_BREAKAWAY_FROM_JOB`.
2. If `IsProcessInJob` reports the process is already in a job, the launcher kills it
   and relaunches with `CREATE_BREAKAWAY_FROM_JOB` set, then assigns it to the Peach
   Job Object normally.

If the breakaway relaunch also fails (e.g. the process is inside a non-breakaway job
set by a third-party tool or a debugger), **the launch is aborted** and the error is
surfaced to the user. There is no unsandboxed fallback.

---

## DOSBox-X specifics

DOSBox-X is launched with mount and hardware settings passed as inline `-c` arguments
on the command line. No temporary `.conf` file is written to disk at launch time.
Long paths containing spaces are passed as quoted absolute paths; 8.3 short path
conversion is not used.
