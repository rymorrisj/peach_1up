# Peach 1UP: Security Architecture

## Overview

Peach 1UP is a locally hosted web application that spawns native OS processes, mounts
disk images, and manages emulator lifecycles. That creates an unusual attack surface for
a local app: a browser-facing HTTP service that crosses the process boundary into native
binary execution, filesystem access, and OS-level resource management. Every layer, from
input validation and process spawning through network binding, authentication, and
secrets handling, has explicit rules enforced at the implementation level rather than
left to convention.

Companion documents: [AUTH.md](AUTH.md) (auth flows and permission model),
[windows-sandbox.md](windows-sandbox.md) (Job Object and resource caps),
[DECISIONS.md](DECISIONS.md) (decision log).

---

## Threat Model

Realistic threats specific to this application:

- **Cross-origin requests from other browser tabs.** Any tab open in the browser can
  reach a localhost service. Without auth and CSRF protection, a malicious page could
  trigger launches, delete library entries, or read profile data.
- **Path traversal via user-supplied file paths.** Media paths, profile fields, and image
  paths are supplied by the user and could be crafted to escape permitted directories
  (e.g. `../../etc/passwd`, `..\..\Windows\System32`).
- **Arbitrary process execution via manipulated launch parameters.** If any portion of a
  subprocess call were constructed from unvalidated input, an attacker could inject
  arguments or substitute a different binary.
- **Privilege escalation via the emulator process tree.** Emulators that spawn child
  processes or load plugins could be used to break out of process isolation, so the
  emulator process tree must be fully contained by the isolation layer.
- **Unauthorised access to a shared library on a local network.** If the service is bound
  to `0.0.0.0` (remote access mode), other devices on the network can reach it. Without
  authentication this exposes the full library, settings, and launch capability.
- **Identity secret exposure.** Each user has a per-user HMAC root key
  (`identity_token_secret`) used to mint session tokens; the active session is tracked
  only as a `session_token_hash`, a SHA-256 digest that is not reversible to the token.
  If `identity_token_secret` leaks, an attacker can mint arbitrary valid session tokens
  for that one user until the secret is rotated, but the blast radius is a single account
  rather than a master secret that forges sessions for everyone. A leaked
  `session_token_hash` alone cannot be turned back into a usable token.

---

## Sequential integer primary keys (accepted tradeoff)

All primary keys in this codebase (`GameItemBundle.id`, `GameItem.id`,
`EnvironmentItem.id`, `ProfileItem.id`, and the rest) are sequential auto-increment
integers exposed directly in API route paths, for example
`/api/v1/game-item-bundle/{id}`, `/api/v1/game-item/{id}`,
`/api/v1/environment-items/{id}`, and `/api/v1/tags/{tag_id}/items/{item_id}`. These IDs
are enumerable by any authenticated user.

This is a standing, accepted tradeoff. A migration to opaque identifiers such as UUIDs is
flagged as a separate, larger future discussion if the threat model ever warrants
revisiting it.

---

## Authorisation and Permissions

Permission flags on sub-accounts. The authoritative list is `UserItemBase` in
[`backend/models/user.py`](../backend/models/user.py); this table must be kept in step
with it. See [AUTH.md](AUTH.md) § Permission Flags for the per-endpoint gating detail.

| Flag | What it controls |
| ---- | ---------------- |
| `can_launch_media` | Launch any permitted software collection (default: true) |
| `can_manage_environment` | Register or modify Environments, the Windows OS install workspaces. Was `can_edit_platforms` |
| `can_manage_game` | Create, edit, delete, or scan/import software collections and items, **and** create/modify/delete launch Profiles (the `ProfileItem` model in `routes/profiles.py`). Also the gate on `POST /api/v1/software/scan`. Was `can_edit_library`, renamed to `can_edit_software`, then to this name to reflect that it covers create/delete/scan-import, not just edits |
| `can_manage_media` | Add, edit, or remove Media (the archival audio/text/image/video domain) |
| `can_manage_app` | Add, edit, or remove Apps (the `AppItemBundle` domain) and gates the app-upload router |
| `can_manage_controllerMapping` | Create, edit, or delete controller mappings (System → Controllers) |
| `can_manage_settings` | Modify application settings |
| `can_manage_users` | Lets a sub-account edit its own `name` and reset its own PIN only. No capability over any other account, no self-delete, no create/delete of any sub-account. Owner-only to grant, like every flag here. Checked in addition to (not instead of) the `is_admin` path on the same two endpoints |
| `is_admin` | Edit/reset-pin/unlock/force-logout an existing sub-account, plus various admin-only settings/emulator/BIOS endpoints. Grants no other flag in this table implicitly; each is checked independently. Creating or deleting a sub-account requires `is_owner`, not `is_admin` |

`is_owner` bypasses every permission check (`require_permission` short-circuits for the
owner). It is not settable via the user create or patch API.

### PIN reset authorisation

`POST /api/v1/users/{id}/reset-pin`, as implemented in `users.py::reset_pin` and locked by
`test_users_create_delete_reset.py`:

- The **owner account's** PIN can never be reset through this endpoint by anyone.
  Owner-target requests are rejected with 403; owner PIN recovery is the local
  [`scripts/setup_admin_user.py`](../scripts/setup_admin_user.py) path only.
- The **owner** bypasses every other check and can reset any user's PIN regardless of lock
  state or target role.
