# Windows Sandbox

Peach 1UP runs emulators under a dedicated low-privilege Windows account (`peach_sandbox`)
and wraps each launch in a Windows Job Object with CPU and memory limits. This page
explains what the sandbox does, how the account is set up, and how to adjust the resource
caps if needed.

---

## What the sandbox does

Every emulator launched on Windows runs as the `peach_sandbox` local user rather than as
your own account. This limits what a compromised or misbehaving emulator process can
reach — it cannot read your Documents folder, write to arbitrary paths on `C:\`, or
access your user profile.

On top of the restricted account, each emulator is placed inside a Windows Job Object
before it runs. The Job Object enforces:

| Limit         | Effect                                                                                                                                     |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Kill-on-close | When the Peach 1UP backend exits, all emulator processes in the job are terminated automatically. No orphaned processes.                   |
| CPU hard cap  | Threads are throttled when the emulator exceeds its per-era CPU budget per scheduling interval. Prevents thermal spikes and runaway usage. |
| Memory cap    | Per-process memory is capped. A runaway emulator cannot exhaust host RAM.                                                                  |

If the Job Object cannot be created or the emulator cannot be assigned to it, **the
launch is aborted**. There is no fallback to an uncontained launch.

**What the sandbox does not do:**

- It does not prevent the emulator from reading files the `peach_sandbox` account can
  reach (emulator binaries, media paths you have configured).
- It does not apply AppContainer-level isolation or filesystem virtualisation.
- It does not block all network access at the OS level — network isolation is handled by
  disabling the emulated network adapter inside each emulator (see the network section in
  SECURITY.md).
- It does not apply on Linux. Linux isolation is planned for P8.

---

## The peach_sandbox account

### How it is created

The account is created automatically when the Peach 1UP backend starts for the first time.
No manual setup is required. The backend runs `scripts/create_sandbox_user.ps1` via
PowerShell during its startup sequence. The script:

1. Checks whether `peach_sandbox` already exists on the local machine.
2. If absent, creates it as a standard local user account with:
   - Password never expires
   - User may not change password
   - Account never expires
3. If already present, syncs the password to the value stored in `config/settings.yaml`.
4. Enables the account if it was disabled.
5. Removes the account from the Administrators group if it was accidentally added.
6. Grants read and execute ACLs to the configured emulator binary directories,
   `IMAGES_PATH`, and `ROM_PATH` so `peach_sandbox` can reach media and executables
   without requiring broader filesystem access.
7. Exits with code 0 on success, or code 1 with an error on stderr on any failure.

If the script exits with a non-zero code, backend startup is aborted and the error is
shown in the log. Resolve the error (usually a permissions issue) and restart the backend.

### Password management

The account password is generated automatically on first run as a 32-character
alphanumeric string and stored in `config/settings.yaml` under the key `SANDBOX_PASSWORD`.
It is never written to logs, never returned by any API endpoint, and must never be
committed to version control. If `settings.yaml` is deleted, a new password is generated
on the next start and the account password is synced automatically.

### Privileges

The `peach_sandbox` account is a standard local user. It has no special group membership
and no elevated privileges. It is not an interactive account — it cannot be used to log
in to Windows via the lock screen or Remote Desktop.

---

## Resource caps and eras.yaml

CPU and memory limits for each emulator era are defined in `config/eras.yaml`. Each era
entry has two fields that control the Job Object:

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
| DOS         | 256 MB     | 50%     |
| Windows 3.1 | 256 MB     | 50%     |
| Windows 95  | 512 MB     | 75%     |
| Windows 98  | 512 MB     | 75%     |
| Windows XP  | 1024 MB    | 80%     |
| PS1         | 256 MB     | 60%     |
| PS2         | 512 MB     | 80%     |
| Xbox OG     | 1024 MB    | 75%     |
| NES         | 128 MB     | 30%     |
| N64         | 256 MB     | 60%     |

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

**Backend fails to start with "Sandbox user setup failed"**

The `create_sandbox_user.ps1` script exited non-zero. Common causes:

- The backend is not running with sufficient privileges to create local users. On most
  Windows installs this requires the backend to run as Administrator (UAC prompt).
- `peach_sandbox` exists but is in a state the script cannot repair (e.g. a domain
  account with the same name, or a locked-down policy preventing password changes).

Check the log output for the specific error line and resolve it, then restart the backend.

**Emulator fails to launch with "Failed to launch ... as peach_sandbox"**

`CreateProcessWithLogonW` failed. Most common causes:

- The `peach_sandbox` account does not exist yet — start the backend once to trigger
  account creation before attempting a launch.
- The emulator binary path or media path is not readable by the `peach_sandbox` account.
  ACL grants for all configured paths are applied automatically by
  `create_sandbox_user.ps1` on every backend startup. If you moved an emulator or changed
  a path in `settings.yaml` after initial setup, restart the backend to re-apply the
  grants. You can also grant read + execute access to `peach_sandbox` manually via
  `icacls` or the folder Properties > Security tab.
- The secondary logon service (`seclogon`) is disabled. Open Services (`services.msc`),
  find "Secondary Logon", and set it to Manual or Automatic.

**Emulator crashes immediately with no error**

The memory cap for the era may be too low. Raise `memory_limit_mb` in `config/eras.yaml`
for the affected era and restart the backend.

---

## DOSBox-X specifics

DOSBox-X is launched with mount and hardware settings passed as inline `-c` arguments on
the command line. No temporary `.conf` file is written to disk at launch time. The
`peach_sandbox` account therefore needs read access only to the emulator binary directory
and the media path — it does not require access to any temp or user-profile config
location. Long paths containing spaces are passed as quoted absolute paths; 8.3 short
path conversion is not used.
