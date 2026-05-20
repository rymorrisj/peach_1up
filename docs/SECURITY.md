# Peach 1UP — Security Architecture

## Overview

Peach 1UP is a locally hosted web application that spawns native OS processes, mounts
disk images, and manages emulator lifecycles. This creates an unusual attack surface for
a local app: a browser-facing HTTP service that crosses the process boundary into native
binary execution, file system access, and OS-level resource management. Security is
treated as a first-class concern throughout the codebase. Every layer — input validation,
process spawning, network binding, authentication, and secrets handling — has explicit
rules that are enforced at the implementation level, not left to convention.

---

## Threat Model

Realistic threats specific to this application:

- **Cross-origin requests from other browser tabs** — any tab open in the browser can
  reach a localhost service. Without auth and CSRF protection, a malicious page could
  trigger launches, delete library entries, or read profile data.
- **Path traversal via user-supplied file paths** — media paths, profile fields, and
  image paths are supplied by the user and could be crafted to escape permitted
  directories (e.g. `../../etc/passwd`, `..\..\Windows\System32`).
- **Arbitrary process execution via manipulated launch parameters** — if any portion of a
  subprocess call is constructed from unvalidated input, an attacker could inject
  arguments or substitute a different binary.
- **Privilege escalation via the emulator process tree** — emulators that spawn child
  processes or load plugins could be used to break out of process isolation. The
  emulator process tree must be fully contained by the isolation layer.
- **Unauthorised access to a shared library on a local network** — if the service is
  bound to `0.0.0.0` (remote access mode), other devices on the network can reach it.
  Without authentication this exposes the full library, settings, and launch capability.
- **Session secret exposure** — if the session secret is logged, returned in an API
  response, or committed to version control, all active sessions become forgeable.

---

## Authorisation and Permissions

Permission flags on sub-accounts:

| Flag                  | What it controls                                          |
| --------------------- | --------------------------------------------------------- |
| `can_launch_media`    | Launch any permitted library item (default: true)         |
| `can_edit_platforms`  | Register or modify OS platforms                           |
| `can_edit_library`    | Add, edit, or remove library items                        |
| `can_manage_profiles` | Create or modify sub-accounts (never grants owner powers) |
| `can_edit_settings`   | Modify application settings                               |
| `is_admin`            | All of the above except owner-only operations             |

**PIN security:**

- PINs are 4–6 digits, stored as Argon2id hashes with a per-user random salt.
- An optional app-level pepper may be configured in `settings.yaml`, stored outside SQLite.
- Plaintext PINs are never stored, logged, or returned by any API endpoint.
- 4 consecutive failures locks the account. Owner resets via Settings.
- Owner lockout: run `scripts/setup_admin_user.py` locally — overwrites the owner record.
  No remote reset, no email recovery, no bypass flag.

**Content ratings and parental controls:**

- Ratings ingested from NFO files, disc metadata, or filenames at scan time. Owner can override.
- Unrated is a first-class state. `block_unrated_media` flag controls whether unrated items
  are visible to a sub-account.
- Each sub-account has a `max_content_rating` threshold. Items above the threshold are
  filtered at the query level — hidden entirely, not surfaced and denied at launch.
- Enforcement is server-side. Deny wins over any permission flag with no override path.
- Rating scale is freetext on `LibraryItem`. Recommended: ESRB (E, E10+, T, M, AO) or
  PEGI (3, 7, 12, 16, 18). Ordinal comparison map configured in `settings.yaml`.

---

## Input Validation Rules

**These are mandatory implementation rules, not guidelines.**

- Every file path accepted from any source — request body, query parameter, profile
  field, settings value — **must be resolved and normalised** before any filesystem
  operation is performed. Paths used for library scans, media scanning, and profile
  operations **must be validated against an allowlist** of permitted base directories:
  the configured `LIBRARY_PATH` (and its derived sub-paths `GAMES_PATH`, `OS_PATH`,
  `ROM_PATH`, `BIOS_PATH`, `TOOLS_PATH`), `PROFILES_PATH`, and the application config
  directory. **Exception:** platform image paths (`base_image_path`,
  `working_image_path`) may reside anywhere on the host filesystem — see Known Gaps.
- Path traversal attempts (resolved path escapes its permitted base) **must be rejected
  with a 400 error and logged** before any filesystem operation occurs. This applies to
  all path-validated operations; platform image paths are the explicit carved-out
  exception documented in Known Gaps.
- **No user-supplied string may reach a subprocess call directly.** There must be at
  least one validation layer between input and execution.
- Emulator binary paths are **never taken from request input**, query parameters, or
  profile fields. Paths resolve through three tiers: (1) user override stored in
  `settings.yaml` via the UI, (2) bundled project `emulators/{slug}/` directory,
  (3) catalog-detected known installation paths from `emulators.yaml`. No registry
  scanning. This rule has no exceptions.