- An **admin** can reset PINs only for accounts that are neither the owner nor another
  admin, i.e. regular/capped sub-accounts. Attempting to reset the owner's PIN or any
  admin's PIN, including their own, returns 403.
- A user holding `can_manage_users` can reset **its own** PIN via the same endpoint, but
  no one else's, and this self-service path is blocked with 403 while the account is
  locked, so a locked sub-account cannot self-recover.

A PIN reset does not revoke existing sessions; `session_token_hash` is left untouched. Use
`POST /api/v1/users/{id}/force-logout` to revoke.

### PIN security

- PINs are 4-6 digits, stored as [Argon2id](https://datatracker.ietf.org/doc/html/rfc9106)
  hashes with a per-user random salt.
- An optional app-level pepper (`PIN_PEPPER`) may be configured via
  `PATCH /api/v1/settings/pin-pepper`, stored in `.env`, outside SQLite. It is
  deliberately excluded from the general settings-patch endpoint.
- Plaintext PINs are never stored, logged, or returned by any API endpoint.
- 4 consecutive failures locks the account. The increment-and-lock is a single atomic
  `UPDATE`, so concurrent requests cannot each read the same pre-increment count and both
  slip past the threshold.
- `/auth/switch` is additionally rate limited per source IP (30 requests / 60s) via
  [`backend/core/rate_limit.py`](../backend/core/rate_limit.py).
- Owner lockout: run [`scripts/setup_admin_user.py`](../scripts/setup_admin_user.py)
  locally, which overwrites the owner record. No remote reset, no email recovery, no
  bypass flag. See Known Gaps for the current defect in this script.

### Content ratings and parental controls

- Ratings are ingested from NFO files, disc metadata, or filenames at scan time. The owner
  can override.
- Unrated is a first-class state. The `block_unrated_media` flag controls whether unrated
  items are visible to a sub-account.
- Each sub-account has a `max_content_rating` threshold. Items above the threshold are
  filtered at the query level, hidden entirely rather than surfaced and denied at launch.
- The rating filter **fails closed**. An unknown `max_content_rating` is rejected on write
  (`validate_max_content_rating`), and if a stored ceiling can no longer resolve to a
  known ordinal (e.g. a `rating_ordinals` change orphaned a previously valid value),
  `get_filtered_game_item_bundles` denies all rated content rather than silently dropping
  the cap. A collection whose own rating is unrecognised is likewise denied to a capped
  user, never passed through.
- Enforcement is server-side. Deny wins over any permission flag, with no override path.
- The rating scale is freetext on `GameItemBundle.content_rating` (also present on
  `AppItemBundle.content_rating`). Recommended: ESRB (E, E10+, T, M, AO) or PEGI (3, 7,
  12, 16, 18). The ordinal comparison map is configured via the `rating_ordinals` key in
  `settings`, falling back to defaults in
  [`dependencies.py`](../backend/core/dependencies.py). ⚠ No write path exists today, see
  Known Gaps.

---

## Input Validation Rules

**These are mandatory implementation rules, not guidelines.**

- Every file path accepted from any source, whether request body, query parameter, profile
  field, or settings value, **must be resolved and normalised** before any filesystem
  operation. Paths used for library scans, media scanning, and profile operations **must
  be validated against an allowlist** of permitted base directories: the configured
  `LIBRARY_PATH` and its derived sub-paths (`SOFTWARE_PATH`, `MEDIA_PATH`, `OS_PATH`,
  `ROMS_PATH`), `PROFILES_PATH`, and the application config directory. The allowlist and
  the `normalise_path` canonicaliser live in
  [`backend/service/utils/path_utils.py`](../backend/service/utils/path_utils.py).
  **Exception:** Environment image paths (`base_image_path`, `working_image_path`) may
  reside anywhere on the host filesystem, see Known Gaps.
- Path traversal attempts, where the resolved path escapes its permitted base, **must be
  rejected with a 400 error and logged** before any filesystem operation occurs. This
  applies to all path-validated operations; Environment image paths are the explicit
  carved-out exception documented in Known Gaps.
- **No user-supplied string may reach a subprocess call directly.** There must be at least
  one validation layer between input and execution.
- Emulator binary paths are **never taken from request input**, query parameters, or
  profile fields. `get_install_path()`
  ([`backend/service/utils/emulator_catalog.py`](../backend/service/utils/emulator_catalog.py))
  resolves exactly two ways, by `install_type` from the per-slug TOML descriptor: a ROM
  pack resolves to its bundled directory under `library/system/roms/`, and everything else
  resolves to the bundled project path `emulators/{slug}/{binary}`. There is no
  settings-based user-override tier and no system/registry-detected installation-path
  tier; both were removed as dead code in the Pydantic-descriptor refactor (`616bb4f`,
  2026-08-04). No registry scanning. This rule has no exceptions.
- CLI arguments passed to emulator processes come from validated `ProfileItem` config
  fields only. There is no freeform command construction anywhere in the codebase.
- All validated inputs must be checked again at the point of use. Do not rely on prior
  validation in a different layer. For image paths, see Known Gaps.

---

## Process Spawning Rules

**Mandatory.**

- Emulator binary paths are never derived from request input, per the `get_install_path()`
  rule above.
- Arguments are constructed from validated `ProfileItem` fields only. No string
  interpolation of raw user input into argument lists.
- A launch cooldown is enforced between successive requests to prevent rapid-fire
  spawning.
- All spawned processes are tracked and recorded in `LaunchHistory` (emulator, profile,
  the launch target as `game_item_bundle_id`, `app_item_bundle_id`, or
  `environment_item_id`, start time, exit code).
- On Windows, every spawned process is assigned to a Job Object. If Job Object creation or
  assignment fails, the launch is aborted. There is no unsandboxed fallback.
- Linux is out of scope ([DECISIONS.md](DECISIONS.md) 2026-07-17). Process isolation is
  Windows Job Objects only.

---

## Network Rules

**Mandatory.**

- The service binds to `127.0.0.1` by default. It must not bind to `0.0.0.0` unless
  `ALLOW_NETWORK_ACCESS` is explicitly set to `true` in settings.
- CORS is locked to the application origin by default. It must not be widened without an
  explicit operator decision.
- CSRF protection is required on all state-changing endpoints (POST, PUT, PATCH, DELETE).
- **Remote access is the operator's responsibility.** If remote access is needed, the
  recommended pattern is a reverse proxy with an external auth provider such as
  [Authentik](https://goauthentik.io/) or [Authelia](https://www.authelia.com/) in front
  of this service. Peach 1UP does not manage TLS termination or external routing.
- **Setting `ALLOW_NETWORK_ACCESS=true` creates a hard TLS dependency.** The session and
  CSRF cookies' `Secure` flag is derived directly from `ALLOW_NETWORK_ACCESS` (see
  [AUTH.md](AUTH.md) § Token & Cookie Model), so enabling network access flips `Secure` to
  `True` whether or not a reverse proxy is actually in place. A browser will not send a
  `Secure` cookie back over plain HTTP, so without TLS termination already running in
  front of the service, authentication silently breaks: login appears to succeed, the
  cookie is dropped, and every following request looks unauthenticated, producing an
  infinite re-login loop with no error message. Do not set `ALLOW_NETWORK_ACCESS=true`
  until TLS termination is in place.

### Network isolation is emulator-native

Network blocking is enforced at the emulator level, not via host OS firewall rules. Each
emulator is launched with its network adapter disabled or absent when `enable_networking`
is false on the active profile, which is the default. DOSBox-X launches with the NE2000
adapter disabled via `-set ne2000=false`. 86Box sets `net_type = none` to disable
connectivity without removing the emulated NIC. The console emulators (DuckStation, PCSX2,
xemu, Mesen, Project64, Flycast, RPCS3, Xenia) have no meaningful network capability and
require no explicit blocking.

This approach requires no host elevation, cannot be accidentally bypassed by a COM
availability issue, and is harder for emulated software to work around than a host
firewall rule. Users who need network access for specific software can enable it
explicitly per profile.

### 86Box network specifics

Network connectivity is controlled via `net_type` in `[Network]`, written on every launch.
`none` disables connectivity without removing the emulated NIC, avoiding Windows PnP
re-detection. `slirp` enables user-mode NAT when `enable_networking = true`. `pcap`
(bridged, full IPX/NetBEUI support) is not currently exposed; see the
[86Box documentation](https://86box.readthedocs.io/) if you need it. `net_card` is never
written by Peach 1UP, because changing it triggers Windows hardware detection.

---

## Destructive Operations

**Mandatory.**

Any endpoint that deletes or overwrites data requires a two-step confirmation:

1. The client requests a short-lived confirmation token from a dedicated endpoint.
2. The client includes the token in the destructive request.
3. The token expires after **60 seconds** (`TOKEN_TTL` in
   [`confirmation_tokens.py`](../backend/service/utils/confirmation_tokens.py)). Expired
   tokens are rejected.

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
  `session_token_hash` (SHA-256 hash of the current session token, `NULL` meaning logged
  out), `session_token_expires_at`, and `session_token_ttl` (duration policy in minutes).
  Logging in mints `session_token = HMAC-SHA256(identity_token_secret, nonce + issued_at)`
  via `mint_session_token()` in
  [`backend/core/identity.py`](../backend/core/identity.py) and persists only its hash;
  the plaintext token is never stored. The cookie value is `{user_item_id}.{session_token}`,
  set as `peach_token` with `HttpOnly` and `SameSite=Lax`, and must never appear in logs,
  API responses, or version control. Sessions default to no server-side expiry unless
  `UserItem.session_token_ttl` is set, though the cookie itself carries a 30-day
  `max_age` in that case. One active session per user by design: a new login overwrites
  `session_token_hash` directly, invalidating any prior session, so there is no separate
  token table and nothing to revoke or clean up. The owner account always requires PIN
  verification to switch into.
- PINs are hashed with Argon2id with a per-user random salt. Plaintext PINs are never
  stored or logged.
- Request logging is deliberately minimal: `RequestLoggingMiddleware` emits only method,
  path, status code, and duration, so no request or response headers, and no bodies, ever
  reach the log. Credentials must not appear in application logs under any circumstances,
  and any future logging middleware that widens what is captured must redact
  `Authorization`, `Cookie`, and outbound third-party query parameters explicitly.
- IGDB, TheGamesDB, and any other third-party API credentials are stored in `.env` only.
  They are never committed to version control, never returned by the API, and never
  logged. See the TheGamesDB query-parameter caveat in Known Gaps.

---

## SQLite Security Notes

SQLite does not enforce foreign key constraints by default. This must be corrected on
every connection.

**Required:** register a SQLAlchemy `connect` event listener that executes
`PRAGMA foreign_keys=ON` on every new connection. Do not assume this is set by default or
by the ORM. The listener must be in place before any schema migration or data operation
runs. It is registered in
[`backend/core/database.py`](../backend/core/database.py), and separately in
[`scripts/setup_admin_user.py`](../scripts/setup_admin_user.py), which builds its own
standalone engine.

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

## Windows-specific process rules

**Mandatory.**

- All emulator processes on Windows are launched under the current user account via
  `CreateProcessW`. Account-level isolation via a separate user account is not used.
- Every emulator launch is assigned to a fresh Job Object with kill-on-close, a per-era
  CPU rate floor and cap (`MIN_MAX_RATE`), and a per-era per-process memory cap. Both
  resource caps are individually waivable per emulator via `skip_cpu_limit` and
  `skip_memory_limit` in the descriptor. **Every descriptor in
  [`config/emulators/`](../config/emulators/) currently sets both to `false`**, so both
  the CPU rate cap and the memory cap are enforced for every emulator as shipped, and
  kill-on-close is not the only Job Object control in force. See the Known Limitations
  section below for the history of these two flags and the current per-emulator status,
  and [windows-sandbox.md](windows-sandbox.md) for the per-era numbers the caps apply.
- **`skip_cpu_limit` is honoured on both isolation layers.** Until the P9 follow-up
  hardening pass it was honoured only by the Python-side Job Object in `launcher.py`.
  `sandbox_host.exe` had no representation of the flag at all: `JobConfig` had no such
  field, `app_container.py` never read it when building the container payload, and
  `job.cpp` applied CPU rate control unconditionally. Every `container_enabled` emulator
  therefore still received the CPU cap through the container path despite setting
  `skip_cpu_limit = true`, which reinstated the host-audio-muting bug the flag exists to
  prevent and negated the P9-2 MinRate floor. The flag now travels in the
  `sandbox_host.exe` stdin payload as an explicit `job_config.skip_cpu_limit` boolean and
  is resolved through `get_skip_cpu_limit()`, so the per-emulator settings override
  written by `PATCH /{slug}/sandbox` applies to both layers. `skip_memory_limit` is
  resolved the same way, through `get_skip_memory_limit()`.
- The Python launcher sequence is: launch the process suspended
  (`CREATE_NEW_PROCESS_GROUP | CREATE_SUSPENDED`, so it cannot run before limits are in
  force) → create the Job Object, named with the launched process's PID for per-launch
  uniqueness → apply limits → `AssignProcessToJobObject` → breakaway retry on error 5 →
  `ResumeThread`.
- If `CreateProcessW` or `AssignProcessToJobObject` fails for any reason, **the launch is
  aborted**. There is no unsandboxed fallback, and a failed process is terminated while
  still suspended rather than resumed.
- AppContainer is an additional isolation layer applied on top of Job Objects when
  `container_enabled = true` in the emulator descriptor. DOSBox-X, DuckStation, Flycast,
  Mesen, PCSX2, Xenia, and xemu all have `container_enabled = true`. 86Box, Project64, and
  RPCS3 remain disabled: RPCS3 due to documented JIT/TCG incompatibility
  (`container_permanently_excluded`); Project64 is confirmed incompatible for a separate,
  unrelated reason, it crashes on launch under AppContainer (`Main.cpp:99`, exit_code=1)
  even with memory and CPU limits raised, root cause unknown, and is also
  `container_permanently_excluded`; 86Box works under AppContainer in some environments but
  not all, is disabled by default, and is not being investigated further. xemu was
  previously excluded on a suspected QEMU TCG/DeviceIoControl incompatibility; that
  diagnosis was wrong, the real cause was memory/CPU limits too small for its JIT heap, and
  it is now enabled with adequate limits.
- The container-enable resolution and media-broker config that were previously duplicated
  across the emulator backends are now single implementations in
  [`emulator_catalog.py`](../backend/service/utils/emulator_catalog.py):
  `resolve_container_enabled()` resolves the effective `container_enabled` flag for a
  launch (profile or spec override, falling back to the catalog/settings value), and
  `build_media_broker_config()` builds the `SandboxConfig` broker-file list from it.
  Backends whose broker needs are more than "expose the read-only media file"
  (`box86.py`, `dosbox.py`, `xemu.py`) still build their own `SandboxConfig`. A slug marked
  `container_permanently_excluded` in its TOML (`project64`, `rpcs3`) rejects a
  profile-level `container_enabled` override at this layer: `resolve_container_enabled()`
  ignores the override and logs a warning rather than honouring it. `PATCH /{slug}/sandbox`
  already blocked enabling a permanently disabled container via settings (a
  `container_enabled is True` request against a catalog `container_enabled: false` entry is
  rejected with 400), so both routes into container gating are now covered.
- For AppContainer-enabled emulators, process creation is delegated to
  `sandbox_host.exe`, which handles `SECURITY_CAPABILITIES`,
  `CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT`, and `ResumeThread`. The Python
  launcher wraps the resulting PID in a Job Object via the same breakaway-retry path, with
  `apply_limits=False`: `sandbox_host.exe`'s own Job Object already applied the numeric
  limits before the process was resumed, so the Python-side job exists only as a teardown
  handle and for launch-history reporting.
- Emulators that have not yet passed the AppContainer test matrix ship with Job Object
  only and a visible warning in the Emulators page. The no-fallback abort policy still
  applies.

The Job Object and AppContainer implementation lives in the vendored
[`wincage`](../services/vendor/wincage/) package: `wincage/process.py` and `wincage/job.py`
for the Python side, `wincage/src/container.cpp`, `job.cpp`, and `main.cpp` for
`sandbox_host.exe`.

---

## Smart Detection: hash-based media identity verification

Media detection runs a full-file SHA-1 lookup (with MD5/CRC32 fallback) as the first tier
of its pipeline, checked against a bundled `hash_index.json` built offline from
Redump/No-Intro community DAT files. A SHA-1 match confirms the uploaded disc image's
bytes are byte-for-byte identical to a known, community-verified dump of a specific title,
which is a useful integrity signal (a corrupted or incomplete rip will not match) and not
only a title-lookup convenience.

The detection pipeline now lives in the vendored
[`formatscout`](../services/vendor/formatscout/) package
(`formatscout/hashing/`, `formatscout/detector.py`), with the Peach-specific resolvers
remaining in
[`backend/service/utils/detection/`](../backend/service/utils/detection/). It was
previously `backend/service/utils/smart_media_detector`.

**Scope, what this actually covers today:**

- It runs during library ingest, when a media path is turned into a `GameItemBundle`
  library item ([`backend/service/games/items.py`](../backend/service/games/items.py),
  [`backend/api/routes/game_item_bundles.py`](../backend/api/routes/game_item_bundles.py),
  [`backend/service/utils/drive_utils.py`](../backend/service/utils/drive_utils.py)), not
  during the raw upload-streaming step. The chunked upload router
  (`/api/v1/software/uploads/*`) only writes bytes to disk; it does not hash or verify
  anything as part of the transfer.
- `AppItemBundle` (software app) uploads skip this entirely, per
  [`backend/service/uploads/software_apps.py`](../backend/service/uploads/software_apps.py)'s
  own docstring: era detection and hashing are not run for apps, and era stays `"unknown"`
  until a human sets it via the edit form.
- Hash-index coverage today is limited to two platforms, Sony PlayStation (`ps1`) and
  Microsoft Xbox (`xbox`), per the "Current coverage state" section of
  [`services/vendor/formatscout/README.md`](../services/vendor/formatscout/README.md).
  Every other supported era (`win95`, `win98`, `winxp`, `ps2`, `nes`, `snes`, `n64`,
  `dreamcast`) has zero hash-index coverage and falls through to the lower-confidence
  magic-byte, structural, directory, and extension/size tiers regardless of whether the
  file is corrupted or tampered with. Building a new index from DAT files is a manual
  `python -m formatscout.hashing.build_index` step with no ingestion automation.

**What this is not:** a live integrity-monitoring or tamper-detection mechanism. There is
no stored expected-hash-per-library-item to diff against on relaunch, no re-verification
after initial ingest, and no upload is blocked or rejected on a hash mismatch or miss. A
non-matching file still ingests normally, just at lower confidence. See the
"hash_index.json is committed but not independently reproducible" note below for the
related caveat that the source DAT files behind the index are not in the repo.

---

## Path allowlist enforcement on scan endpoints

The scan endpoint validates all user-supplied directory paths against an allowlist of
configured base directories (`LIBRARY_PATH`, `PROFILES_PATH`) before any filesystem
operation. This is a mandatory enforcement of the Input Validation Rules above. If none of
these paths are configured in settings, scanning is blocked entirely. Media collections
must reside under a configured base directory. This restriction must be carried forward to
any future endpoint that accepts a directory or file path parameter.

All frontend requests are made via the `ApiClient` singleton with
`credentials: 'include'`, so the `peach_token` HttpOnly cookie is sent on every request.

---

## Known Limitations

### Job Object assignment on Windows 11 (nested job retry)

Windows 11 pre-assigns new child processes to an OS-managed Job Object. Attempting to
assign such a process to a second Job Object fails with error code 5 (access denied)
unless the process was launched with `CREATE_BREAKAWAY_FROM_JOB`.

The launcher handles this automatically in two stages:

1. The emulator is launched suspended (`CREATE_NEW_PROCESS_GROUP | CREATE_SUSPENDED`)
   without `CREATE_BREAKAWAY_FROM_JOB`.
2. If `AssignProcessToJobObject` fails with error 5, the launcher terminates the still
   suspended process and relaunches with `CREATE_BREAKAWAY_FROM_JOB` set, then assigns it
   to the Peach Job Object normally.

If the breakaway relaunch also fails (e.g. the process is inside a non-breakaway job set by
a third-party tool or a debugger), **the launch is aborted** and the error is surfaced to
the user. There is no unsandboxed fallback. Network isolation is unaffected because it is
emulator-native, with the network adapter disabled at the emulator config level.

### Job Object resource cap waivers (skip_memory_limit, skip_cpu_limit)

Two Job Object caps apply per launch: a per-process memory cap
(`JOB_OBJECT_LIMIT_PROCESS_MEMORY`) and a CPU rate cap
(`JOB_OBJECT_CPU_RATE_CONTROL_MIN_MAX_RATE`, falling back to
`JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP` below Windows 10 1607 build 14393 or if
`SetInformationJobObject` fails). Both are sized per era in `eras.yaml` and can be waived
per emulator via `skip_memory_limit` and `skip_cpu_limit` in that emulator's TOML
descriptor, resolved through `get_skip_memory_limit()` and `get_skip_cpu_limit()` in
`emulator_catalog.py`.

Two mechanisms motivated waiving the memory cap in the past:

- Qt's security initialisation (platform plugin startup) fast-fails with
  `STATUS_STACK_BUFFER_OVERRUN` (0xC0000409) when `JOB_OBJECT_LIMIT_PROCESS_MEMORY` is
  applied post-creation via `AssignProcessToJobObject`. Confirmed on 86Box 5.3 / Qt
  5.15.18 on Windows 11 (DECISIONS.md 2026-05-19).
- Managed-runtime and JIT emulators (Mesen on .NET/Avalonia, xemu's pre-allocated JIT
  heap) pre-allocate heap at startup and can hit the same fast-fail if the era's memory
  cap is sized too small for that pre-allocation (DECISIONS.md 2026-06-01).

The CPU cap was waived in the past as a workaround for CPU rate control deprioritising
the host audio session while an emulator runs, muting system audio. The recorded fix for
that (DECISIONS.md 2026-05-21) is the switch from `HARD_CAP` to `MIN_MAX_RATE` with a
non-zero `MinRate` reserving a floor for the audio thread, not a blanket waiver of the
cap.

**Current status: every descriptor in [`config/emulators/`](../config/emulators/) sets
both flags to `false`.** Neither cap is waived for any emulator today, both are enforced
as shipped. This is a change from the 2026-05-19 through 2026-06-01 period, when several
descriptors set one or both flags to `true` for the reasons above. No DECISIONS.md entry
records when or why each descriptor was reverted to `false`, so the notes below state
only what each TOML and its own `known_limitations` block actually say, not what is
inferred from the emulator's toolkit.

| Emulator | `container_enabled` | `skip_cpu_limit` | `skip_memory_limit` | Notes |
| --- | --- | --- | --- | --- |
| 86Box | false | false | false | Disabled by default pending further AppContainer testing across environments (`container_hardcap_note` in `86box.toml` says it works in some environments, not all). Historically in the Qt `STATUS_STACK_BUFFER_OVERRUN` group above (DECISIONS.md 2026-05-19); the memory cap is enforced today. |
| DOSBox-X | true | false | false | No skip_* history recorded in DECISIONS.md or the descriptor. |
| DuckStation | true | false | false | Historically in the same Qt `STATUS_STACK_BUFFER_OVERRUN` group as 86Box (DECISIONS.md 2026-05-19); enforced today. |
| Flycast | true | false | false | No skip_* history recorded. Separately, `flycast.toml`'s own `known_limitations` entry still describes AppContainer as disabled for the current version for more testing, which does not match `container_enabled = true` in the same file; this predates the skip_* flags and is unrelated to them. |
| Mesen | true | false | false | `skip_memory_limit = true` previously papered over an undersized era memory cap colliding with the managed .NET/Avalonia runtime's startup heap pre-allocation (DECISIONS.md 2026-06-01 names Mesen in this group). It is `false` today with no crash reported, consistent with the underlying cap sizing having been fixed rather than the check being waived. |
| PCSX2 | true | false | false | Historically in the same Qt `STATUS_STACK_BUFFER_OVERRUN` group as 86Box and DuckStation (DECISIONS.md 2026-05-19); enforced today. |
| Project64 | false (`container_permanently_excluded = true`) | false | false | Crashes on launch under AppContainer (`Main.cpp:99`, exit_code=1) even with memory and CPU limits raised; root cause unresolved and unrelated to either skip flag. Permanently excluded from AppContainer regardless of any override; Job Object caps are the only active isolation layer and both are enforced. |
| RPCS3 | false | false | false | Disabled today per its own `known_limitations` entry (JIT/TCG incompatibility, described as the same class of limitation as xemu), but `container_permanently_excluded = false` in `rpcs3.toml`, unlike Project64. Job Object caps are enforced. |
| xemu | true | false | false | Previously excluded from AppContainer on a suspected QEMU TCG/DeviceIoControl incompatibility; the actual cause recorded in `xemu.toml`'s own `known_limitations` entry ("AppContainer previously disabled due to undersized limits") was memory and CPU limits sized too small for its pre-allocated JIT heap. Re-enabled once the era's limits were sized adequately; no skip flag was needed to fix it. |
| Xenia | true | false | false | No skip_* history recorded. |
| 86box-roms | n/a | false | false | Not a launchable process (`install_type = "rom_pack"`); both flags are set only for schema uniformity, per the comment in `86box-roms.toml` and `emulator_descriptor.py`. |

If you are debugging host audio muting on a container-enabled emulator, note that
`sandbox_host.exe` ignored `skip_cpu_limit` entirely before the P9 follow-up hardening
pass, so the CPU cap was applied by the container path regardless of the descriptor. See
the `skip_cpu_limit` note under Windows-specific process rules above for how that was
fixed. Since neither flag is waived for any emulator today, treat that as the baseline:
if a future regression needs one waived again, record the reason in DECISIONS.md in the
same change that flips the TOML value, so this table does not go stale the way it did
between 2026-06-01 and today.

### AppContainer not yet validated for all emulators

Each emulator requires a smoke test and the full test matrix (OS × GPU × audio ×
controller × install path × locale) before `container_enabled` is set to true. Until then
that emulator runs under Job Object only. See SCOPE.md P9-6 for the test matrix
definition.

### Linux out of scope

Linux support, and the earlier cgroups/network-namespaces sandbox plan for it, was removed
from scope entirely; see [DECISIONS.md](DECISIONS.md) 2026-07-17. Process isolation is
Windows Job Objects only, and there is no Linux code path to secure.

### Drive image path is user-controlled per profile

Drive `.img` files are created at `{item.folder_path}/{item.slug}.img`, alongside the
software collection's media folder under `library/media/`. The slug is validated at
creation time. At launch time, `_build_drive_mount_lines` confirms the resolved drive path
is within the `library/` tree via `is_relative_to()` after `normalise_path()`
canonicalisation. `IMGMAKE` receives the absolute path derived from the slug, so no user
string reaches the `IMGMAKE` command directly.

### /auth/switch rate limiter is in-memory, TTL-swept

The IP-keyed rate limiter for `/auth/switch`
([`backend/core/rate_limit.py`](../backend/core/rate_limit.py)) stores attempt counts in a
process-local dict. A distributed attack using many unique source IPs no longer grows this
dict unbounded: `check_and_record` lazily sweeps keys whose window has fully elapsed since
their last attempt, so the dict stays bounded by the volume of *recent* distinct keys
rather than every key ever seen. It also records only allowed attempts, so a client
hammering past the limit cannot keep pushing its own window forward. This matches the
in-memory-only precedent set by `install_registry` and `process_registry`: no persistence
requirement, and a backend restart clears it.

`NOTE:` Peach 1UP is a household application first and foremost. We add a basic level of
protection, but network safety is the user's concern.

### hash_index.json is committed but not independently reproducible

The bundled `hash_index.json` used for tier-1 hash lookup
(`services/vendor/formatscout/formatscout/hashing/hash_index.json`) is committed to the
repo, but the No-Intro/Redump DAT files it was built from are not, being external,
licensed datasets. There is no way to regenerate or verify this index from files in the
repo alone. Flag only, no fix planned.

### CI runs tests but not pre-commit or husky

A GitHub Actions workflow ([`.github/workflows/test.yml`](../.github/workflows/test.yml))
runs on every push and pull request to `main`: it regenerates constants and the
OpenAPI/TypeScript types, runs the backend `pytest --cov` suite on `windows-latest`
(Python 3.14.6), and runs `vitest run --coverage` for the frontend. A separate
[`codeql.yml`](../.github/workflows/codeql.yml) workflow provides static analysis.

There is still **no pre-commit hook or husky config**, and the type-generation job
regenerates and uploads artifacts rather than diffing them against the committed
`shared/types.ts` and `constants_generated.py`, so a stale-but-committed generated file is
not yet mechanically caught. `_check_router_parity()` in `export_and_build_types.py` still
guards the ROUTERS-versus-`main.py` mismatch at export time.

### Environment health check is a shallow integrity probe, not full validation

`_probe_image_integrity` in
[`backend/service/environments/environments.py`](../backend/service/environments/environments.py)
confirms the working image file is non-empty and that its first and last 512 bytes (where
a VHD footer would live, per `vm/vhd.py`) are readable. `_environment_files_present`
additionally requires both the working and base image files to exist. Neither parses or
validates the disk image format itself, so a working image with a corrupted middle
section, or a header that matches by coincidence, will report healthy.

This is an intentional cost/coverage tradeoff, since full validation would require
format-specific parsing for every supported image type. If corrupted-but-passing images
become a real support burden, revisit with a format-aware checksum or a guest-OS-level
boot probe instead of a byte-range check.

---

## Known Gaps

### Environment image path traversal relies on OS trust model

`base_image_path` and `working_image_path` on Environment records may be set by any user
with `can_manage_environment` permission and may point to any location on the host
filesystem. The runtime allowlist check against `OS_PATH` and `LIBRARY_PATH` was
intentionally removed to allow images on secondary drives, external volumes, and NAS
shares outside the configured library directories.

**Implications:** a user with `can_manage_environment` can cause the backend to read,
copy, or perform existence checks on files at arbitrary paths on the host. Mitigating
factors:

- `can_manage_environment` is an explicit operator-granted permission, not a default for
  sub-accounts.
- The application runs as a local user, not a privileged service account.
- No image path value is ever passed to a shell. There is no command construction from
  these fields.

**Not covered by the bullets above: the AppContainer layer also writes ACLs at these
paths.** This bullet list previously claimed operations were limited to copy, read, and
existence check, which stopped being accurate when P9 layered AppContainer on top of Job
Objects. A container-enabled launch passes image paths to `sandbox_host.exe` as broker
files, and `container.cpp`'s `grant_directory` applies a **permanent, inheritable DACL
grant** to the AppContainer SID via `TreeSetNamedSecurityInfoW`, rewriting the ACL of every
object in the tree beneath the path. Nothing reverts it on process exit; see
[`services/vendor/wincage/README.md`](../services/vendor/wincage/README.md), "DACL grants
are permanent on the path". The reachable operation set on an arbitrary user-chosen path
therefore includes durable ACL modification, not just reads.

Current state after the P9 follow-up hardening pass:

- **DOSBox-X Environment launches (`working_image_path`) no longer take a directory-level
  grant.** The grant was narrowed to a traverse-only (`access="x"`, `mode="secure"`,
  non-inheriting) ACE on the parent node plus an `rw` ACE on the image file itself.
  DOSBox-X only ever opens that one file for an environment launch, so the previous
  recursive `rw` grant on the whole parent tree was not required by any emulator
  operation.
- **Paths are canonicalised at the point of use** via `normalise_path` before becoming a
  DACL target, so a symlink or junction planted under the chosen directory cannot redirect
  the grant to a tree the user never named. This is canonicalisation only; it deliberately
  rejects no location, since arbitrary Environment image locations remain permitted by
  design.
- **Per-item drive images (`drive_image_path`) keep their recursive parent-directory
  grant**, because DOSBox-X creates the `.img` in place via `IMGMAKE` on first launch and
  needs `FILE_ADD_FILE` on the parent. That path is separately containment-checked against
  `library/` in `_build_drive_mount_lines`, so its grant target is always inside the
  library tree.

`BrokerFile.mode` accepts `"grant"`, `"secure"`, and `"inherit"`; only `grant` and
`secure` modify a filesystem ACL, and `grant` is the recursive one. See
[`services/vendor/wincage/README.md`](../services/vendor/wincage/README.md) for the
authoritative per-mode semantics, which belong with the package rather than here.
- **Still open:** any other backend that passes an unvalidated Environment path as a
  `mode = "grant"` broker file inherits the original recursive-grant behaviour.
  `container.cpp`'s `grant_directory` also carries a standing `TODO` that per-user ACEs
  accumulate on shared grant directories with no cleanup on user deletion.

This gap is tracked and will be addressed in a future hardening pass, either by restoring
a configurable allowlist with an opt-out flag or by surfacing an explicit warning at
environment registration time.

### Owner lockout recovery script fails to run

[`scripts/setup_admin_user.py`](../scripts/setup_admin_user.py) imports
`from backend.models.user import User`, but
[`backend/models/user.py`](../backend/models/user.py) defines only `UserItem`,
`UserItemBase`, and `UserItemRead`. There is no `User` symbol and no alias, so the script
raises `ImportError` before touching the database.

This is the **only** documented owner PIN recovery path (see the PIN security section
above and [AUTH.md](AUTH.md) Flow 14). Until it is fixed, an owner who forgets their PIN or
trips the 4-attempt lockout has no supported recovery route. Flagged here rather than
fixed, since this is a documentation audit.

Related, and true even once the import is fixed: the script does not clear
`session_token_hash`, so a session issued before an owner PIN reset stays valid until it
expires or is explicitly revoked.

### No recovery key exists

Earlier revisions of this document and of [AUTH.md](AUTH.md) described a recovery key
"shown once at first run" and "stored as an Argon2id hash only". No such mechanism exists
in the codebase: there is no recovery-key column, generation, display, or verification
path anywhere in `backend/` or `frontend/src/`. The claim has been removed from both
documents rather than restated. If a recovery key is still wanted, it needs to be designed
and built, not documented.

### Library path configuration has no user-facing mechanism

The Library Paths settings panel was removed from the UI in session [B4]. `LIBRARY_PATH`,
`PROFILES_PATH`, and `ROMS_PATH` can no longer be set through the frontend. The
`config/settings.yaml` hand-edit fallback documented here previously has also been
removed; settings are now DB-backed via `settings`, and no equivalent file exists to
hand-edit. **There is currently no file-based or UI-based way for a user to reconfigure
these three paths.**

The backend endpoint `POST /api/v1/settings/library-path` remains live and functional,
writing directly to `settings` via `set_path()`. It requires a
`can_manage_settings`-permitted session, which in practice means calling the API directly
(e.g. via curl with an authenticated cookie) rather than anything a typical user can do
through the app.

⚠ **Flag, needs a decision, not fixed here:** the previous mitigation for this gap
(hand-edit a config file) no longer has any equivalent, which is a regression from before
the settings.yaml removal rather than just a doc-accuracy fix. Replacement options
(restore a UI panel, or document a supported API/CLI workflow for advanced users) need to
be decided before this doc can point users anywhere concrete.

Highest-risk case: `ROMS_PATH` defaults to `{project_root}/library/system/roms/86box`.
Users who supply 86Box ROMs from a zip extracted to a non-default location, the common
case, will silently use the wrong ROM path after a clean install, with no documented way to
correct it short of calling the API directly. The 86Box backend raises a ROM path error at
launch time rather than silently proceeding, so the failure is visible, but the fix path is
now undocumented.

**Mitigations:**

- ~~The README and first-run wizard should surface settings.yaml path configuration
  explicitly for non-standard installs.~~ No longer applicable, settings.yaml does not
  exist. Needs replacement guidance once the flag above is resolved.
- ~~The 86Box ROM path guidance card on the emulator detail page should include a note
  that the path can be overridden in settings.yaml.~~ Same, needs updated wording once a
  replacement mechanism exists.
- `GeneralTab.tsx` is orphaned and can be deleted when convenient.

### TheGamesDB metadata fetching leaks its key into any URL logging

The TheGamesDB API key is passed as a URL query parameter (`apikey=...`) per the
third-party API's own convention. It is never logged or returned in responses today, but
if HTTP debug/trace logging were ever enabled for outbound `httpx` calls, the key would
leak into logs via the request URL. Any future logging middleware must redact query params
on outbound third-party requests, or scrub this specific param.

---

## Reporting Security Issues

Please report security vulnerabilities **privately** via
[GitHub Security Advisories](https://github.com/rymorrisj/peach_1up/security/advisories)
rather than opening a public issue. Public disclosure before a fix is available puts other
users at risk. Include a description of the vulnerability, steps to reproduce, and any
relevant environment details. We will respond as quickly as possible and coordinate a
disclosure timeline with you.
