# Security Architecture

Peach 1UP is a locally hosted web app that spawns native processes, mounts disk images, and
manages emulator lifecycles. That is an unusual attack surface for a local app: a
browser-facing HTTP service crossing into native binary execution, filesystem access, and
OS-level resource management. The rules below are enforced at the implementation level, not
left to convention.

Companion documents: [AUTH.md](AUTH.md) (auth flows and permission model) ·
[windows-sandbox.md](windows-sandbox.md) (Job Object and resource caps) ·
[CHANGELOG.md](../CHANGELOG.md) (decision history).

## Threat model

| Threat | Why it applies here |
|---|---|
| Cross-origin requests from other browser tabs | Any open tab can reach a localhost service. Without auth and CSRF, a malicious page could trigger launches, delete library entries, or read profile data. |
| Path traversal via user-supplied paths | Media paths, profile fields, and image paths come from the user and could be crafted to escape permitted directories. |
| Arbitrary process execution via launch parameters | If any part of a subprocess call were built from unvalidated input, an attacker could inject arguments or substitute a binary. |
| Privilege escalation through the emulator process tree | Emulators that spawn children or load plugins could break out, so the whole tree must stay contained. |
| Unauthorised access to a shared library on a LAN | With `ALLOW_NETWORK_ACCESS` on, other devices can reach the service. Without auth that exposes the full library, settings, and launch capability. |
| Identity secret exposure | Each user has a per-user HMAC root key (`identity_token_secret`); the active session is tracked only as a SHA-256 `session_token_hash`. A leaked root key lets an attacker mint valid tokens for **that one user** until it is rotated, not for everyone. A leaked hash cannot be turned back into a usable token. |

### Accepted tradeoff: sequential integer primary keys

Every primary key (`GameItemBundle.id`, `GameItem.id`, `EnvironmentItem.id`,
`ProfileItem.id`, and the rest) is a sequential auto-increment integer exposed directly in
route paths, so IDs are enumerable by any authenticated user. This is a standing accepted
tradeoff. Migrating to opaque identifiers is a separate, larger discussion if the threat
model ever warrants it.

## Authorisation

Permission flags on sub-accounts. The authoritative list is `UserItemBase` in
[`models/user.py`](../backend/models/user.py); keep this in step with it. See
[AUTH.md](AUTH.md) for per-endpoint detail.

| Flag | Controls |
|---|---|
| `can_launch_media` | Launch any permitted bundle. Default `true` |
| `can_manage_environment` | Register or modify Environments, the Windows OS install workspaces |
| `can_manage_game` | Create, edit, delete, scan, and import game bundles and items, **and** Profile CRUD. Also gates `POST /api/v1/game-items/scan` |
| `can_manage_media` | Add, edit, or remove Media (the archival audio/text/image/video domain) |
| `can_manage_app` | Add, edit, or remove Apps, and gates the app-upload router |
| `can_manage_controllerMapping` | Create, edit, or delete controller mappings |
| `can_manage_settings` | Read and modify application settings |
| `can_manage_users` | Lets a sub-account edit its own `name` and reset its own PIN only. No capability over any other account, no self-delete, no create or delete |
| `is_admin` | Edit, reset-pin, unlock, and force-logout an existing sub-account, plus admin-only settings, emulator, and BIOS endpoints. Grants no other flag implicitly. Creating or deleting a sub-account requires `is_owner`, not `is_admin` |

`is_owner` bypasses every permission check and is not settable through the user create or
patch API.

### PIN reset authorisation

`POST /api/v1/user-items/{id}/reset-pin`, locked by
`test_users_create_delete_reset.py`:

- The **owner's** PIN can never be reset through this endpoint by anyone. Owner-target
  requests get 403. Recovery is [`scripts/setup_admin_user.py`](../scripts/setup_admin_user.py)
  only.
- The **owner** bypasses every other check and can reset any user's PIN regardless of lock
  state or role.
- An **admin** can reset PINs only for accounts that are neither the owner nor another
  admin. Targeting the owner, another admin, or their own record returns 403.
- A user holding `can_manage_users` can reset **its own** PIN and no one else's, and that
  self-service path is blocked with 403 while the account is locked, so a locked
  sub-account cannot self-recover.

