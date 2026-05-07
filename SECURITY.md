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
- **JWT secret exposure** — if the JWT secret is logged, returned in an API response, or
  committed to version control, all issued tokens become forgeable.

---

## Authentication and Profiles

Auth is **off by default** for single-user local installs. It must be explicitly enabled
in settings.

**Profile model:**

- **Owner profile** — created at first run. Full access. Bypasses all permission checks.
  Cannot be deleted.
- **Sub-profiles** — created by the owner. Explicit permission flags govern what each
  sub-profile can do. All profiles can launch media by default.
- **Profile switching** — PS4-style: visible on the home screen, select to switch. Each
  profile may optionally have a PIN. PIN is required to switch into that profile.
- **OIDC** — supported as an optional external identity provider. Disabled by default.
  When enabled, profile switching defers to the OIDC provider for identity verification.

**Recovery:**

- A recovery key is generated at first run and shown once. It is not stored in
  recoverable form after that. The owner must record it.
- The recovery key can be used to reset the owner profile via the web UI.
- CLI reset (`peach reset-owner`) is the last-resort fallback if the web UI is
  inaccessible.
- No email recovery. No external auth dependency by default.

---

## Authorisation and Permissions

Permission flags on sub-profiles:

| Flag                  | What it controls                                              |
| --------------------- | ------------------------------------------------------------- |
| `can_launch_media`    | Launch any library item (granted to all profiles by default)  |
| `can_install_media`   | Run installation flows for new media                          |
| `can_edit_library`    | Add, edit, or remove library items                            |
| `can_manage_profiles` | Create or modify sub-profiles (never grants owner privileges) |
| `can_edit_settings`   | Modify application settings                                   |
| `is_admin`            | All of the above except owner-only operations                 |

**Content ratings and parental controls:**

- The owner assigns a content rating to each library item.
- The owner sets a maximum allowed rating per sub-profile.
- A sub-profile cannot launch an item whose rating exceeds its limit, regardless of
  other permissions.
- Rating enforcement is server-side. The client UI hides restricted items but the API
  enforces the limit independently.

---

## Input Validation Rules

**These are mandatory implementation rules, not guidelines.**

- Every file path accepted from any source — request body, query parameter, profile
  field, settings value — **must be resolved, normalised, and validated against an
  allowlist of permitted base directories** before any filesystem operation is performed.
  Permitted base directories are: the configured `IMAGES_PATH`, `PROFILES_PATH`,
  `ROM_PATH`, and the application config directory.
- Path traversal attempts (resolved path escapes its permitted base) **must be rejected
  with a 400 error and logged** before any filesystem operation occurs.
- **No user-supplied string may reach a subprocess call directly.** There must be at
  least one validation layer between input and execution.
- Emulator binary paths come from `settings.yaml` only. They are never taken from
  request input, query parameters, or profile fields.
- CLI arguments passed to emulator processes come from validated `Profile` config fields
  only. There is no freeform command construction anywhere in the codebase.
- All validated inputs must be checked again at the point of use — do not rely on prior
  validation in a different layer.

---

## Process Spawning Rules

**Mandatory.**

- Emulator binaries are resolved from `settings.yaml` exclusively. The binary path is
  never derived from request input.
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

- The JWT secret is generated on first run and stored in `settings.yaml`. It is never
  exposed via any API response and never written to logs.
- Passwords are hashed with bcrypt at a minimum cost factor of **12**. Plaintext
  passwords are never stored or logged.
- HTTP middleware strips `Authorization` headers before any log output. Credentials must
  not appear in application logs under any circumstances.
- IGDB API keys and any other third-party API credentials are stored in `settings.yaml`
  only. They are never committed to version control, never returned by the API, and never
  logged.
- The recovery key is shown once at first run and then discarded. It is stored as a
  bcrypt hash only — the plaintext form cannot be recovered from the stored hash.
- The session secret is generated on first run via get_or_generate_session_secret() and persisted to settings.yaml. It must never appear in logs, API responses, or  
  version control. It is treated with the same handling rules as the JWT secret. If settings.yaml is deleted or the key is removed, a new secret is generated on next startup, invalidating all existing sessions.

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
- Secrets, credentials, or JWT handling

If an implementation approach would require bypassing, weakening, or working around any
rule in this file, **stop and flag it** rather than finding a workaround. Raise it in the
conversation and wait for an explicit decision before proceeding.

---

## Known Limitations

**Job Objects bypass on Windows 11 (error code 5)**

On Windows 11, assigning an emulator process to a Job Object fails with error code 5
(access denied) regardless of breakaway flag combinations. When this occurs, the launcher
falls back to `launch_direct`, which starts the emulator without Job Object containment.
Network blocking via Windows Firewall rules still applies in this fallback path, but
process-level isolation is weaker — resource limits and filesystem restriction are not
enforced. This is a known Windows 11 behaviour and is logged in
[DECISIONS.md](DECISIONS.md) (2026-05-05, "Job Objects bypassed via launch_direct for
DOS launches"). The issue is tracked for revisit once the web UI replaces the TUI.

The scan endpoint validates all user-supplied directory paths against an allowlist of configured base directories (IMAGES_PATH, PROFILES_PATH, ROM_PATH) before any filesystem operation. This is a mandatory enforcement of the Input Validation Rules above. If none of these paths are configured in settings, scanning is blocked entirely. Media collections must reside under a configured base directory. This restriction must be carried forward to any future endpoint that accepts a directory or file path parameter.

All frontend fetch calls must include credentials: 'include' while SessionMiddleware is active so session cookies are transmitted correctly. When P5 changes the serving model (FastAPI serving the React static build directly), re-evaluate whether this setting is still correct or introduces unintended cookie scope.

---

## Reporting Security Issues

Please report security vulnerabilities **privately** via
[GitHub Security Advisories](https://github.com/anthropics/peach_1up/security/advisories)
rather than opening a public issue. Public disclosure before a fix is available puts
other users at risk. Include a description of the vulnerability, steps to reproduce, and
any relevant environment details. We will respond as quickly as possible and coordinate
a disclosure timeline with you.