- CLI arguments passed to emulator processes come from validated `Profile` config fields
  only. There is no freeform command construction anywhere in the codebase.
- All validated inputs must be checked again at the point of use — do not rely on prior
  validation in a different layer. (For image paths, see Known Gaps.)

---

## Process Spawning Rules

**Mandatory.**

- Emulator binary paths are never derived from request input. Paths resolve through
  three tiers: `settings.yaml` user override, bundled `emulators/{slug}/` project
  directory, or catalog-detected system installation paths from `emulators.yaml`.
  No registry scanning.
- Arguments are constructed from validated `Profile` fields only. No string interpolation
  of raw user input into argument lists.
- One concurrent launch is permitted per profile. A second launch request while a
  session is active must be rejected.
- A launch cooldown is enforced between successive requests to prevent rapid-fire
  spawning.
- All spawned processes are tracked and recorded in `LaunchHistory` (emulator, profile,
  media path, start time, exit code).
- On Linux, process isolation uses cgroups and network namespaces. On Windows, Job
  Objects are used where available (see [Known Limitations](#known-limitations)).

---

## Network Rules

**Mandatory.**

- The service binds to `127.0.0.1` by default. It must not bind to `0.0.0.0` unless
  `ALLOW_NETWORK_ACCESS` is explicitly set to `true` in settings.
- CORS is locked to the application origin by default. It must not be widened without
  an explicit operator decision.
- CSRF protection is required on all state-changing endpoints (POST, PUT, PATCH, DELETE).
- **Remote access is the operator's responsibility.** If remote access is needed, the
  recommended pattern is a reverse proxy with an external auth provider (e.g. Authentik,
  Authelia) in front of this service. Peach 1UP does not manage TLS termination or
  external routing.

**Network isolation is emulator-native**

Network blocking is enforced at the emulator level, not via host OS firewall rules.
Each emulator is launched with its network adapter disabled or absent when
enable_networking is false on the active profile (the default). DOSBox-X launches
with the NE2000 adapter disabled via config. 86Box omits the network device from
the machine config entirely. VirtualBox sets --nic1 null via VBoxManage at launch
time. Console emulators (DuckStation, PCSX2, xemu, Mesen, Project64) have no
meaningful network capability and require no explicit blocking.

This approach requires no host elevation, cannot be accidentally bypassed by a
COM availability issue, and is harder for emulated software to work around than
a host firewall rule. Users who need network access for specific software can
enable it explicitly per profile.

---

## Destructive Operations

**Mandatory.**

Any endpoint that deletes or overwrites data requires a two-step confirmation:

1. The client requests a short-lived confirmation token from a dedicated endpoint.
2. The client includes the token in the destructive request.
3. The token expires after **60 seconds**. Expired tokens are rejected.

Applies to:

- Platform delete
- Library item delete
- Snapshot delete
- Snapshot restore (overwrites the working image)
- Working image reset to base

All destructive operations are logged with the profile that initiated them, the resource
affected, and the timestamp.

---

## Secrets Handling

**Mandatory.**

- The session secret (`SESSION_SECRET` in `settings.yaml`) is generated on first run via
  `get_or_generate_session_secret()` and used by `SessionMiddleware` to sign session
  cookies. It must never appear in logs, API responses, or version control. If
  `settings.yaml` is deleted or the key is removed, a new secret is generated on next
  startup, invalidating all existing sessions.
- PINs are hashed with Argon2id with a per-user random salt. Plaintext PINs are never
  stored or logged.
- HTTP middleware strips `Authorization` headers before any log output. Credentials must
  not appear in application logs under any circumstances.
- IGDB API keys and any other third-party API credentials are stored in `settings.yaml`
  only. They are never committed to version control, never returned by the API, and never
  logged.
- The recovery key is shown once at first run and then discarded. It is stored as an
  Argon2id hash only — the plaintext form cannot be recovered from the stored hash.

---

## SQLite Security Notes

SQLite does not enforce foreign key constraints by default. This must be corrected on
every connection.

**Required:** register a SQLAlchemy `connect` event listener that executes
`PRAGMA foreign_keys = ON` on every new connection. Do not assume this is set by default
or by the ORM. The listener must be in place before any schema migration or data
operation runs.

---

## What Claude Code Must Do

This section is a standing instruction. When implementing any feature that touches the
following areas, **re-read this file before writing code**:

- Authentication or session handling
- Profile switching or permission checks
- File path handling of any kind
- Subprocess or process spawning
- Emulator launch flows
- Disk image operations (mount, copy, snapshot, restore)
- Settings read or write
- Destructive operations (delete, overwrite, reset)
- Network binding, CORS configuration, or middleware
- Secrets, credentials, or session secret handling

If an implementation approach would require bypassing, weakening, or working around any
rule in this file, **stop and flag it** rather than finding a workaround. Raise it in the
conversation and wait for an explicit decision before proceeding.

---

### Windows-specific process rules

**Mandatory.**

- All emulator processes on Windows are launched under the current user account via
  `CreateProcessW`. Account-level isolation (AppContainer or a dedicated low-privilege
  account) is deferred to a later phase.
- Every emulator launch is assigned to a fresh Job Object with:
  - `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` — the entire emulator process tree is torn
    down automatically if the backend exits, preventing orphaned processes.
  - A per-era CPU hard cap sourced from `config/eras.yaml` (`cpu_limit_percent`).
    Threads are throttled, not killed, when the budget is exhausted per scheduling
    interval. Requires Windows 8.1 or later.
  - A per-era per-process memory cap sourced from `config/eras.yaml`
    (`memory_limit_mb`), applied via `JOB_OBJECT_LIMIT_PROCESS_MEMORY`.
- If Job Object creation or assignment fails for any reason, **the launch is aborted**
  and the error is surfaced to the user. There is no unsandboxed fallback path.

---

## Known Limitations

### Job Object assignment on Windows 11 (nested job retry)

Windows 11 pre-assigns new child processes to an OS-managed Job Object. Attempting to
assign such a process to a second Job Object fails with error code 5 (access denied)
unless the process was launched with `CREATE_BREAKAWAY_FROM_JOB`.

The launcher handles this automatically in two stages:

1. The emulator is launched suspended without `CREATE_BREAKAWAY_FROM_JOB`.
2. If `IsProcessInJob` reports the process is already in a job, the launcher kills it
   and relaunches with `CREATE_BREAKAWAY_FROM_JOB` set, then assigns it to the Peach
   Job Object normally.

If the breakaway relaunch also fails (e.g. the process is inside a non-breakaway job set
by a third-party tool or a debugger), **the launch is aborted** and the error is surfaced
to the user. There is no unsandboxed fallback. Network isolation is unaffected because it
is emulator-native (network adapter disabled at the emulator config level).

The scan endpoint validates all user-supplied directory paths against an allowlist of configured base directories (LIBRARY_PATH, PROFILES_PATH) before any filesystem operation. This is a mandatory enforcement of the Input Validation Rules above. If none of these paths are configured in settings, scanning is blocked entirely. Media collections must reside under a configured base directory. This restriction must be carried forward to any future endpoint that accepts a directory or file path parameter.

All frontend fetch calls must include credentials: 'include' while SessionMiddleware is active so session cookies are transmitted correctly. When P5 changes the serving model (FastAPI serving the React static build directly), re-evaluate whether this setting is still correct or introduces unintended cookie scope.

#### Qt emulator process memory cap waived

JOB_OBJECT_LIMIT_PROCESS_MEMORY is not applied to Qt-based emulators
(86Box, DuckStation, PCSX2). Qt's security initialisation triggers
STATUS_STACK_BUFFER_OVERRUN (0xC0000409) when this limit is applied
after process creation. Kill-on-close and CPU rate control still apply.
The skip_memory_limit flag in config/emulators/ controls this per
emulator. See DECISIONS.md 2026-05-19 for full rationale.

### Linux sandbox implementation (planned)

The current Linux process isolation description (cgroups and network namespaces) is
a design intent. A concrete implementation based on either nsjail or native
namespaces + cgroups will be introduced in P8. Until then, Linux emulator launches
do not have a hardened sandbox equivalent to the planned Windows low-privilege
user + Job Object model.

---

## Known Gaps

### Platform image path traversal relies on OS trust model

`base_image_path` and `working_image_path` on Platform records may be set by any user
with `can_edit_platforms` permission and may point to any location on the host filesystem.
The runtime allowlist check against `OS_PATH` and `LIBRARY_PATH` was intentionally
removed to allow images on secondary drives, external volumes, and NAS shares outside
the configured library directories.

**Implications:** A user with `can_edit_platforms` can cause the backend to read, copy,
or perform existence checks on files at arbitrary paths on the host. Mitigating factors:

- `can_edit_platforms` is an explicit operator-granted permission, not a default for
  sub-accounts.
- The application runs as a local user, not a privileged service account.
- Operations on image paths are limited to copy, read, and existence check — no shell
  execution of image path values.

This gap is tracked and will be addressed in a future hardening pass, either by restoring
a configurable allowlist with an opt-out flag or by surfacing an explicit warning at
environment registration time.

---

## Reporting Security Issues

Please report security vulnerabilities **privately** via
[GitHub Security Advisories](https://github.com/anthropics/peach_1up/security/advisories)
rather than opening a public issue. Public disclosure before a fix is available puts
other users at risk. Include a description of the vulnerability, steps to reproduce, and
any relevant environment details. We will respond as quickly as possible and coordinate
a disclosure timeline with you.
