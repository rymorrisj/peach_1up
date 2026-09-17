# Changelog

One historical record for Peach 1UP: what shipped, when, and why. This merges the old
`dev_docs/DECISIONS.md` (104 dated entries, 2026-04-15 through 2026-07-17) and
`dev_docs/SCOPE.md` (the P0 through PX phase plan). Both files are gone now; everything
they held lives here.

| | |
|---|---|
| Version | `0.1.0` (`VERSION`), no tagged release cut yet |
| Status | Pre-alpha, closed testing |
| Span | 2026-04-15 to 2026-08-11 |
| Platform | Windows 10/11 only |

Work runs newest first, grouped by phase. Each decision is dated to when it was actually
made, not when it shows up here. If something got reversed later, the original entry
stays and the reversal gets noted next to it instead of quietly disappearing.

A couple of terminology notes for anyone reading the older entries: the model layer got
renamed twice, so `LibraryItem`/`LibraryCollection`/`LibrarySet` map to today's
`GameItemBundle` + `GameItem`, `Platform` is now `EnvironmentItem`, `Profile` is
`ProfileItem`, `User` is `UserItem`, and `media_type` is `file_type`. Windows 3.1
(`win31`) used to be a supported era and isn't anymore. `settings.yaml`,
`platforms.yaml`, and `emulators.yaml` are all gone too: operational settings and paths
live in the `settings` DB table now, and each emulator gets its own descriptor at
`config/emulators/*.toml`.

## Unreleased

### Open items

Carried forward, not resolved. Listed here on purpose, so they stay visible instead of
quietly vanishing along with the old source documents.

