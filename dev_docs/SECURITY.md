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
- **Identity secret exposure** — each user has a per-user HMAC root key
  (`identity_token_secret`) used to mint session tokens; the active session is tracked only as
  a `session_token_hash` (a SHA-256 digest, not reversible to the token). If
  `identity_token_secret` leaks, an attacker can mint arbitrary valid session tokens for that
  one user indefinitely, until the secret is rotated — but the blast radius is a single
  account, not a master secret that forges sessions for everyone. A leaked `session_token_hash`
  alone cannot be turned back into a usable token.

---

## Sequential integer primary keys (accepted tradeoff)

All primary keys in this codebase — `GameItemBundle.id`, `GameItem.id`,
`EnvironmentItem.id`, `Profile.id`, etc. — are sequential auto-increment integers, exposed directly in
API route paths E.G.: (`/api/v1/game-item-bundle/{id}`, `/api/v1/game-item/{id}`,
`/api/v1/environment-items/{id}`, `/api/v1/tags/{tag_id}/items/{item_id}`, etc.). These IDs are enumerable by any authenticated user.

It is documented here as a standing, accepted tradeoff.
A migration to opaque identifiers (e.g. UUIDs) has been flagged as a separate,
larger future discussion if the threat model ever warrants revisiting it.

---

## Authorisation and Permissions

Permission flags on sub-accounts. The authoritative list is `UserBase` in
`backend/models/user.py`; this table must be kept in step with it.

| Flag                     | What it controls                                                                                                                                                                                                                                                                                |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `can_launch_media`       | Launch any permitted software collection (default: true)                                                                                                                                                                                                                                        |
| `can_manage_environment`  | Register or modify Environments (the Windows OS install workspaces; was `can_edit_platforms`)                                                                                                                                                                                                   |
| `can_manage_game`    | Create, edit, delete, or scan/import software collections and items, **and** create/modify/delete launch Profiles (the `Profile` model in `routes/profiles.py`). Also the gate on `POST /api/v1/software/scan`. Was `can_edit_library` (renamed once to `can_edit_software`, then to this name to reflect that it covers create/delete/scan-import, not just edits) |
| `can_manage_media`         | Add, edit, or remove Media (the archival audio/text/image/video domain)                                                                                                                                                                                                                          |
| `can_manage_app`         | Add, edit, or remove Apps (the `AppItemBundle` domain) and gates the app-upload router                                                                                                                                                                                                          |
| `can_manage_controllerMapping` | Create, edit, or delete controller mappings (System → Controllers)                                                                                                                                                                                                                              |
| `can_manage_settings`      | Modify application settings                                                                                                                                                                                                                                                                     |
| `can_manage_users`       | Lets a sub-account edit its own `name` and reset its own PIN only — no capability over any other account, no self-delete, no create/delete of any sub-account. Owner-only to grant, like every flag here. Checked in addition to (not instead of) the `is_admin` path on the same two endpoints |
| `is_admin`               | Edit/reset-pin/unlock/force-logout an existing sub-account, plus various admin-only settings/emulator/BIOS endpoints. Does **not** implicitly grant any other flag in this table — each is checked independently. Creating or deleting a sub-account requires `is_owner`, not `is_admin`        |

`is_owner` bypasses every permission check (`require_permission` short-circuits
for the owner). It is not settable via the user create/patch API.

**PIN reset authorisation (`POST /api/v1/users/{id}/reset-pin`).** The enforced
rules, as implemented in `users.py::reset_pin` and locked by
`test_users_create_delete_reset.py`, are:

- The **owner account's** PIN can never be reset through this endpoint by anyone
  (owner-target requests are rejected with 403; owner PIN recovery is the local
  `scripts/setup_admin_user.py` path only).
- The **owner** bypasses every other check and can reset any user's PIN
  regardless of lock state or target role.
- An **admin** can reset PINs only for accounts that are neither the owner nor
  another admin, i.e. regular/capped sub-accounts only. Attempting to reset the
  owner's PIN or any admin's PIN, including their own, returns 403.
- A user holding `can_manage_users` can reset **its own** PIN via the same
  endpoint (self-service), but no one else's, and this self-service path is
  blocked with 403 while the account is locked, so a locked sub-account cannot
  self-recover.

**PIN security:**