A PIN reset does not revoke existing sessions; `session_token_hash` is left untouched. Use
`POST /api/v1/user-items/{id}/force-logout` to revoke.

### PIN security

- 4 to 6 digits, stored as [Argon2id](https://datatracker.ietf.org/doc/html/rfc9106)
  hashes with a per-user random salt.
- An optional app-level pepper (`PIN_PEPPER`) is set via
  `PATCH /api/v1/settings/pin-pepper` (owner-only) and stored in `.env`, outside SQLite. It
  is deliberately refused by the generic settings PATCH, because changing it forces a
  re-hash of the owner PIN in the same request.
- Plaintext PINs are never stored, logged, or returned.
- 4 consecutive failures locks the account. The increment-and-lock is a single atomic
  `UPDATE`, so concurrent requests cannot both slip past the threshold.
- `/auth/switch` is rate limited per source IP (30 requests / 60s) via
  [`core/rate_limit.py`](../backend/core/rate_limit.py).
- Owner lockout: run `scripts/setup_admin_user.py` locally. No remote reset, no email
  recovery, no bypass flag.

### Content ratings and parental controls

- Ratings are ingested from NFO sidecars, disc metadata, or filenames at scan time. The
  owner can override.
- Unrated is a first-class state, controlled per account by `block_unrated_media`.
- Each sub-account has a `max_content_rating` ceiling. Items above it are filtered at the
  query level, hidden entirely rather than surfaced and denied at launch.
- **The filter fails closed.** An unknown `max_content_rating` is rejected on write. If a
  stored ceiling can no longer resolve to a known ordinal (a `rating_ordinals` change
  orphaned it), no rated content passes at all rather than the cap being silently dropped.
  A bundle whose own rating is unrecognised is likewise denied to a capped user, never
  passed through.
- Enforcement is server-side. Deny wins over any permission flag, with no override path.
- The scale is freetext on `GameItemBundle.content_rating` and
  `AppItemBundle.content_rating`. Recommended: ESRB (E, E10+, T, M, AO) or PEGI (3, 7, 12,
  16, 18). The ordinal map is the `rating_ordinals` settings key, falling back to defaults
  derived in [`dependencies.py`](../backend/core/dependencies.py). No write path exists for
  it today; see Known Gaps.

## Input validation

**Mandatory implementation rules, not guidelines.**

- Every file path from any source (request body, query parameter, profile field, settings
  value) **must be resolved and normalised** before any filesystem operation. Paths used
  for scans and profile operations **must be validated against an allowlist** of permitted
  base directories: `LIBRARY_PATH` and its derived sub-paths (`SOFTWARE_PATH`,
  `MEDIA_PATH`, `OS_PATH`, `ROMS_PATH`), plus `PROFILES_PATH`. The allowlist and the
  `normalise_path` canonicaliser live in
  [`path_utils.py`](../backend/service/utils/path_utils.py).
  **Exception:** Environment image paths (`base_image_path`, `working_image_path`) may
  reside anywhere on the host; see Known Gaps.
- Traversal attempts, where the resolved path escapes its permitted base, **must be
  rejected with 400 and logged** before any filesystem operation occurs.
- **No user-supplied string may reach a subprocess call directly.** There must be at least
  one validation layer between input and execution.
- **Emulator binary paths are never taken from request input**, query parameters, or
  profile fields. `get_install_path()`
  ([`emulator_catalog.py`](../backend/service/utils/emulator_catalog.py)) resolves exactly
  two ways, by `install_type` on the per-slug TOML descriptor:

  | `install_type` | Resolves to |
  |---|---|
  | `rom_pack` | The descriptor's `binary` path relative to the project root (for 86Box: `emulators/86box/roms`), returned only if it exists and is non-empty |
  | Everything else | `emulators/{slug}/{binary}` |

  There is no settings-based user-override tier and no registry or system-installation
  detection tier. Both existed and were removed as dead code in the Pydantic-descriptor
  refactor (`616bb4f`, 2026-08-04). **This rule has no exceptions.**
- CLI arguments come from validated `ProfileItem` config fields only. There is no freeform
  command construction anywhere in the codebase.
- All validated inputs must be re-checked at the point of use. Do not rely on validation
  performed in a different layer.

## Process spawning

**Mandatory.**

- Emulator binary paths are never derived from request input, per `get_install_path()`
  above.
- Arguments are built from validated `ProfileItem` fields only, with no string
  interpolation of raw input into argument lists.
- A launch cooldown is enforced between successive requests to prevent rapid-fire spawning.
- Every spawned process is tracked and recorded in `LaunchHistory` (emulator, profile,
  target as `game_item_bundle_id` / `app_item_bundle_id` / `environment_item_id`, start
  time, exit code).
- Every spawned process is assigned to a Job Object. **If creation or assignment fails the
  launch is aborted.** There is no unsandboxed fallback.
- Linux is out of scope. Process isolation is Windows Job Objects only.

## Network rules

**Mandatory.**

- The service binds `127.0.0.1` by default and must not bind `0.0.0.0` unless
  `ALLOW_NETWORK_ACCESS` is explicitly `true`.
- CORS is locked to the application origin by default and must not be widened without an
  explicit operator decision.
- CSRF protection is required on all state-changing requests (POST, PUT, PATCH, DELETE).
- **Remote access is the operator's responsibility.** The recommended pattern is a reverse
  proxy with an external auth provider such as [Authentik](https://goauthentik.io/) or
  [Authelia](https://www.authelia.com/) in front. Peach 1UP does not manage TLS termination
  or external routing.
- **`ALLOW_NETWORK_ACCESS=true` creates a hard TLS dependency.** The session and CSRF
  cookies' `Secure` flag is derived directly from it, so enabling network access flips
  `Secure` to `True` whether or not a proxy is actually in place. A browser will not send a
  `Secure` cookie over plain HTTP, so without TLS termination already running,
  authentication silently breaks: login appears to succeed, the cookie is dropped, and
  every following request looks unauthenticated, producing an infinite re-login loop with
  no error message. Do not enable it until TLS termination is in place.

### Network isolation is emulator-native

Blocking happens at the emulator level, not via host firewall rules. Each emulator launches
with its network adapter disabled or absent when `enable_networking` is false on the active
profile, which is the default.

| Emulator | Mechanism |
|---|---|
| DOSBox-X | `-set ne2000=false` |
| 86Box | `net_type = none` in `[Network]`, written on every launch |
| Console emulators | No meaningful network capability, no explicit blocking required |

This needs no host elevation, cannot be bypassed by a COM availability issue, and is harder
for emulated software to work around than a host firewall rule.

**86Box specifics.** `net_type = none` disables connectivity without removing the emulated
NIC, avoiding Windows PnP re-detection. `slirp` enables user-mode NAT when
`enable_networking = true`. `pcap` (bridged, full IPX/NetBEUI) is not exposed; see the
[86Box documentation](https://86box.readthedocs.io/) if you need it. `net_card` is never
written by Peach 1UP, because changing it triggers Windows hardware detection.

## Destructive operations

**Mandatory.** Any endpoint that deletes or overwrites data requires two steps:

1. The client requests a short-lived confirmation token from a dedicated endpoint.
2. The client includes that token in the destructive request.
3. Tokens expire after **60 seconds** (`TOKEN_TTL` in
   [`confirmation_tokens.py`](../backend/service/utils/confirmation_tokens.py)). Expired
   tokens are rejected.

Applies to: game bundle delete, app bundle delete, environment delete, drive delete,
emulator delete, and AppContainer sandbox-state reset.

All destructive operations are logged with the initiating profile, the affected resource,
and the timestamp.

## Secrets handling

**Mandatory.**

- Each user row carries `identity_token_secret` (a server-only HMAC root key, generated
  once at account creation and never transmitted), `session_token_hash` (SHA-256 of the
  current token, `NULL` meaning logged out), `session_token_expires_at`, and
  `session_token_ttl`. Only the hash is persisted; the plaintext token is never stored. The
  cookie value is `{user_item_id}.{session_token}`, set as `peach_token` with `HttpOnly` and
  `SameSite=Lax`, and must never appear in logs, API responses, or version control. One
  active session per user by design: a new login overwrites the hash directly, so there is
  no token table and nothing to revoke or clean up. The owner always requires PIN
  verification to switch into.
- PINs are Argon2id-hashed with a per-user random salt. Plaintext PINs are never stored or
  logged.
- Request logging is deliberately minimal: `RequestLoggingMiddleware` emits method, path,
  status code, and duration only, so no headers and no bodies ever reach the log. Any
  future logging middleware that widens this must explicitly redact `Authorization`,
  `Cookie`, and outbound third-party query parameters.
- Third-party API credentials live in `.env` only, via
  [`env_secrets.py`](../backend/service/utils/env_secrets.py). They are never committed,
  never returned by the API, and never logged. See the TheGamesDB query-parameter caveat in
  Known Gaps.

## SQLite

SQLite does not enforce foreign key constraints by default, and this must be corrected on
every connection.

**Required:** register a SQLAlchemy `connect` event listener executing
`PRAGMA foreign_keys=ON` on every new connection, in place before any schema or data
operation runs. Do not assume the ORM does it. It is registered in
[`core/database.py`](../backend/core/database.py), and separately in
[`scripts/setup_admin_user.py`](../scripts/setup_admin_user.py), which builds its own
standalone engine.

## Standing instruction

Re-read this file before writing code that touches any of: authentication or session
handling, profile switching or permission checks, file path handling of any kind,
subprocess or process spawning, emulator launch flows, disk image operations, settings read
or write, destructive operations, network binding or CORS or middleware, or secrets and
credential handling.

If an implementation approach would require bypassing, weakening, or working around any
rule here, **stop and flag it** rather than finding a workaround. Raise it and wait for an
explicit decision.

## Windows process rules

**Mandatory.**

- All emulator processes launch under the current user account via `CreateProcessW`.
  Account-level isolation via a separate user account is not used.
- Every launch is assigned to a fresh Job Object with kill-on-close, a per-era CPU rate
  floor and cap (`MIN_MAX_RATE`), and a per-era per-process memory cap. Both resource caps
  are individually waivable per emulator via `skip_cpu_limit` and `skip_memory_limit`.
  **Every descriptor in [`config/emulators/`](../config/emulators/) currently sets both to
  `false`**, so both caps are enforced for every emulator as shipped and kill-on-close is
  not the only control in force. See [windows-sandbox.md](windows-sandbox.md) for the
  per-era numbers.
- **Both skip flags are honoured on both isolation layers.** Until the P9 follow-up
  hardening pass they were honoured only by the Python-side Job Object.
  `sandbox_host.exe` had no representation of `skip_cpu_limit` at all: `JobConfig` had no
  such field, the container payload never carried it, and `job.cpp` applied CPU rate control
  unconditionally. Every container-enabled emulator therefore received the CPU cap through
  the container path despite the descriptor, which reinstated the host-audio-muting bug the
  flag exists to prevent. It now travels in the `sandbox_host.exe` stdin payload as an
  explicit `job_config.skip_cpu_limit` boolean, resolved through `get_skip_cpu_limit()`, so
  the per-emulator override written by `PATCH /{slug}/sandbox` applies to both layers.
  `skip_memory_limit` resolves the same way.
- Launcher sequence: launch suspended (`CREATE_NEW_PROCESS_GROUP | CREATE_SUSPENDED`, so it
  cannot run before limits are in force) → create the Job Object, named with the launched
  process's PID for per-launch uniqueness → apply limits → `AssignProcessToJobObject` →
  breakaway retry on error 5 → `ResumeThread`.
- If `CreateProcessW` or `AssignProcessToJobObject` fails for any reason, **the launch is
  aborted**. There is no unsandboxed fallback, and a failed process is terminated while
  still suspended rather than resumed.
- AppContainer is an additional layer applied when `container_enabled = true`:

  | State | Emulators |
  |---|---|
  | Enabled | DOSBox-X, DuckStation, Flycast, Mesen, PCSX2, Xenia, xemu |
  | Disabled, environment-dependent | 86Box. Works in some environments and not others, disabled by default, not being investigated further |
  | Disabled, JIT incompatible | RPCS3 |
  | Permanently excluded | Project64 (`container_permanently_excluded = true`). Crashes on launch (`Main.cpp:99`, `exit_code=1`) even with limits raised, root cause unknown |

  xemu was previously excluded on a suspected QEMU TCG / `DeviceIoControl` incompatibility.
  That diagnosis was wrong: the real cause was memory and CPU limits sized below its
  pre-allocated JIT heap. It is enabled with adequate limits.

- Container-enable resolution and media-broker config are single implementations in
  [`emulator_catalog.py`](../backend/service/utils/emulator_catalog.py):
  `resolve_container_enabled()` resolves the effective flag for a launch (profile or spec
  override, falling back to catalog and settings), and `build_media_broker_config()` builds
  the `SandboxConfig` broker list. Backends whose broker needs exceed "expose the read-only
  media file" (`box86.py`, `dosbox.py`, `xemu.py`) still build their own `SandboxConfig`.
  A slug marked `container_permanently_excluded` rejects a profile-level override here:
  `resolve_container_enabled()` ignores it and logs a warning. `PATCH /{slug}/sandbox`
  separately rejects enabling a permanently disabled container with 400, so both routes
  into container gating are covered. **Today only `project64` carries that flag**, despite
  `rpcs3.toml`'s own `known_limitations` describing the same class of hard incompatibility;
  see [CHANGELOG.md](../CHANGELOG.md) open items.
- For container-enabled emulators, process creation is delegated to `sandbox_host.exe`,
  which handles `SECURITY_CAPABILITIES`,
  `CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT`, and `ResumeThread`. The Python
  launcher wraps the resulting PID in a Job Object via the same breakaway-retry path with
  `apply_limits=False`: `sandbox_host.exe`'s own Job Object already applied the numeric
  limits before the process resumed, so the Python-side job exists only as a teardown handle
  and for launch-history reporting.
- Emulators that have not passed the AppContainer test matrix ship with Job Object only and
  a visible warning on the Emulators page. The no-fallback abort policy still applies.

Implementation lives in the vendored [`wincage`](../services/vendor/wincage/) package:
`wincage/process.py` and `wincage/job.py` for the Python side, `wincage/src/container.cpp`,
`job.cpp`, and `main.cpp` for `sandbox_host.exe`.

## Hash-based media identity verification

Detection runs a full-file SHA-1 lookup (with MD5/CRC32 fallback) as its first tier against
a bundled `hash_index.json` built offline from Redump/No-Intro DAT files. A SHA-1 match
confirms the bytes are identical to a known community-verified dump, which is a real
integrity signal (a corrupted or incomplete rip will not match) and not only a title-lookup
convenience.

The pipeline lives in the vendored
[`formatscout`](../services/vendor/formatscout/) package, with the Peach-specific resolvers
in [`detection/`](../backend/service/utils/detection/).

**What it covers today:**

- It runs during library ingest, when a media path becomes a `GameItemBundle`
  ([`games/items.py`](../backend/service/games/items.py),
  [`routes/game_item_bundles.py`](../backend/api/routes/game_item_bundles.py),
  `drive_utils.py`), not during the raw upload-streaming step. The chunked upload routers
  only write bytes; they do not hash or verify anything in transit.
- `AppItemBundle` uploads skip it entirely. Era detection and hashing are not run for apps,
  and era stays `"unknown"` until a human sets it.
- **Hash-index coverage is two platforms:** PS1 and Xbox. Every other era (`win95`,
  `win98`, `winxp`, `ps2`, `ps3`, `xbox360`, `nes`, `snes`, `n64`, `dreamcast`) has zero
  coverage and falls through to the lower-confidence magic-byte, structural, directory, and
  extension tiers regardless of whether the file is corrupted or tampered with. Building a
  new index is a manual `python -m formatscout.hashing.build_index` step with no ingestion
  automation.

**What it is not:** live integrity monitoring or tamper detection. There is no
stored-expected-hash diff on relaunch, no re-verification after ingest, and no upload is
blocked or rejected on a mismatch or miss. A non-matching file ingests normally, at lower
confidence.

## Path allowlist on scan endpoints

The scan endpoint validates all user-supplied directory paths against an allowlist of
configured base directories before any filesystem operation. If none are configured,
scanning is blocked entirely. Media collections must reside under a configured base
directory. **This restriction must be carried forward to any future endpoint that accepts a
directory or file path parameter.**

All frontend requests go through the `ApiClient` singleton with `credentials: 'include'`,
so the `peach_token` cookie is sent on every request.

## Known limitations

### Job Object assignment on Windows 11

Windows 11 pre-assigns new child processes to an OS-managed Job Object, and a second
assignment fails with error 5 (access denied) unless the process was launched with
`CREATE_BREAKAWAY_FROM_JOB`. The launcher retries automatically: it terminates the still
suspended process and relaunches with the flag set, then assigns normally.

If the retry also fails (the process is inside a non-breakaway job set by a third-party tool
or debugger) **the launch is aborted** and the error surfaces to the user. Network isolation
is unaffected, being emulator-native.

### Resource-cap waiver history

Two Job Object caps apply per launch: a per-process memory cap
(`JOB_OBJECT_LIMIT_PROCESS_MEMORY`) and a CPU rate cap
(`JOB_OBJECT_CPU_RATE_CONTROL_MIN_MAX_RATE`, falling back to `HARD_CAP` below Windows 10
1607 build 14393 or on a `SetInformationJobObject` failure). Both are sized per era in
`eras.yaml` and waivable per emulator.

Two mechanisms motivated waiving the memory cap in the past:

- Qt's platform-plugin startup fast-fails with `STATUS_STACK_BUFFER_OVERRUN` (`0xC0000409`)
  when the memory cap is applied post-creation via `AssignProcessToJobObject`. Confirmed on
  86Box 5.3 / Qt 5.15.18 on Windows 11 (2026-05-19).
- Managed-runtime and JIT emulators (Mesen on .NET/Avalonia, xemu's pre-allocated JIT heap)
  pre-allocate at startup and hit the same fast-fail when the era cap is sized too small for
  that pre-allocation (2026-06-01).

The CPU cap was waived as a workaround for rate control deprioritising the host audio
session, muting system audio. The recorded fix for that (2026-05-21) is the switch from
`HARD_CAP` to `MIN_MAX_RATE` with a non-zero `MinRate` reserving a floor for the audio
thread, not a blanket waiver.

**Current status: every descriptor sets both flags to `false`.** Neither cap is waived for
any emulator; both are enforced as shipped. The correct fix in every case turned out to be
sizing the era limits properly rather than skipping the check.

| Emulator | `container_enabled` | `skip_cpu_limit` | `skip_memory_limit` | Notes |
|---|---|---|---|---|
| 86Box | false | false | false | Disabled by default pending broader AppContainer testing. Historically in the Qt fast-fail group; the memory cap is enforced today |
| DOSBox-X | true | false | false | No waiver history |
| DuckStation | true | false | false | Historically in the Qt fast-fail group; enforced today |
| Flycast | true | false | false | No waiver history. Its `known_limitations` entry still describes AppContainer as disabled, which contradicts `container_enabled = true` in the same file |
| Mesen | true | false | false | `skip_memory_limit = true` previously papered over an undersized era cap colliding with the .NET/Avalonia startup heap. `false` today with no crash reported, consistent with the cap sizing having been fixed |
| PCSX2 | true | false | false | Historically in the Qt fast-fail group; enforced today |
| Project64 | false, `container_permanently_excluded = true` | false | false | Crashes under AppContainer even with limits raised, root cause unresolved and unrelated to either flag. Job Object caps are the only active isolation layer and both are enforced |
| RPCS3 | false | false | false | Disabled per its own `known_limitations` (JIT incompatibility), but `container_permanently_excluded = false`, unlike Project64 |
| xemu | true | false | false | Re-enabled 2026-08-11 once the `xbox` era limits were sized above its JIT heap. No skip flag was needed |
| Xenia | true | false | false | No waiver history |
| 86box-roms | n/a | false | false | Not a launchable process (`install_type = "rom_pack"`); both flags are set only for schema uniformity |

If a future regression needs a waiver again, record the reason in
[CHANGELOG.md](../CHANGELOG.md) in the same change that flips the TOML value, so this table
does not go stale the way it did between 2026-06-01 and 2026-08-11.

### AppContainer is not validated for every emulator

Each emulator needs a smoke test and the full matrix (OS × GPU × audio × controller ×
install path × locale) before `container_enabled` is set. Until then it runs under Job
Object only.

### `/auth/switch` rate limiter is in-memory

The IP-keyed limiter ([`core/rate_limit.py`](../backend/core/rate_limit.py)) stores counts
in a process-local dict. A distributed attack across many unique source IPs no longer grows
it unbounded: `check_and_record` lazily sweeps keys whose window has fully elapsed, so the
dict stays bounded by the volume of *recent* distinct keys rather than every key ever seen.
It also records only allowed attempts, so a client hammering past the limit cannot keep
pushing its own window forward. Same in-memory-only precedent as `install_registry` and
`process_registry`: no persistence requirement, a restart clears it.

Peach 1UP is a household application first. We provide a basic level of protection; network
safety beyond the LAN is the operator's concern.

### Drive image paths are user-controlled per profile

Drive `.img` files are created at `{item.folder_path}/{item.slug}.img`, alongside the
bundle's media folder. The slug is validated at creation time. At launch,
`_build_drive_mount_lines` confirms the resolved path is inside the `library/` tree via
`is_relative_to()` after `normalise_path()` canonicalisation. `IMGMAKE` receives an absolute
path derived from the slug, so no user string reaches the command directly.

### `hash_index.json` is committed but not reproducible

The bundled index
(`services/vendor/formatscout/formatscout/hashing/hash_index.json`) ships in the package,
but the No-Intro/Redump DAT files it was built from do not: they are external, licensed
datasets. There is no way to regenerate or verify the index from files in the repo alone.
Flag only, no fix planned.

### Environment health check is a shallow probe

`_probe_image_integrity` in
[`environments/environments.py`](../backend/service/environments/environments.py) confirms
the working image is non-empty and that its first and last 512 bytes (where a VHD footer
would live) are readable. `_environment_files_present` additionally requires both the
working and base image files to exist. Neither parses or validates the disk image format, so
a working image with a corrupted middle section, or a header that matches by coincidence,
reports healthy.

Intentional cost/coverage tradeoff: full validation would need format-specific parsing for
every supported image type. If corrupted-but-passing images become a real support burden,
revisit with a format-aware checksum or a guest-OS boot probe.

### CI runs tests but has no pre-commit hook, and its staleness check is inert

[`test.yml`](../.github/workflows/test.yml) runs on every push and PR to `main`: it
regenerates constants and the OpenAPI/TypeScript types, runs Ruff plus `pytest --cov` on
`windows-latest`, runs ESLint, Prettier, a production build, and `vitest run --coverage`,
and finishes with a packaging smoke test that builds with PyInstaller and asserts the frozen
exe serves `/api/openapi.json`. [`codeql.yml`](../.github/workflows/codeql.yml) provides
static analysis.

There is **no pre-commit hook or husky config**, and the `generate-types` job's
`git diff --exit-code` staleness check cannot fail: all four generated paths are gitignored
and untracked, so `git diff` has nothing to compare. `_check_router_parity()` in
`export_and_build_types.py` still guards the `ROUTERS`-versus-`main.py` mismatch at export
time, and that one does fail loudly.

## Known gaps

### Environment image path traversal relies on the OS trust model

`base_image_path` and `working_image_path` may be set by any user with
`can_manage_environment` and may point anywhere on the host filesystem. The runtime
allowlist check was intentionally removed to allow images on secondary drives, external
volumes, and NAS shares.

**Implications:** such a user can cause the backend to read, copy, or existence-check files
at arbitrary host paths. Mitigating factors:

- `can_manage_environment` is an explicit operator-granted permission, not a sub-account
  default.
- The application runs as a local user, not a privileged service account.
- No image path is ever passed to a shell. There is no command construction from these
  fields.

**The AppContainer layer also writes ACLs at these paths.** A container-enabled launch
passes image paths to `sandbox_host.exe` as broker files, and `container.cpp`'s
`grant_directory` applies a **permanent, inheritable DACL grant** to the AppContainer SID via
`TreeSetNamedSecurityInfoW`, rewriting the ACL of every object beneath the path. Nothing
reverts it on exit. The reachable operation set on an arbitrary user-chosen path therefore
includes durable ACL modification, not just reads.

Current state after the P9 follow-up hardening pass:

- **DOSBox-X Environment launches no longer take a directory-level grant.** Narrowed to a
  traverse-only (`access="x"`, `mode="secure"`, non-inheriting) ACE on the parent node plus
  an `rw` ACE on the image file itself. DOSBox-X only ever opens that one file for an
  environment launch, so the previous recursive `rw` grant on the whole parent tree was not
  required by any emulator operation.
- **Paths are canonicalised at the point of use** via `normalise_path` before becoming a
  DACL target, so a symlink or junction planted under the chosen directory cannot redirect
  the grant to a tree the user never named. This is canonicalisation only; it deliberately
  rejects no location.
- **Per-item drive images keep their recursive parent-directory grant**, because DOSBox-X
  creates the `.img` in place via `IMGMAKE` on first launch and needs `FILE_ADD_FILE` on the
  parent. That path is separately containment-checked against `library/`.
- **Still open:** any other backend that passes an unvalidated Environment path as a
  `mode = "grant"` broker file inherits the original recursive behaviour. `container.cpp`'s
  `grant_directory` also carries a standing `TODO` that per-user ACEs accumulate on shared
  grant directories with no cleanup on user deletion.

`BrokerFile.mode` accepts `"grant"`, `"secure"`, and `"inherit"`. Only `grant` and `secure`
modify an ACL, and `grant` is the recursive one. See
[`services/vendor/wincage/README.md`](../services/vendor/wincage/README.md) for the
authoritative per-mode semantics.

To be addressed in a future hardening pass, either by restoring a configurable allowlist
with an opt-out flag or by surfacing an explicit warning at environment registration time.

### No recovery key exists

Earlier revisions of this document and of [AUTH.md](AUTH.md) described a recovery key
"shown once at first run" and "stored as an Argon2id hash only". **No such mechanism exists
anywhere in the codebase**: no column, no generation, no display, no verification path. The
claim has been removed from both documents rather than restated. If a recovery key is
wanted, it needs to be designed and built, not documented.

### Library path configuration has no user-facing mechanism

The Library Paths settings panel was removed from the UI. `LIBRARY_PATH`, `PROFILES_PATH`,
and `ROMS_PATH` can no longer be set through the frontend, and the `config/settings.yaml`
hand-edit fallback is gone with the file. **There is currently no file-based or UI-based way
for a user to reconfigure these paths.**

`POST /api/v1/settings/library-path` remains live and functional, writing to the `settings`
table via `set_path()`. It requires a `can_manage_settings` session, which in practice means
calling the API directly with an authenticated cookie rather than anything a typical user
can do through the app.

**Needs a decision, not fixed here:** the previous mitigation (hand-edit a config file) has
no equivalent, which is a regression from before the `settings.yaml` removal rather than
just a doc-accuracy issue. Replacement options are restoring a UI panel or documenting a
supported API/CLI workflow for advanced users.

Highest-risk case: `ROMS_PATH` defaults to `library/system/roms/86box`. Users who supply
86Box ROMs extracted to a non-default location, the common case, will silently use the wrong
path after a clean install with no documented way to correct it. The 86Box backend raises a
ROM path error at launch rather than proceeding, so the failure is visible, but the fix path
is undocumented.

### TheGamesDB leaks its key into any URL logging

The TheGamesDB API key is passed as a URL query parameter (`apikey=...`) per that API's own
convention. It is never logged or returned today, but if HTTP debug or trace logging were
enabled for outbound `httpx` calls, the key would leak into logs via the request URL. Any
future logging middleware must redact query params on outbound third-party requests, or
scrub this parameter specifically.

## Reporting security issues

Report vulnerabilities **privately** via
[GitHub Security Advisories](https://github.com/rymorrisj/peach_1up/security/advisories)
rather than opening a public issue. Include a description, steps to reproduce, and relevant
environment details. We will respond as quickly as possible and coordinate a disclosure
timeline with you.