| Item | State |
|---|---|
| `sha1 = NULL` on directory-shaped leaves | Ingest runs `classify()` against the leaf's `file_path`. When that path is a directory (PS3 folder layouts, DOS loose-file folders) no hash gets computed and `sha1` stays `NULL`. Manual re-verify then takes the no-baseline branch, resolves the directory to its inner media file, and stores that file's hash instead, so the two paths end up disagreeing about what the leaf's hash actually represents. |
| Frontend test-runner hang | `TabbedLayout.test.tsx` and `test/routing.sectionRedirects.test.tsx` pass their assertions but never let the Vitest process exit. Looks like a leaked async handle, source not pinned down, and the hang point isn't even consistent between runs. Both are skipped for now, both carry a `TODO`. |
| PSS-3, PSS-6, PSS-7 | On hold. The trained executable-detection model needed the eXoDOS dataset, and its torrents and The Eye are both down. The LLM-assisted config path isn't needed for alpha anyway. |
| PX-4, console concurrent instancing | Paused. Per-user owned copies are scoped but not built. Two users launching the same console item at the same time can cause a duplicate media copy; expected until this actually ships. |
| BIOS/ROM centralization | Deferred, discovery-first. The `RomPackItem` relationship to a new ROM model is unresolved and blocks any schema work here. |
| Archive-aware ingestion | Deferred. Zip/7z-aware reading in the detector and DAT ingestion, plus DAT normalization ahead of `build_index.py`. Building this in-house rather than pulling in RomVault. |
| CHD Tier-1 hash matching | Blocked on `libchdr` hunk decompression. An interim size-based PS1/PS2 split is standing in for now. |
| Library path reconfiguration | `LIBRARY_PATH`, `PROFILES_PATH`, and `ROMS_PATH` have no UI and no config file. `POST /api/v1/settings/library-path` works, but the only way to reach it is calling the API directly. |
| `AI_API_KEY` | Writable through the settings PATCH endpoint and scrubbed from reads, but nothing actually consumes it yet. Either wire up a real consumer or drop the allowlist entry. (`IGDB_CLIENT_ID`/`IGDB_CLIENT_SECRET` were in the same spot and are now live, consumed by `igdb_provider.py`.) |
| 86Box per-machine ROM completeness | `--dumpmissing` isn't wired in as a preflight check. A machine profile missing one card's ROM might not surface a clean error. |
| 86Box drivers | The ROM pack and BIOS ship, but there are no guest drivers to actually make use of them. |
| xemu relaunch crash | `0xc0000409` in `msvcrt.dll` on any launch with system files configured. Confirmed upstream (xemu-project/xemu#1486), cross-vendor GPU. The workaround is disabling Control Flow Guard for `xemu.exe`. No code fix is possible on our end. |
| Aspect/resolution detection | Some platforms launch at default or native settings and end up with broken graphics. |

### 2026-08-22, formatscout/wincage migrated to pip-installed dependencies

Supersedes the note below about `formatscout` and `wincage` being consumed as local
editable path dependencies under `services/vendor/`. Both are ordinary PyPI dependencies
now, resolved by `uv sync`, and the `services/vendor/` trees for both packages are gone.
`wincage`'s `sandbox_host.exe` ships prebuilt inside its installed wheel, so there's no
native build step left to worry about.

### 2026-08-12, Project64/RPCS3/Xenia corrections

Corrects two of the 2026-08-11 findings below and locks in Project64's resource-cap
waiver.

| Emulator | Change |
|---|---|
| Project64 | Turned out the `Main.cpp:99` crash is specific to the memory limit being enforced alongside AppContainer, not a blanket incompatibility. `container_permanently_excluded` is back to `false`, `container_enabled = true`, `skip_memory_limit = true`. The CPU limit and AppContainer isolation itself stay on. |
| RPCS3 | The 2026-08-11 "disabled, JIT incompatible" finding was wrong, same class of misdiagnosis as the earlier xemu entry. RPCS3 actually works fine under AppContainer. `container_enabled = true`. |
| Xenia | Reverted the `gpu = "vulkan"` workaround for the AMD D3D12 driver timeout; the installed `xenia.config.toml` is back to the upstream default `gpu = "any"`. Anyone who hits the timeout can still set `gpu = "vulkan"` manually per the `known_limitations` entry, which notes Xenia's own in-app warning that its Vulkan path is early and incomplete. |

This also cleans up two stale doc/config mismatches from the open items list.
`flycast.toml`'s `known_limitations` text still said AppContainer was disabled for
testing, even though `container_enabled = true` had already been set in the same file.
`rpcs3.toml`'s `known_limitations` called AppContainer support impossible, when it's now
confirmed working. Both descriptor texts match their flags now.

Attribution audit: `NOTICE` was missing a DuckStation entry entirely and still listed
RPCS3 as lacking a `SOURCE_OFFER.txt`. Added `emulators/rpcs3/SOURCE_OFFER.txt`
(GPL-2.0-or-later, matching the other GPL emulators' format) and a DuckStation `NOTICE`
entry. DuckStation's own descriptor (`config/emulators/duckstation.toml`) actually lists
its license as CC BY-NC-ND 4.0, not GPL as this audit assumed going in, confirmed against
`emulators/duckstation/LICENSE.txt`. That license forbids redistributing derivatives,
which lines up with how DuckStation is actually handled: fetched unmodified from its own
GitHub release at install time rather than bundled, so it gets a `NOTICE` entry but no
`SOURCE_OFFER.txt`.

### 2026-08-11, AppContainer test findings

Supersedes the 2026-06-04 xemu exclusion entry.

| Emulator | AppContainer | Finding |
|---|---|---|
| Project64 | Permanently excluded | Crashes on launch under AppContainer (`Main.cpp:99`, `exit_code=1`), reproduced even with memory and CPU limits raised. Root cause unknown. `container_permanently_excluded = true`, so no profile or settings override can turn it back on. |
| 86Box | Disabled by default | Works under AppContainer on some machines and not others. Environment-dependent enough that it's not worth chasing further right now. `container_enabled = false` with no hard cap, so it can be re-enabled per install. |
| xemu | Re-enabled | The 2026-06-04 QEMU TCG / `DeviceIoControl` diagnosis was wrong. The real cause was memory and CPU limits sized below xemu's pre-allocated JIT heap, which produced an early exit that looked like an AppContainer incompatibility. With the xbox era limits sized properly (above 2048 MB), xemu runs fine under AppContainer. |
| DOSBox-X, DuckStation, Flycast, Mesen, PCSX2, Xenia | Enabled, clean | No open findings. |
| RPCS3 | Disabled | Heavily JIT-based (Cell PPU/SPU and RSX); runtime code generation doesn't play well with AppContainer's restricted token. Job Object isolation only for now. |

All ten emulator descriptors have `skip_cpu_limit = false` and `skip_memory_limit =
false`. No resource-cap waivers are active: the per-era CPU rate cap and the per-process
memory cap are both enforced on every launch.

### August 2026, package extraction and pre-beta hardening

- Detection and sandboxing split out into their own packages: disk-image and directory
  format detection became `formatscout`, Windows AppContainer and Job Object sandboxing
  became `wincage`. Both were consumed as local editable path dependencies under
  `services/vendor/` (2026-08-04 to 2026-08-07). Peach-specific launch-target resolvers
  (PS3, Xbox 360 XEX, Xbox optical images, `MediaTarget`) stayed in-tree under
  `backend/service/utils/detection/`.
- Emulator descriptors moved onto a Pydantic schema (`emulator_descriptor.py`), and the
  dead emulator-path resolution tiers went with it. `get_install_path()` now resolves
  exactly two ways: a `rom_pack` to its bundled directory, everything else to
  `emulators/{slug}/{binary}`. No settings-based user override anymore, no registry or
  system-install detection either. (`616bb4f`, 2026-08-04)
- Emulators switched to on-demand download. Nine of the ten use `install_type =
  "github_release"`; Project64 is `install_type = "zip"` because that project only
  publishes git tags, no release assets. Nothing gets committed as a binary. (2026-08-03)
- Hardcoded ceilings went onto the resource limits: `eras.yaml` values get clamped at
  load time, `cpu_limit_percent` at 90, `memory_limit_mb` at 75% of the host's actual
  physical RAM (queried per process via `GlobalMemoryStatusEx`). Going over the ceiling
  just logs a warning and uses the ceiling for that run, it never raises. (2026-08-09)
- Fixed Job Object naming so it includes the launched process PID; a name can no longer
  collide across concurrent launches.
- Dropped two orphaned tables, `hash_index_entries` and `emulator_installs`, along with
  all their write logic. (2026-08-09)
- Tooling cleanup: Python dependency management moved to `uv`, Ruff and Prettier gates
  went into CI, and a tag-triggered Windows release workflow got added with the version
  pulled from `constants.yaml` (a mismatched tag fails the build). Signing is stubbed for
  now, waiting on an OSS certificate.
- Fixed the owner recovery script. `scripts/setup_admin_user.py` was importing a `User`
  symbol that no longer existed, so it raised `ImportError` on every run. It imports
  `UserItem` now, and also calls `clear_session()` on the reset owner so a session issued
  before the reset can't survive it.
- Corrected launch exit handling: a clean exit code 0 counts as success, not a crash.
  (2026-08-09)
- PS3 era resolution is authoritative now, and directory structures get verified against
  their real media file instead of the folder itself. (2026-08-11)

### July 2026, v2 and v3 domain refactors

Two rename passes back to back reshaped the whole domain model and route surface.

| v1 | v2 | v3 (current) |
|---|---|---|
| `LibraryItem`, `LibrarySet` | `SoftwareCollection` + `SoftwareItem` | `GameItemBundle` + `GameItem` |
| `Platform` | `Environment` | `EnvironmentItem` |
| `User` | `User` | `UserItem` |
| `Profile` | `Profile` | `ProfileItem` |
| `ControllerMapping` | `ControllerMapping` | `ControllerMappingItem` |
| `can_edit_library` | `can_manage_software` | `can_manage_game` |
| `can_edit_platforms` | `can_edit_environments` | `can_manage_environment` |
| `/api/v1/library` | `/api/v1/software` | `/api/v1/game-items`, `/api/v1/game-item-bundle` |
| `/api/v1/platforms` | `/api/v1/environments` | `/api/v1/environment-items` |

A few other things landed in this same window:

- PS3 (RPCS3) and Xbox 360 (Xenia) support, including `.pkg` detection, `.SFB`
  disc-format folder detection, XEX folder detection plus launch dispatch, and default
  profiles for both. 7-Zip got vendored in to handle their `.7z` release assets.
- Five-state file verification (`verified` / `caution` / `mismatch` / `not_in_index` /
  `unchecked`), with per-disc SHA-1 computed at ingest, a fuzzy title-match fallback
  scoped to the resolved era, a bundle-level worst-severity rollup, and a manual
  re-verify endpoint. `suspect` got renamed to `mismatch` and the fuzzy threshold dropped
  to 0.80.
- Media and Apps domains added alongside Games, plus a polymorphic entity-link table
  connecting Game, App, and Media records with authorization checked on both sides.
- Consolidated the chunked upload pipeline into three per-domain routers built off one
  factory (`/api/v1/uploads/software-games`, `/software-media`, `/software-apps`), each
  gated by its own permission flag and registered explicitly at startup.
- Design system pass: colors converted to RGB-triplet CSS variables with skin-ready
  selectors, Modal/Toast/Tabs/Collapsible moved onto Radix primitives, and Card, Select,
  Checkbox, and RadioGroup primitives added.
- Docusaurus mounted at `/docs`, with `baseUrl` and footer/hero link resolution fixed.

### July 2026, platform consolidation

| Date | Decision |
|---|---|
| 2026-07-17 | Windows-only now. Linux support is out of scope. Process isolation is Windows Job Objects, full stop, and the earlier cgroups/namespaces sandbox plan is cancelled. Linux code paths came out of `filesystem.py`, `dosbox.py`, `emulator_installer.py`, `extract_xiso.py`, and `path_utils.py` in the same pass. |
| 2026-07-08 | Generated files never get committed. `constants_generated.py`, `generated/constants.ts`, `shared/openapi.json`, and `shared/types.ts` are regenerated by a dedicated `generate-types` CI job that the backend and frontend test jobs pull in as an artifact. Fixed CI failures on fresh checkouts and closes the drift risk between the two type pipelines: CI always tests against output generated fresh from current source. |
| 2026-07-05 | Environment snapshots got descoped in favor of DB plus `/emulators` backup. Working images can only get corrupted by normal use, and base/working reprovisioning already recovers from that. The two real single points of failure are the DB and `emulators/<slug>/` (saves, `.ini` state, BIOS placement, none of it DB-tracked). Backup just captures the whole `emulators` tree as-is instead of splitting user data from binaries per emulator: correct by construction, at the cost of backing up binaries that could just be redownloaded. |
| 2026-07-05 | Scan and import are stateless now. The `_scan_state` preview cache is gone; scan re-walks disk on every call, and import re-validates submitted paths against the DB at request time. `original_name` (a one-time snapshot taken at import) is what matches disk paths to existing rows on later scans. A DB-known path that's missing on disk fails loud instead of silently dropping. |
| 2026-07-05 | Full-delete-on-removal is a settings flag now, not an `_archive` folder. `delete_media_on_removal` (bool, default `False`). When it's true, deleting a collection also deletes its slug-named media folder, path-allowlist-validated under `MEDIA_PATH`. This replaces the `_archive` idea, which never had any cleanup code behind it. |
| 2026-07-03 | CHD era gets resolved by logical size now, not defaulted to PS2. Redump publishes per-track hashes, but a CHD's header-embedded `rawsha1` hashes the internal raw hunk stream, a completely different hash space that never lines up with the Redump index even with a full DAT. Real resolution needs `libchdr` decompression, which is deferred. For now, `CHTR`/`CHT2` CHDs split PS1 (CD, up to roughly 800 MB) from PS2 (DVD, several GB) by logical size. |
| 2026-07-02 | Reverted the shared-environment-drive convergence back to per-item drives (reset to `951d65e`). The shared design didn't hold up: there's no way to tell installer-versus-ready-to-run apart before a user actually runs an item, and that caused confirmed cross-item state leakage. Kept from the reverted branch: the AppContainer per-file ACE fix, the autoexec media-drive fallback plus auto-run behavior, and FAT16 cylinder-alignment padding. Backup tag `backup/shared-drives-f6ec3a8`. |
| 2026-07-01 | (Reversed the next day, see above.) DOS and Win3.1 converged onto environment-style working images, one persistent drive per era shared across all media of that era. |

### P-META, TheGamesDB metadata enrichment

Manual, on-demand enrichment. The user searches TheGamesDB, confirms a match, and
applies cover art plus detail fields to whatever entity they picked. No scan-time
auto-fetch, no background jobs, and it never blocks a launch.

- Encrypted `thegamesdb_api_key` settings field, owner-only write, masked once it's set.
- Search (`ByGameName`) and confirm/apply (`Images` + `ByGameID`) are split by an
  explicit user action, so just browsing search results doesn't cost an API credit.
- `sessionStorage` caches only the search-results list, keyed by page URL, cleared on a
  successful Keep.
- Cover art lives per physical row; description, rating, genre, release date, and
  platform live at bundle level for multi-disc sets.
- `genres`/`developers`/`publishers` come back as raw numeric IDs and get rejected with
  a 422 instead of silently dropped. Actually persisting them needs a schema decision
  that hasn't been made yet.
- Later extended with `metadata_fetched_at` tracking at both bundle and leaf level, a
  warning before re-fetching, and an Accept-All flow that links fetched assets into a
  Media item.

### PX-2, architecture refactors

Audit-driven refactors that needed to happen before console support could actually be
trusted.

- `config/emulators/*.toml` loads straight at runtime now; the `merge_emulators.py`
  build step is gone.
- One uniform backend launch interface: a single kwargs contract, data-driven dispatch,
  no more frozenset branching.
- Reconciled the AppContainer grant surface: the broker `path_key` vocabulary had to
  line up with `_resolve_path_key` before any console container could be enabled.
- Moved the launch contract into the descriptor itself (args template, cwd rule,
  portable sentinel, userdata location).
- Resolved a drive-location contradiction and removed the dead `DRIVES_PATH` key.
- Xbox is treated as a consumable now: xemu doesn't need an Environment for a single
  ISO.
- DOSBox-X per-launch config isolation. Each launch writes its conf into its own
  `tempfile.mkdtemp()` directory now. Before this, every launch shared one location, and
  a concurrent second launch could overwrite it mid-read.
- Fixed xemu config ownership: `validate_bios_path` checks the per-VM file, the broken
  `configure_emulator` xemu branch is gone, and flash/bootrom key naming got verified
  against xemu's documented schema.

### PX-1, era and console completion

Closed the remaining era gaps and verified every console backend end to end, on the
theory that a backend existing isn't the same thing as a backend actually launching.

- Fixed the 86Box PnP hardware-detection loop: hardware fields only get written on
  first boot and left alone after that, so Windows stops treating every launch as a
  hardware change. `net_card = none` and `net_type = none` get written to `[Network]`
  on every launch.
- Verified every console backend in order (Mesen, Project64, DuckStation, PCSX2, xemu)
  for launch, media load, Job Object tracking, and clean exit.
- Added Windows ME as an era via DOSBox-X, plus dgVoodoo2 injection for 3D-era Win9x
  games.
- Networking toggle surfaced in the profile UI.
- Controller remapping UI, frontend only for now.

A run of smoke-test fixes landed directly after P9, tagged `fix()` and severity-graded
in the commit history instead of tracked as phase items.

### Auth redesign, per-client token auth

- Session tokens are HMAC-derived per user now. Each user row carries an
  `identity_token_secret` root key, and only a SHA-256 hash of the live session token
  gets persisted. No separate token table, so one active session per user just falls
  out of the design.
- Cookie value is `{user_item_id}.{session_token}`, set as `peach_token` with
  `HttpOnly` and `SameSite=Lax`. No expiry by default unless `session_token_ttl` is set.
- The owner always needs a PIN. There's no unauthenticated owner fallback anywhere.
- `first_run_complete` moved out of `settings.yaml` and into the DB.
- Removed dead code: `SessionMiddleware`, `_FIRST_RUN_EXEMPT_PATHS`,
  `get_or_generate_session_secret`, `SESSION_SECRET`.
- Launch-history endpoints now require auth; the inline `is_admin` check moved into a
  dependency.
- Redesigned the frontend `ApiClient` as a singleton with `credentials: 'include'`, an
  `AbortController` timeout, a global error toast, and 401/403 redirect handling.

| Date | Decision |
|---|---|
| 2026-06-23 | Argon2id pepper gets mixed directly into the hash secret. Rotating it invalidates every existing hash with no migration path, by construction, so no staleness marker or extra DB field is needed. Enabling or rotating the pepper forces every non-owner account into `pin_required=True` and clears their `pin_hash`; the owner gets re-hashed in the same request. Don't add a multi-pepper verification fallback to soften this. Treat a pepper change as a real communicated event, not a quiet settings toggle. |
| 2026-06-20 | Refresh validates and extends, it never rotates. The old design minted a new token on every refresh, so two near-simultaneous refreshes from one session would race: whichever committed first invalidated the token the second was still presenting, producing a spurious 401 and an auto-logout right after first-run setup. `extend_session()` now only updates `session_token_expires_at`. Token issuance is exclusive to setup-owner and switch. A `useRef` StrictMode guard got added to the frontend too, as defense in depth, not as the actual fix. |
| 2026-06-20 | Docs site mounted via Starlette Host routing, registered before the SPA catch-all. Starlette dispatches to the first `Match.FULL` route in registration order, and a Host route matches FULL on any path once the hostname matches. Verified this empirically with `TestClient` in both orderings. It's exempted from `FirstRunGuardMiddleware` only, so the docs are reachable before setup completes, but the localhost-only network gate still applies. |

### P-Smart Scan (PSS), executable detection

Two-tier detection aimed at one-click launch accuracy: a bundled offline hash index
built from community Redump/No-Intro DAT files, plus an optional LLM-assisted config
path for anyone supplying their own API key.

- eXoDOS config extraction pipeline for executable paths, mount commands, and launch
  sequences.
- TOSEC and Redump DAT parsing into a bundled hash index for disc-image identity.
- Hash-based title confirmation wired into the scan flow, falling back to heuristics
  when there's no match.
- Encrypted `ai_api_key` settings field, never logged, never returned by the API.
- Expanded the heuristic blocklist (DEICE, PKUNZIP, LZMA, EXPAND, MSCDEX, SMARTDRV,
  README, UNWISE).
- Reviewed and expanded the default per-era emulator configs.

| Date | Decision |
|---|---|
| 2026-06-21 | `requires_install` is scoped to DOS and Win3.1 only now. It used to flag every `.iso`/`.cue` regardless of era, which mislabeled PS1/PS2/Dreamcast discs. It's gated on `era in {dos, win31}` before any suffix or directory check now, matching its only real consumer: the DOS loose-file drive-hydration gate. Console disc containers never set it. |
| 2026-06-02 | xiso detection now works off a magic string at offset `0x10000`: `MICROSOFT*XBOX*MEDIA` means xiso, and `CD001` at `0x8001` with a file size over 4 GB means a raw DVD rip. |
| 2026-06-02 | CHD platform detection now goes off the metadata tag. `CHGD` (GD-ROM) is an unambiguous Dreamcast discriminator that needs no payload parsing. `CHTR`/`CHT2` mean PS2 regardless of track type or sector size. |
| 2026-06-22 | Piloted a single accessor pattern for config-file reads on `eras.yaml`. It was getting parsed by six independent code paths, only one of which cached it, so every launch did redundant hot-path I/O. Consolidated into `eras_config.py` behind `get_eras()`/`get_era()` and one cache. No call-site error handling changed. |
| 2026-06-25 | Added `LibrarySet`/`LibrarySetItem` for multi-disc media, additive only. The set holds shared identity plus `launch_disk_id`; set items hold only per-disc media and cover paths. Non-disc-1 items don't get a standalone launch route, by design. No scan-time auto-detection, grouping only happens manually at upload time. |

### P9, Windows AppContainer isolation

AppContainer layered on top of the existing Job Object wrapper for filesystem, network,
and inter-process containment. Regular AppContainer only, not LPAC.

- Validated empirically before writing any production code: SDL2 + WASAPI + D3D11, Qt
  5.15 QPA, and SDL2 + OpenGL 4.5 test harnesses, run on Windows 10 22H2 and Windows 11
  23H2.
- `app_container.py` provisioning module: provision, `get_sid`, `grant_path`. Moniker
  scheme is `Peach1UP.<slug>.<scope>`. No auto-deletion.
- Sandbox tier shows on the Emulators page; a Reset sandbox state action lives in
  Advanced Settings.

| Date | Decision |
|---|---|
| 2026-05-21 | Went with regular AppContainer, rejected LPAC. Stripping ALL APPLICATION PACKAGES breaks OpenGL ICD loading from DriverStore and reproduces the same silent-failure pattern `peach_sandbox` had. Regular AppContainer keeps the audio session and GPU adapter access working, because the user identity doesn't change. |
| 2026-05-21 | Rolling out AppContainer per emulator via `container_enabled`. An emulator only gets it after its smoke test and the full test matrix pass. Anything that fails ships under Job Object only, with a visible warning. There's no unsandboxed fallback, ever. |
| 2026-05-21 | Switched CPU rate control from `HARD_CAP` to `MIN_MAX_RATE`. `HARD_CAP` starves threads to zero CPU at interval end, which mutes the host WASAPI audio session. A non-zero `MinRate` reserves a floor for the audio thread. Had to fix this before running the test matrix, or the results would have been polluted. |
| 2026-05-22 | Broker file model replaces direct DACL grants. `BrokerFile` has three modes: `secure` (apply an ACE to an existing file), `inherit` (open the file and pass the handle to the child), and `grant` (recursive `SetNamedSecurityInfo` with OI/CI on a directory). Descriptors carry `container_broker_files`. |
| 2026-05-22 | AppContainer GUI processes need a window station grant. No visible windows without explicit `GENERIC_ALL` on `WinSta0` and its default desktop, applied once at provisioning time. Required for every SDL2 and Qt emulator. |
| 2026-05-22 | Watchdog parent pid has to be a real process pid. `sandbox_host.exe` kills the sandboxed child if the parent dies, and a placeholder pid fires the watchdog immediately. |
| 2026-05-28 | Per-emulator `era` in the TOML uses the most demanding era for AppContainer sizing. 86Box covers win95/98/XP and maps to `winxp`, so the container is never under-resourced. Don't retune these to a lighter era just to fix a mismatch. |
| 2026-05-21 | xemu gets `%APPDATA%` write access at first launch. It writes its shader cache and settings there regardless of portable mode, and AppContainer doesn't redirect `%APPDATA%`. |
| 2026-06-04 | (Superseded 2026-08-11.) xemu got permanently excluded from AppContainer over a suspected QEMU TCG `DeviceIoControl` incompatibility. This is also where the TOML hard-cap pattern started: `container_enabled = false` in a descriptor locks out AppContainer no matter what settings or UI toggles say. |

### P8, native installer and distribution

Packaged as a native Windows installer with no runtime dependencies for end users.

- PyInstaller compiles the FastAPI backend and its dependencies into a standalone
  executable with the Python runtime embedded.
- pystray tray icon with Open, Restart, and Quit; the browser auto-opens on first
  launch.
- NSIS installer packages the compiled backend, the React static build, the emulators
  directory, and the SQLite data path. Registers Peach 1UP as a Windows service. UAC
  prompt only shows up at install time.

| Date | Decision |
|---|---|
| 2026-06-11 | Swapped NSSM for WinSW as the Windows service wrapper. NSSM hasn't had a stable release in years. WinSW is actively maintained, GitHub-released, and uses declarative XML config instead of runtime `set` commands. Service-account hardening moves to the `<serviceaccount>` element in `installer/tools/Peach1UP.xml`. |
| 2026-05-14 | Service runs as LocalSystem by default for now. Locking it down to a dedicated account is a pre-release hardening item. |

### P7, emulator and support software installation

On-demand emulator installation, ROM pack support, and in-app guidance cards with
official download links. No emulator binary gets redistributed in the repo.

- Binary detection for every emulator; ripped out the dead download machinery in
  `emulator_installer.py` and the HTTP 501 on the install route.
- Guidance cards for the 86Box ROM pack (with a Git Clone button) and BIOS files,
  surfaced in the first-run wizard and the emulator catalog page.
- Added the Flycast (Dreamcast) backend.
- Attribution page in Settings with GPL source links and copyright notices.

### P6.5, household user accounts and parental controls

One owner account plus multiple sub-accounts, each with a 4 to 6 digit PIN secured with
Argon2id.

- `users` and `user_restrictions` tables, seeded at first run.
- `scripts/setup_admin_user.py` creates or overwrites the owner account interactively,
  and doubles as a standalone recovery tool.
- Four consecutive PIN failures lock the account. The increment-and-lock happens as a
  single atomic `UPDATE`, so concurrent requests can't both slip past the threshold.
- Content ratings get ingested at scan time from NFO sidecars, disc metadata, or
  filenames.
- Rating enforcement is server-side and fails closed: an unrecognized rating, or a user
  ceiling that no longer resolves to a known ordinal, denies rather than passes.
- Permission flags gate every mutating endpoint; the owner bypasses all of them.
- PS4-style profile switcher on the home screen, with a PIN entry modal.

| Date | Decision |
|---|---|
| 2026-05-12 | Finalized the auth model for P6.5: owner plus sub-accounts, Argon2id PIN hashing, 4-attempt lockout, owner reset through settings, emergency recovery via a local script. Replaces the earlier placeholder profile-switching concept. |

### P6, Windows host isolation and resource limits

| Date | Decision |
|---|---|
| 2026-05-07 | Job Objects are required for every Windows emulator launch. Each launch gets assigned to a Job with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` plus a sane default CPU cap, so emulator trees always get torn down if the backend exits. |
| 2026-05-07 | (Reversed 2026-05-13.) Windows emulator launches run under a dedicated low-privilege `peach_sandbox` account, meant as a stepping stone toward AppContainer. |
| 2026-05-13 | `peach_sandbox` is gone entirely. That restricted account blocked audio access for every emulator, required the backend to run as Administrator, and added a lot of setup complexity for very little gain. Emulators run as the current user now, contained by Job Objects. Account-level isolation is deferred to AppContainer. |
| 2026-05-13 | Removed the conf-merge approach; confirmed inline `-c` args are sufficient on their own. The real root cause of the P6 launch failures was `peach_sandbox` lacking ACL read access, not path formatting or conf parsing. `dosbox_paths.py` and all the merge machinery are gone. |
| 2026-05-07 | Removed Windows Firewall COM network blocking. Rule creation through COM needs elevation and fails with `E_ACCESSDENIED` on standard installs. Network isolation is emulator-native instead: each emulator launches with its network adapter disabled or absent whenever `enable_networking` is false. No elevation required, and it's harder for emulated software to work around than a host firewall rule. |
| 2026-05-07 | Added `enable_networking` to the profile model, default false. |
| 2026-05-19 | Qt-based emulators need `skip_memory_limit` in the Job Object. Qt's platform-plugin startup fast-fails with `STATUS_STACK_BUFFER_OVERRUN` (`0xC0000409`) when `JOB_OBJECT_LIMIT_PROCESS_MEMORY` gets applied post-creation. Confirmed on 86Box 5.3 / Qt 5.15.18 on Windows 11. Kill-on-close and CPU rate control aren't affected. |
| 2026-06-01 | Revised the memory cap model. Era caps had only ever been sized for guest hardware. Managed-runtime and JIT emulators pre-allocate heap at startup regardless of game load, and hit the same fast-fail. Caps now account for emulator overhead plus headroom, not just guest hardware. |
| 2026-06-01 | Removed BIOS paths from `settings.yaml`. Every emulator resolves its BIOS files relative to its own binary directory now. |
| 2026-05-17 | Removed the Environment image path allowlist. Images can live on secondary drives, external volumes, and NAS shares now. Worth being explicit about the tradeoff: traversal protection for these paths relies on OS filesystem permissions and the user trust model now, not an application-level allowlist. Tracked as a known security gap. |
| 2026-05-17 | Emulator path model set to bundled, catalog-detected, or settings override. (All but the bundled tier got removed later as dead code, 2026-08-04.) |
| 2026-05-29 | Replaced the `/media` static mount with an authenticated route. `StaticFiles` bypasses `BaseHTTPMiddleware` entirely, so `SecurityMiddleware` never actually ran for mounted paths. BIOS, ROM, and OS image files are no longer passively exposed to network clients when `ALLOW_NETWORK_ACCESS=true`. |
| 2026-05-29 | Library update path fields now go through `normalise_path`. `PATCH` used to accept arbitrary strings for `media_path`, `executable_path`, `folder_path`, and `cover_art_path` with zero validation. All four now get null-byte and traversal rejection; the first two also assert existence. |
| 2026-05-25 | Added a persistent drive model to Profile: DOS and Win3.1 need a writable C: to persist sound config, saves, and installed files. |
| 2026-05-25 | Split `library/` into `media/` (user-facing, scanned) and `system/` (OS images, drives, ROMs, BIOS, saves, never scanned or shown). |
| 2026-05-25 | `.exe` and folder media supported for DOS and Win3.1 now, mounted via `MOUNT D <dir>` instead of `imgmount`. |
| 2026-05-27 | Extracted drive CRUD into `drive_utils.py`; set the FAT16 minimum size floor to 10 MB. |
| 2026-05-27 | Era auto-detection on scan and manual add: ISO 9660 PVD, PE headers, directory heuristics, extension fallback. `detection_reason` gets persisted and surfaced in the UI. |
| 2026-05-27 | Platform and profile get auto-assigned at add and scan time via `defaults_for_era`. |
| 2026-05-22 | Added `-noconfig` to the DOSBox-X launch args, because without it DOSBox-X loads its own bundled conf from the working directory and overrides the generated `output=surface` with `output=ttf`. |

### P5, architecture consolidation and schema unification

| Date | Decision |
|---|---|
| 2026-05-07 | FastAPI's OpenAPI spec is the single source of truth for types now. TypeScript types generate from it via `openapi-typescript` into `shared/types.ts`. The hand-maintained frontend type file is gone. |
| 2026-05-07 | SQLModel replaces the old SQLAlchemy-plus-Pydantic dual layer. That three-layer setup was really a hedge toward a Postgres migration that was never actually planned. SQLModel collapses the ORM and schema into one definition. |
| 2026-05-07 | Removed Alembic in favor of `create_all()` on startup. Migration overhead isn't worth it while there's no real user data yet and the DB can be wiped freely. Revisit this once user data actually needs to survive schema changes. |

Also: the database moved to `database/data/`, and having a static frontend build became
a hard prerequisite for the backend to start (the Vite dev server is opt-in, for
frontend work only).

### P4, console backends

Expanded past PC using the same profile and launch architecture: DuckStation (PS1),
PCSX2 (PS2), Project64 (N64), Mesen (NES), xemu (Xbox OG), and later Flycast
(Dreamcast). Added `.chd` and `.xiso` format support plus an in-app cartridge imaging
guide.

### P3.5, web UI

Replaced the Textual TUI with a React and TypeScript frontend served by FastAPI.

| Date | Decision |
|---|---|
| 2026-05-06 | Native installer now, replacing Tauri and Docker. PyInstaller compiles the backend, React gets served as static files by FastAPI, and pystray handles the tray icon. No Rust, no Docker, no separate web server. |
| 2026-05-06 | Pinned Tailwind CSS to v3. v4 brings breaking syntax changes and shadcn/ui doesn't support it yet. Don't upgrade until it does. |
| 2026-05-06 | Decoupled the Profile model from media items: profiles are global and reusable now, and an item just stores a nullable `selected_profile_id`. Tying profiles to items would have forced duplicating identical config. |
| 2026-05-06 | Launch now requires a profile selection; the Launch button stays gated until a valid profile is assigned. |
| 2026-05-06 | Platforms and profiles get pre-seeded at first run. Seeding is defensive: it warns instead of crashing, and platforms get created even when the binary is missing (the UI then just shows the official download link). |
| 2026-05-06 | Restricted the library scan path to configured base directories. The old implementation passed the directory parameter straight into `scan_directory()` with no validation at all. |
| 2026-05-06 | Added `SessionMiddleware` with a generated, persisted secret. (Removed entirely later by the auth redesign.) |
| 2026-05-06 | Logged defect: the Win9x FastAPI launch path had an `OSPlatform` signature mismatch, resolved at the start of P5. |

### P3, maturity

Stability, test coverage, and graceful failure handling across every supported era: a
first-run setup wizard, the library scanner, per-game config history, manual emulator
binary override, network-block verification on every launch, a community known-titles
database, and platform health checks with recovery prompts.

### P2, Windows 95/98/XP direct launch

Register a Windows OS environment and launch software from it through the right
backend. Two media paths: pre-installed HDD images (the primary path, zero install
friction) and original installer media (the user completes the install manually inside
the emulator).

| Date | Decision |
|---|---|
| 2026-05-17 | Flipped the Win9x backend from VirtualBox to 86Box. VirtualBox gives near-native CPU speed but poor compatibility for titles that need cycle-accurate timing, specific chipset behavior, or legacy peripheral emulation. 86Box is the preservation standard for Win9x software, and these titles are preservation targets, not performance benchmarks. |
| 2026-05-17 | Removed VirtualBox from the emulator stack entirely. It resists portable mode and needs a system service (`VBoxSDS`) the launcher can't manage cleanly. All Win9x and XP launches route through 86Box now. |
| 2026-05-19 | 86Box's VM directory layout follows portable-mode conventions. 86Box resolves every config path relative to the VM directory, and splitting config, disk images, and binaries across separate trees causes path-resolution failures. So all VM working files live together under `emulators/86box/vms/<slug>/`. The installation ISO stays in `library/os/` as read-only source media, referenced by absolute path. |
| 2026-05-19 | Environments are just a UI abstraction over that layout. Users see a name, era, hardware profile, and installation media; on disk each environment is a subdirectory under `emulators/86box/vms/<slug>/`. |
| 2026-05-14 | Renamed Platforms to Environments, and merged the Platforms page into Emulators (it was really just showing emulator binary status, which belongs there anyway). |
| 2026-05-14 | Library items and Environments are distinct execution models. Library items follow launch, play, cleanup, with state torn down after every session. Environments are persistent managed workspaces for software that needs installation, registry state, or long-term OS persistence. The real distinction is consumable versus persistent, not game versus tool. |
| 2026-05-14 | Profiles are scoped to emulators now, not eras, because settings are emulator-specific. Tags associate profiles with environments and content types instead of hard FK relationships. |
| 2026-05-14 | Added a tags system with pre-created system tags for emulators, eras, hardware configs (voodoo, mt32, soundblaster, adlib, ega, vga, svga), and content types. Users can add custom tags on top. |
| 2026-05-14 | Peach 1UP only manages processes it launches directly. Software launched externally, including emulator installers via `ShellExecute`, runs outside process tracking, Job Objects, and launch history. This is intentional, and it's surfaced in the UI near the Run Installer buttons. |
| 2026-05-14 | Renamed `images/` to `library/`, with per-item folders, so users can drop in cover art and supplementary files without any backend involvement. |
| 2026-05-03 | `OSPlatform` model for Win9x/XP. Per-game OS installs just aren't practical. One shared OS image per era, with a base plus working copy, is the right architecture here, matching how eXoDOS, 86Box power users, and VM tooling all already do it. |
| 2026-05-03 | Pre-installed HDD image is the primary media path. 90s installers are interactive and wildly inconsistent, so pre-installed images skip the install step entirely. Original media stays supported as a secondary path. |
| 2026-05-03 | DOSBox-X is scoped to DOS and Win3.1. For Win95/98 it's a compatibility fallback only, meant for DOS applications running under a Windows shell, never for native Win32 software. |

Also shipped: era hardware templates in `config/` (not hardcoded), base and working
image management (the base is locked and never modified), media attachment at launch
time with `autorun.inf` detection, a community-curated known-titles database with a
user-facing Hardware accuracy mode checkbox, an OS platform guidance screen linking to
community sourcing resources without automating any download, basic platform snapshots,
and CD-ROM passthrough for original discs.

### P1.5, polish and documentation

A documentation pass across every module (module docstrings, Google-style docstrings,
inline comments for the genuinely non-obvious stuff), the first README covering
objective, prerequisites, and setup, a dead-code sweep, and a wizard-flow audit for dead
ends and missing feedback.

### P1, core usability (DOS proof of concept)

Per-game YAML profiles, generated DOSBox-X configs tuned per era, persistent virtual
hard drives created and reused per profile, an install-once flow with direct launch
after that, media auto-detection, a UAC manifest for auto-elevation, missing-emulator
guidance with official links, and a settings screen.

| Date | Decision |
|---|---|
| 2026-04-16 | P1 scope is DOS direct launch only. Console backends and Win95/98/XP direct launch are deferred to P2. The goal here: drop in a DOS ISO, pick it, the game runs, no emulator interaction required. |
| 2026-04-16 | Conditional ROM warning on the era selector, only shown when the ROM pack is absent and accuracy mode is available. Checked at render time, so it just disappears once the pack shows up, no restart needed. |

### P0, bare minimum working launcher (2026-04-15 to 2026-04-16)

Project scaffold, the Windows Job Objects wrapper, DOSBox-X and 86Box backends, a
Textual TUI with an era selector and game picker, the end-to-end launch flow, and an
error-handling layer that surfaces every failure instead of crashing silently.

| Date | Decision |
|---|---|
| 2026-04-15 | Native Windows plus Job Objects for emulators. Windows containers are unstable on Home edition, and Linux containers have no official emulator binaries. Emulators sandbox game code natively; Job Objects cover host process isolation, resource limits, and filesystem restriction. Read-only mounts enforced from P0 on. |
| 2026-04-15 | Networking disabled via Job Objects. Safety rule, no multiplayer in scope. (Later replaced by emulator-native blocking, 2026-05-07.) |
| 2026-04-15 | DOSBox-X for DOS and Win3.1: no ROM requirement, works immediately, strong DOS accuracy. |
| 2026-04-15 | Textual for the TUI: keyboard-driven, Python-native, good docs. GUI deferred. |
| 2026-04-15 | No persistence in P0, disk images only. Physical drive passthrough deferred. |
| 2026-04-15 | Established `DECISIONS.md` as a separate append-only decision log, to keep `CLAUDE.md` and `CONTEXT.md` clean. (Retired 2026-08-12, merged into this file.) |

## Founding decisions (2026-04-15 to 2026-05-05)

| Date | Decision |
|---|---|
| 2026-05-05 | Peach 1UP is a preservation automation tool. The gap it fills is the path from "I have this old media" to "it's running correctly," with no manual emulator configuration. |
| 2026-05-05 | Library is the primary entity name. Software, game, tool, application, and utility are metadata tags, not structural distinctions. |
| 2026-05-05 | A profile is a hardware-era launch preset, not a per-game config. Bundled presets ship out of the box, fully user-editable and forkable. |
| 2026-05-03 | The user supplies all ROMs and BIOS assets. No bundled ROMs, BIOS files, or OS images, and no automated fetching of copyrighted media. Peach 1UP provides guidance and links only. |
| 2026-05-05 | FastAPI as the backend framework, with an auto-generated OpenAPI spec driving a typed React client. |
| 2026-05-05 | React and TypeScript for the frontend, chosen over Vue for ecosystem size. Vite for build tooling. |
| 2026-05-05 | SQLite via SQLAlchemy, plenty for read-heavy single-library usage. Prisma got rejected as Node-native and awkward next to a Python backend. |
| 2026-05-05 | Docusaurus for documentation: React-based, versioned, MDX, full-text search. |
| 2026-05-03 | Removed Docker from the runtime architecture entirely. It has no role in emulator execution or isolation. Supersedes the two 2026-04-15 Docker decisions. |
| 2026-05-03 | Set console scope to PS1, N64, NES, and Xbox OG. |
| 2026-05-05 | Moved PS2 from the backlog into P4. |

## Reversed and superseded decisions

Kept for the record. Every one of these was live at some point.

| Date | Decision | Outcome |
|---|---|---|
| 2026-05-05 | Linux-first application platform, running the app in Linux containers | Reversed 2026-07-17. Windows-only now. |
| 2026-05-05 | Docker Engine (headless) as the primary install, with `start.bat` as fallback | Reversed 2026-05-06 (native installer), then again 2026-05-03 (Docker pulled from the runtime entirely). |
| 2026-05-05 | cgroups and namespaces replace Job Objects as the isolation layer | Cancelled 2026-07-17 along with Linux support. |
| 2026-05-05 | Job Objects bypassed via `launch_direct` for DOS launches, because error 5 blocked assignment on Windows 11 | Superseded by the `CREATE_BREAKAWAY_FROM_JOB` retry path. |
| 2026-05-03 | VirtualBox as the default for Win95/98 and XP | Superseded 2026-05-17. |
| 2026-05-03 | 86Box as opt-in accuracy mode only | Superseded 2026-05-17; 86Box is the only Win9x/XP backend now. |
| 2026-05-07 | Windows 7 added to the VirtualBox era mapping | Void, VirtualBox is gone. |
| 2026-05-14 | VirtualBox Expert Mode set via `VBoxManage` post-install | Void, VirtualBox is gone. |
| 2026-05-14 | Emulator binaries bundled with the project, not downloaded at setup | Reversed 2026-08-03; every emulator installs on demand now. |
| 2026-05-07 | Emulator launches run under a dedicated low-privilege user | Reversed 2026-05-13. |
| 2026-05-07 | AppContainer deferred to a later phase (P8+) | Delivered in P9 instead. |
| 2026-05-13 | `peach_sandbox` requires explicit ACL grants on emulator and media directories | Void along with the account itself. |
| 2026-06-04 | xemu permanently excluded from AppContainer | Superseded 2026-08-11, the original diagnosis was wrong. |
| 2026-05-25 | Persistent drive model added to Profile | Doubly stale, superseded by the per-item then shared-drive churn of 2026-07-01/02. |
| 2026-05-27 | Drive CRUD extracted into `drive_utils.py` | Same as above. |
| 2026-07-01 | DOS/Win3.1 converged to shared environment-style working images | Reverted the next day, 2026-07-02. |
| 2026-05-03 | Basic platform snapshots moved into P2 | Descoped 2026-07-05 in favor of DB plus `/emulators` backup. |
| 2026-04-16 | ROM pack via git clone as a bundled asset | Superseded 2026-05-03 (user supplies all assets). |

## Deferred, not built

Scoped or talked through, deliberately never shipped.

- Linux support. Out of scope, permanently.
- Vibepollo / game streaming. Only worth revisiting if a hosted route ever actually gets
  taken.
- Editable memory and CPU limit overrides in the UI. The per-era values in `eras.yaml`
  are hand-edit only, no settings field, no UI control.
- Platform image compression and deduplication. Working copies and save backups just
  accumulate; there's no storage-management tooling.
- LLM-assisted emulator navigation.
- A ROM/BIOS pack builder for mixing and matching machines and software.
- 86Box floppy support.
- RetroArch `.cfg` import/export, SDL_GameControllerDB lookup, and per-emulator
  controller serializers. The serializers are what would actually make "map once, use
  everywhere" real; without them, Controller Mapping is just a storage form. Sequenced
  last because they're launch-path adjacent and need real hardware to test.
- Owner PIN lockout via unauthenticated `/auth/switch`. Four wrong owner PIN attempts
  lock the owner out, forcing host-script recovery. It's rate limited (30 per 60s per
  IP) but not actually prevented. Accepted under the household-trust threat model; only
  matters if this gets exposed beyond the LAN.