- PINs are 4–6 digits, stored as Argon2id hashes with a per-user random salt.
- An optional app-level pepper (`PIN_PEPPER`) may be configured via `PATCH /api/v1/settings/pin-pepper`, stored in `.env` — outside SQLite.
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
- The rating filter **fails closed**. An unknown `max_content_rating` is rejected on
  write (`validate_max_content_rating`), and if a stored ceiling can no longer resolve
  to a known ordinal (e.g. a `rating_ordinals` change orphaned a previously-valid
  value), `get_filtered_collections` denies all rated content rather than silently
  dropping the cap. A collection whose own rating is unrecognised is likewise denied to
  a capped user, never passed through.
- Enforcement is server-side. Deny wins over any permission flag with no override path.
- Rating scale is freetext on `GameItemBundle.content_rating` (also present on
  `AppItemBundle.content_rating`). Recommended: ESRB (E, E10+, T, M, AO) or
  PEGI (3, 7, 12, 16, 18). Ordinal comparison map configured via the
  `rating_ordinals` key in `settings` (falls back to defaults in
  `dependencies.py` — ⚠ no write path exists today; see Known Gaps).

---

## Input Validation Rules

**These are mandatory implementation rules, not guidelines.**

- Every file path accepted from any source — request body, query parameter, profile
  field, settings value — **must be resolved and normalised** before any filesystem
  operation is performed. Paths used for library scans, media scanning, and profile
  operations **must be validated against an allowlist** of permitted base directories:
  the configured `LIBRARY_PATH` (and its derived sub-paths `SOFTWARE_PATH`, `MEDIA_PATH`,
  `OS_PATH`, `ROMS_PATH`), `PROFILES_PATH`, and the application config
  directory. **Exception:** Environment image paths (`base_image_path`,
  `working_image_path`) may reside anywhere on the host filesystem — see Known Gaps.
- Path traversal attempts (resolved path escapes its permitted base) **must be rejected
  with a 400 error and logged** before any filesystem operation occurs. This applies to
  all path-validated operations; platform image paths are the explicit carved-out
  exception documented in Known Gaps.
- **No user-supplied string may reach a subprocess call directly.** There must be at
  least one validation layer between input and execution.
- Emulator binary paths are **never taken from request input**, query parameters, or
  profile fields. `get_install_path()` (`backend/service/utils/emulator_catalog.py`)
  resolves exactly two ways, by `install_type` from the per-slug TOML descriptor:
  a ROM pack resolves to its bundled directory under `library/system/roms/`, everything
  else resolves to the bundled project path `emulators/{slug}/{binary}`. There is no
  settings-based user-override tier and no system/registry-detected installation-path
  tier; both were removed as dead code in the Pydantic-descriptor refactor
  (`616bb4f`, 2026-08-04). No registry scanning. This rule has no exceptions.
- CLI arguments passed to emulator processes come from validated `Profile` config fields
  only. There is no freeform command construction anywhere in the codebase.
- All validated inputs must be checked again at the point of use — do not rely on prior
  validation in a different layer. (For image paths, see Known Gaps.)

---

## Process Spawning Rules

**Mandatory.**

- Emulator binary paths are never derived from request input. `get_install_path()`
  resolves to exactly one of two places depending on `install_type`: the bundled
  ROM pack directory, or the bundled `emulators/{slug}/{binary}` project path.
  No settings-based user override and no system-installation-path detection tier
  exist today (see Input Validation Rules above). No registry scanning.
- Arguments are constructed from validated `Profile` fields only. No string interpolation
  of raw user input into argument lists.
- A launch cooldown is enforced between successive requests to prevent rapid-fire
  spawning.
- All spawned processes are tracked and recorded in `LaunchHistory` (emulator, profile,
  the launch target as `game_item_bundle_id`, `app_item_bundle_id`, or
  `environment_item_id`, start time, exit code).
- On Windows, every spawned process is assigned to a Job Object. If Job Object creation
  or assignment fails, the launch is aborted — there is no unsandboxed fallback.
- Linux is out of scope (DECISIONS.md 2026-07-17). Process isolation is Windows Job
  Objects only.

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
- **Setting `ALLOW_NETWORK_ACCESS=true` creates a hard TLS dependency.** The session and
  CSRF cookies' `Secure` flag is derived directly from `ALLOW_NETWORK_ACCESS` (see AUTH.md
  § Token & Cookie Model) — enabling network access flips `Secure` to `True` regardless of
  whether a reverse proxy is actually in place. A browser will not send a `Secure` cookie
  back over plain HTTP, so without a TLS-terminating reverse proxy already running in front
  of the service, authentication silently breaks: login appears to succeed, but the cookie
  is dropped and every following request looks unauthenticated, producing an infinite
  re-login loop with no error message. Do not set `ALLOW_NETWORK_ACCESS=true` until TLS
  termination is actually in place.

### Network isolation is emulator-native

Network blocking is enforced at the emulator level, not via host OS firewall rules.
Each emulator is launched with its network adapter disabled or absent when
enable_networking is false on the active profile (the default). DOSBox-X launches
with the NE2000 adapter disabled via config. 86Box sets net_type = none to disable
connectivity without removing the emulated NIC. Console emulators (DuckStation, PCSX2, xemu, Mesen, Project64,
Flycast, RPCS3, Xenia) have no meaningful network capability and require no explicit blocking.

This approach requires no host elevation, cannot be accidentally bypassed by a
COM availability issue, and is harder for emulated software to work around than
a host firewall rule. Users who need network access for specific software can
enable it explicitly per profile.

### Emulator-specific

#### 86Box

Network connectivity is controlled via `net_type` in `[Network]` — written on every
launch. `none` disables connectivity without removing the emulated NIC (avoiding
Windows PnP re-detection). `slirp` enables user-mode NAT when `enable_networking = true`.
`pcap` (bridged, full IPX/NetBEUI support) is not currently exposed — see 86Box
documentation if you need it. `net_card` is never written by Peach 1UP; changing it
triggers Windows hardware detection.

---

## Destructive Operations

**Mandatory.**

Any endpoint that deletes or overwrites data requires a two-step confirmation:

1. The client requests a short-lived confirmation token from a dedicated endpoint.
2. The client includes the token in the destructive request.
3. The token expires after **60 seconds**. Expired tokens are rejected.

Applies to:

- Environment delete
- Software collection delete
- Snapshot delete
- Snapshot restore (overwrites the working image)
- Working image reset to base

All destructive operations are logged with the profile that initiated them, the resource
affected, and the timestamp.

---

## Secrets Handling

**Mandatory.**

- Each user row carries `identity_token_secret` (a server-only HMAC root key, generated
  once via `generate_identity_secret()` at account creation and never transmitted),
  `session_token_hash` (SHA-256 hash of the current session token; `NULL` means logged
  out), `session_token_expires_at`, and `session_token_ttl` (duration policy in minutes).
  Logging in mints `session_token = HMAC-SHA256(identity_token_secret, nonce + issued_at)`
  via `mint_session_token()` in `backend/core/identity.py` and persists only its hash —
  the plaintext token is never stored. The cookie value is `{user_id}.{session_token}`,
  set as `peach_token` — HttpOnly, `SameSite=Lax`, localhost only — and must never appear
  in logs, API responses, or version control. Sessions default to no expiry unless
  `User.session_token_ttl` is set. One active session per user by design: a new login
  overwrites `session_token_hash` directly, naturally invalidating any prior session —
  there is no separate token table and nothing to revoke or clean up. The owner account
  always requires PIN verification to switch into.
- PINs are hashed with Argon2id with a per-user random salt. Plaintext PINs are never
  stored or logged.
- HTTP middleware strips `Authorization` headers before any log output. Credentials must
  not appear in application logs under any circumstances.
- IGDB API keys and any other third-party API credentials are stored in `.env`
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
  `CreateProcessW`. Account-level isolation via a separate user account is not used.
- Every emulator launch is assigned to a fresh Job Object with kill-on-close,
  a per-era CPU rate floor and cap (`MIN_MAX_RATE`), and a per-era per-process memory
  cap (Qt emulators exempt via `skip_memory_limit` — see Known Limitations). CPU rate
  control may be skipped per emulator via `skip_cpu_limit = true` in the descriptor —
  every emulator except RPCS3 sets this today (RPCS3 is the only one that keeps the
  enforced CPU cap; see the AppContainer known-limitations entries for RPCS3 and xemu).
- The Python launcher sequence is: launch process (`CREATE_NEW_PROCESS_GROUP`) → create
  Job Object (named with the launched process's PID for per-launch uniqueness) → apply
  limits → `AssignProcessToJobObject` → breakaway retry if error 5.
- If `CreateProcessW` or `AssignProcessToJobObject` fails for any reason, **the launch
  is aborted**. There is no unsandboxed fallback.
- AppContainer is an additional isolation layer applied on top of Job Objects when
  `container_enabled = true` in the emulator descriptor. DOSBox-X, DuckStation, Flycast,
  Mesen, PCSX2, Project64, and Xenia all have `container_enabled = true`. 86Box, RPCS3,
  and xemu remain disabled — xemu and RPCS3 due to documented JIT/TCG incompatibility
  (both are `container_permanently_excluded`), 86Box pending further testing.
- The container-enable resolution and media-broker config that were previously duplicated
  across all five backends (86Box, DOSBox-X, xemu, Flycast, console) are now single
  implementations in `backend/service/utils/emulator_catalog.py`: `resolve_container_enabled()`
  resolves the effective `container_enabled` flag for a launch (profile/spec override, falling
  back to the catalog/settings value), and `build_media_broker_config()` builds the
  `SandboxConfig` broker-file list from it. A slug marked `container_permanently_excluded`
  in its TOML (`xemu`, see DECISIONS.md 2026-06-04, and `rpcs3`) rejects a profile-level
  `container_enabled` override at this layer — `resolve_container_enabled()` ignores the
  override and logs a warning rather than honouring it. `PATCH /{slug}/sandbox` already
  blocked enabling a permanently-disabled container via settings (`container_enabled is True`
  requested against a catalog `container_enabled: false` entry rejected with 400); this fix
  closes the separate profile-override path into the same subsystem, so both routes into
  container gating are now covered.
- For AppContainer-enabled emulators, process creation is delegated to `sandbox_host.exe`,
  which handles `SECURITY_CAPABILITIES`, `CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT`,
  and `ResumeThread`. The Python launcher wraps the resulting PID in a Job Object via the
  same breakaway-retry path.
- Emulators that have not yet passed the AppContainer test matrix ship with Job Object
  only and a visible warning in the Emulators page. The no-fallback abort policy still applies.

---

## Smart Detection: Hash-Based Media Identity Verification

`backend/service/utils/smart_media_detector` runs a full-file SHA-1 (with MD5/CRC32
fallback) lookup as the first tier of its detection pipeline, checked against a bundled
`hash_index.json` built offline from Redump/No-Intro community DAT files. A SHA-1 match
confirms the uploaded disc image's bytes are byte-for-byte identical to a known, community
verified dump of a specific title, this is a useful integrity signal (a corrupted or
incomplete rip will not match), not just a title-lookup convenience.

**Scope, what this actually covers today:**

- This runs during library ingest, when a media path is turned into a `GameItemBundle`
  library item (`backend/service/games/items.py`, `backend/api/routes/game_item_bundles.py`,
  `backend/service/utils/drive_utils.py`), not during the raw upload-streaming step itself.
  The chunked upload router (`/api/v1/software/uploads/*`) only writes bytes to disk, it does
  not hash or verify anything as part of the transfer.
- `AppItemBundle` (software app) uploads explicitly skip this entirely, per
  `backend/service/uploads/software_apps.py`'s own docstring: era detection and hashing are
  not run for apps, era stays `"unknown"` until a human sets it via the edit form.
- Hash-index coverage today is limited to two platforms, Sony PlayStation and Microsoft
  Xbox, see `smart_media_detector/README.md`'s Current coverage state section. Uploads for
  every other supported era fall through to lower-confidence, non-hash detection tiers
  regardless of whether the file is corrupted or tampered with.

**What this is not:** a live integrity-monitoring or tamper-detection mechanism. There is no
stored expected-hash-per-library-item to diff against on relaunch, no re-verification after
initial ingest, and no upload is blocked or rejected on a hash mismatch or a hash miss, a
non-matching file still ingests normally, just at lower confidence via the magic-byte,
structural, directory, or extension/size tiers. See the existing "hash_index.json is
committed but not independently reproducible" note below for the related caveat that the
source DAT files behind this index are not themselves in the repo.

---

## Known Limitations

### Job Object assignment on Windows 11 (nested job retry)

Windows 11 pre-assigns new child processes to an OS-managed Job Object. Attempting to
assign such a process to a second Job Object fails with error code 5 (access denied)
unless the process was launched with `CREATE_BREAKAWAY_FROM_JOB`.

The launcher handles this automatically in two stages:

1. The emulator is launched normally (`CREATE_NEW_PROCESS_GROUP`, no
   `CREATE_SUSPENDED`) without `CREATE_BREAKAWAY_FROM_JOB`.
2. If `AssignProcessToJobObject` fails with error 5 (access denied), the launcher
   kills the process and relaunches with `CREATE_BREAKAWAY_FROM_JOB` set, then
   assigns it to the Peach Job Object normally.

If the breakaway relaunch also fails (e.g. the process is inside a non-breakaway job set
by a third-party tool or a debugger), **the launch is aborted** and the error is surfaced
to the user. There is no unsandboxed fallback. Network isolation is unaffected because it
is emulator-native (network adapter disabled at the emulator config level).

The scan endpoint validates all user-supplied directory paths against an allowlist of configured base directories (LIBRARY_PATH, PROFILES_PATH) before any filesystem operation. This is a mandatory enforcement of the Input Validation Rules above. If none of these paths are configured in settings, scanning is blocked entirely. Media collections must reside under a configured base directory. This restriction must be carried forward to any future endpoint that accepts a directory or file path parameter.

All frontend requests are made via the `ApiClient` singleton with `credentials: 'include'`, ensuring the `peach_token` HttpOnly cookie is sent on every request.

#### Qt emulator process memory cap waived

JOB_OBJECT_LIMIT_PROCESS_MEMORY is not applied to Qt-based emulators
(86Box, DuckStation, PCSX2) or managed-runtime emulators (Mesen
.NET/Avalonia, xemu JIT heap). Qt's security initialisation triggers
STATUS_STACK_BUFFER_OVERRUN (0xC0000409) when this limit is applied
after process creation. Mesen and xemu pre-allocate heap at startup via
their managed runtimes and exhibit the same failure. Kill-on-close and
CPU rate control still apply. The skip_memory_limit flag in
config/emulators/ controls this per emulator. See DECISIONS.md
2026-06-01 for the revised rationale.

#### Job Object CPU rate control mutes host audio

JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP causes Windows to deprioritise
the host audio session while an emulator is running, muting system
audio. This is a side effect of the interim Job Objects isolation
model. AppContainer isolation (P9) removes this limitation. As a
workaround, CPU rate control can be disabled per emulator via
skip_cpu_limit = true in the emulator descriptor. DOSBox-X sets
this flag in its descriptor; the launcher honours it via
get_skip_cpu_limit() in emulator_catalog.py.

### AppContainer not yet validated for all emulators

Each emulator requires smoke test and full test matrix (OS × GPU × audio × controller ×
install path × locale) before `container_enabled` is set to true. Until then, that emulator
runs under Job Object only. See SCOPE.md P9-6 for the test matrix definition.

### Linux out of scope

Linux support (and the earlier cgroups/network-namespaces sandbox plan for it) was
removed from scope entirely — see DECISIONS.md 2026-07-17. Process isolation is
Windows Job Objects only; there is no Linux code path to secure.

### Drive image path is user-controlled per profile

Drive .img files are created at `{item.folder_path}/{item.slug}.img` — alongside the
software collection's media folder under `library/media/`. The slug is validated
at creation time. At launch time, `write_launch_conf` confirms the resolved
drive path is within the `library/` tree via `is_relative_to()`.
IMGMAKE receives the absolute path derived from the slug — no user string
reaches the IMGMAKE command directly.

### /auth/switch rate limiter is in-memory, TTL-swept

The IP-keyed rate limiter added for /auth/switch (backend/core/rate*limit.py)
stores attempt counts in a process-local dict. A distributed attack using
many unique source IPs no longer grows this dict unbounded: `check_and_record`
lazily sweeps keys whose window has fully elapsed since their last attempt,
at most once every 60 seconds, so the dict stays bounded by the volume of
\_recent* distinct keys rather than every key ever seen. Still matches the
existing in-memory-only precedent set by install_registry and
process_registry — no persistence requirement, and a backend restart clears
it.

`NOTE:` Peach 1UP is a household application first and foremost. We will add some basic
level protections but network safety is the users concern.

### hash_index.json is committed but not independently reproducible

The bundled `hash_index.json` used by the smart media detector (Tier-1 hash lookup) is
committed to the repo, but the No-Intro/Redump DAT files it was built from are not — they
are external, licensed datasets not included here. There is no way to regenerate or verify
this index from files in the repo alone. Flag only, no fix planned.

### CI runs tests but not pre-commit or husky

A GitHub Actions workflow (`.github/workflows/test.yml`) now runs on every push and pull
request to `main`: it regenerates constants and the OpenAPI/TypeScript types, runs the
backend `pytest --cov` suite on `windows-latest` (Python 3.14.6), and runs `vitest run
--coverage` for the frontend. There is still **no pre-commit hook or husky config**, and
the type-generation job regenerates and uploads artifacts rather than diffing them against
the committed `shared/types.ts` / `constants_generated.py`, so a stale-but-committed
generated file is not yet mechanically caught. `_check_router_parity()` in
`export_and_build_types.py` still guards the ROUTERS-vs-`main.py` mismatch at export time.

### Platform health check is a shallow integrity probe, not full validation

\_compute_status's integrity check confirms the working and base image files
exist and have a readable, non-empty header and tail (mirroring the cheap
footer-location check already used in vm/vhd.py). It does not parse or
validate the disk image format itself. A working image with a corrupted
middle section, or a header that matches by coincidence, will report
"healthy." This is an intentional cost/coverage tradeoff — full validation
would require format-specific parsing for every supported image type. If
corrupted-but-passing images become a real support burden, revisit with a
format-aware checksum or a guest-OS-level boot probe instead of a byte-range
check.

---

## Known Gaps

### Environment image path traversal relies on OS trust model

`base_image_path` and `working_image_path` on Environment records may be set by any user
with `can_manage_environment` permission and may point to any location on the host filesystem.
The runtime allowlist check against `OS_PATH` and `LIBRARY_PATH` was intentionally
removed to allow images on secondary drives, external volumes, and NAS shares outside
the configured library directories.

**Implications:** A user with `can_manage_environment` can cause the backend to read, copy,
or perform existence checks on files at arbitrary paths on the host. Mitigating factors:

- `can_manage_environment` is an explicit operator-granted permission, not a default for
  sub-accounts.
- The application runs as a local user, not a privileged service account.
- Operations on image paths are limited to copy, read, and existence check — no shell
  execution of image path values.

This gap is tracked and will be addressed in a future hardening pass, either by restoring
a configurable allowlist with an opt-out flag or by surfacing an explicit warning at
environment registration time.

### Library path configuration has no user-facing mechanism

The Library Paths settings panel was removed from the UI in session \[B4\]. LIBRARY_PATH, PROFILES_PATH, and ROMS_PATH can no longer be set through the frontend. The `config/settings.yaml` hand-edit fallback documented here previously has also been removed — settings are now DB-backed via `settings`, and no equivalent file exists to hand-edit. **There is currently no file-based or UI-based way for a user to reconfigure these three paths.**

The backend endpoint POST /api/v1/settings/library-path remains live and functional — it writes directly to `settings` via `set_path()`. It requires a `can_manage_settings`-permitted session, which in practice means calling the API directly (e.g. via curl with an authenticated cookie) rather than anything a typical user can do through the app.

⚠ **Flag — needs a decision, not fixed here:** the previous mitigation for this gap (hand-edit a config file) no longer has any equivalent at all, which is a regression from before the settings.yaml removal, not just a doc-accuracy fix. Replacement options (restore a UI panel, or document a supported API/CLI workflow for advanced users) need to be decided before this doc can point users anywhere concrete.

Highest-risk case: ROMS_PATH defaults to {project_root}/library/system/roms/86box. Users who supply 86Box ROMs from a zip extracted to a non-default location (the common case) will silently use the wrong ROM path after a clean install, with no documented way to correct it short of calling the API directly. The 86Box backend will raise a ROM path error at launch time rather than silently proceeding, so the failure is visible — but the fix path is now undocumented anywhere.

#### Mitigations

- ~~The README and first-run wizard should surface settings.yaml path configuration explicitly for non-standard installs.~~ No longer applicable — settings.yaml does not exist. Needs replacement guidance once the flag above is resolved.
- ~~The 86Box ROM path guidance card on the emulator detail page should include a note that the path can be overridden in settings.yaml.~~ Same — needs updated wording once a replacement mechanism exists.
- GeneralTab.tsx is orphaned and can be deleted when convenient.

#### TheGamesDB Metadata fetching

- TheGamesDB API key is passed as a URL query parameter (apikey=...) per the
  third-party API's own convention. It is never logged or returned in responses
  today, but if HTTP debug/trace logging is ever enabled for outbound httpx calls,
  this key would leak into logs via the request URL. Any future logging
  middleware must redact query params on outbound third-party requests, or
  scrub this specific param.

---

## Reporting Security Issues

Please report security vulnerabilities **privately** via
[GitHub Security Advisories](https://github.com/rymorrisj/peach_1up/security/advisories)
rather than opening a public issue. Public disclosure before a fix is available puts
other users at risk. Include a description of the vulnerability, steps to reproduce, and
any relevant environment details. We will respond as quickly as possible and coordinate
a disclosure timeline with you.
