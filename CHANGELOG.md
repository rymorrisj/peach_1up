# Changelog

Single historical record for Peach 1UP: what shipped, when, and which decisions shaped
it. Merged from the retired `dev_docs/DECISIONS.md` (104 dated decision entries,
2026-04-15 to 2026-07-17) and `dev_docs/SCOPE.md` (the P0 to PX phase plan). Those two
files no longer exist; this file replaces both.

| | |
|---|---|
| Version | `0.1.0` (`VERSION`), no tagged release cut yet |
| Status | Pre-alpha, closed testing |
| Span | 2026-04-15 to 2026-08-11 |
| Platform | Windows 10/11 only |

Work is grouped by development phase, newest first. Dates on individual decisions are the
dates they were recorded. Entries that were later reversed are kept, with the reversal
noted, rather than deleted.

Terminology note for older entries: the model layer was renamed twice. Read
`LibraryItem`/`LibraryCollection`/`LibrarySet` as `GameItemBundle` + `GameItem`,
`Platform` as `EnvironmentItem`, `Profile` as `ProfileItem`, `User` as `UserItem`, and
`media_type` as `file_type`. `win31` (Windows 3.1) was a supported era and is not any
more. `settings.yaml`, `platforms.yaml`, and `emulators.yaml` were all removed;
operational settings and paths are DB-backed in the `settings` table and per-emulator
descriptors are `config/emulators/*.toml`.

## Unreleased

### Open items

Carried forward, not resolved. Listed here so they fail loud rather than disappear with
the source documents.

| Item | State |
|---|---|
| `sha1 = NULL` on directory-shaped leaves | Ingest runs `classify()` against the leaf's `file_path`. When that path is a directory (PS3 folder layouts, DOS loose-file folders) no hash is computed and `sha1` persists as `NULL`. Manual re-verify then takes the no-baseline branch, resolves the directory to its inner media file, and stores *that* file's hash, so the two paths disagree about what the leaf's hash represents. |
| Frontend test-runner hang | `TabbedLayout.test.tsx` and `test/routing.sectionRedirects.test.tsx` pass their assertions but never let the Vitest process exit. Leaked-async-handle signature, source not pinned down, hang point inconsistent between runs. Both skipped, both carry a `TODO`. |
| PSS-3, PSS-6, PSS-7 | On hold. The trained executable-detection model needed the eXoDOS dataset; its torrents and The Eye are both down. The LLM-assisted config path is not needed for alpha. |
| PX-4, console concurrent instancing | Paused. Per-user owned copies scoped but not built. Two users launching the same console item concurrently may cause a duplicate media copy; that is expected until this ships. |
| BIOS/ROM centralization | Deferred, discovery-first. The `RomPackItem` relationship to a new ROM model is unresolved and blocks any schema work. |
| Archive-aware ingestion | Deferred. Zip/7z-aware reading in the detector and DAT ingestion, plus DAT normalization before `build_index.py`. Build in-house, not RomVault. |
| CHD Tier-1 hash matching | Blocked on `libchdr` hunk decompression. Interim size-based PS1/PS2 split is in place. |
| Library path reconfiguration | `LIBRARY_PATH`, `PROFILES_PATH`, and `ROMS_PATH` have no UI and no config file. `POST /api/v1/settings/library-path` works but is only reachable by calling the API directly. |
| `AI_API_KEY` | Writable through the settings PATCH endpoint and scrubbed from reads, but nothing anywhere consumes it. Wire up a consumer or drop the allowlist entry. (`IGDB_CLIENT_ID`/`IGDB_CLIENT_SECRET` were in the same state and are now live, consumed by `igdb_provider.py`.) |
| 86Box per-machine ROM completeness | `--dumpmissing` is not wired in as a preflight check. A machine profile missing one card ROM may not surface a clean error. |
| 86Box drivers | The ROM pack and BIOS ship, but there are no guest drivers to actually use them. |
| xemu relaunch crash | `0xc0000409` in `msvcrt.dll` on any launch with system files configured. Confirmed upstream (xemu-project/xemu#1486), cross-vendor GPU. Workaround is disabling Control Flow Guard for `xemu.exe`. No code fix possible. |
| Aspect/resolution detection | Some platforms launch at default or native settings and break graphics. |

### 2026-08-22, formatscout/wincage migrated to pip-installed dependencies

Supersedes the "consumed as local editable path dependencies under `services/vendor/`"
description in the August 2026 package-extraction entry below. Both `formatscout` and
`wincage` are now regular PyPI dependencies resolved by `uv sync`; the `services/vendor/`
trees for both packages were removed. `wincage`'s `sandbox_host.exe` ships prebuilt inside
its installed wheel, no native build step required.

### 2026-08-12, Project64/RPCS3/Xenia corrections

Corrects two of the 2026-08-11 findings below and finalizes Project64's resource-cap
waiver.

| Emulator | Change |
|---|---|
| Project64 | Root cause narrowed: the `Main.cpp:99` crash is specific to the memory limit being enforced alongside AppContainer, not a blanket incompatibility. `container_permanently_excluded` reverted to `false`, `container_enabled = true`, `skip_memory_limit = true`. The CPU limit and AppContainer isolation itself remain in force. |
| RPCS3 | The 2026-08-11 "disabled, JIT incompatible" finding was wrong, the same class of misdiagnosis as the earlier xemu entry. RPCS3 is confirmed working under AppContainer. `container_enabled = true`. |
| Xenia | The `gpu = "vulkan"` workaround for the AMD D3D12 driver timeout is reverted; the installed `xenia.config.toml` is back to the upstream default `gpu = "any"`. A user who hits the timeout can still set `gpu = "vulkan"` manually per the `known_limitations` entry, which notes Xenia's own in-app warning that its Vulkan path is early/incomplete. |

Also resolves two stale doc/config inconsistencies carried in the open items list:
`flycast.toml`'s `known_limitations` text said AppContainer was disabled for testing
while `container_enabled = true` was already set in the same file; `rpcs3.toml`'s
`known_limitations` called AppContainer support impossible while it is now confirmed
working. Both descriptor texts now match their flags.

Attribution audit: `NOTICE` was missing a DuckStation entry entirely and still noted
RPCS3 as lacking a `SOURCE_OFFER.txt`. Added `emulators/rpcs3/SOURCE_OFFER.txt`
(GPL-2.0-or-later, matches the other GPL emulators' format) and a DuckStation `NOTICE`
entry. DuckStation's own descriptor (`config/emulators/duckstation.toml`) lists its
license as CC BY-NC-ND 4.0, not GPL as assumed going into this audit; confirmed against
`emulators/duckstation/LICENSE.txt`. That license forbids redistribution of derivatives,
which is consistent with DuckStation being fetched unmodified from its own GitHub
release at install time rather than bundled, so it gets a `NOTICE` entry but no
`SOURCE_OFFER.txt`.

### 2026-08-11, AppContainer test findings

Supersedes the 2026-06-04 xemu exclusion entry.

| Emulator | AppContainer | Finding |
|---|---|---|
| Project64 | Permanently excluded | Crashes on launch under AppContainer (`Main.cpp:99`, `exit_code=1`), reproduced with memory and CPU limits raised. Root cause unknown. `container_permanently_excluded = true`, so no profile or settings override can turn it back on. |
| 86Box | Disabled by default | Works under AppContainer in some environments and not others. Environment-dependent, not being investigated further. `container_enabled = false` with no hard cap, so it can be re-enabled per install. |
| xemu | Re-enabled | The 2026-06-04 QEMU TCG / `DeviceIoControl` diagnosis was wrong. The real cause was memory and CPU limits sized below xemu's pre-allocated JIT heap, producing an early exit that looked like an AppContainer incompatibility. With the xbox era limits sized adequately (above 2048 MB) xemu runs correctly under AppContainer. |
| DOSBox-X, DuckStation, Flycast, Mesen, PCSX2, Xenia | Enabled, clean | No open findings. |
| RPCS3 | Disabled | Heavily JIT-based (Cell PPU/SPU and RSX); runtime code generation is incompatible with AppContainer's restricted token. Job Object isolation only. |

All ten emulator descriptors set `skip_cpu_limit = false` and `skip_memory_limit = false`.
There are no active resource-cap waivers: the per-era CPU rate cap and per-process memory
cap are both enforced on every launch.

### August 2026, package extraction and pre-beta hardening

- **Detection and sandboxing extracted into standalone packages.** Disk-image and
  directory format detection became `formatscout`; Windows AppContainer and Job Object
  sandboxing became `wincage`. Both are consumed as local editable path dependencies
  under `services/vendor/`. Peach-specific launch-target resolvers (PS3, Xbox 360 XEX,
  Xbox optical images, `MediaTarget`) stayed in-tree under
  `backend/service/utils/detection/`. (2026-08-04 to 2026-08-07)
- **Emulator descriptors moved to a Pydantic schema** (`emulator_descriptor.py`), and the
  dead emulator-path resolution tiers were removed with it. `get_install_path()` now
  resolves exactly two ways: a `rom_pack` to its bundled directory, everything else to
  `emulators/{slug}/{binary}`. There is no settings-based user override and no
  registry/system-installation detection. (`616bb4f`, 2026-08-04)
- **Emulators moved to on-demand download.** Nine of ten use
  `install_type = "github_release"`. Project64 is `install_type = "zip"` because the
  project publishes git tags but no release assets. No emulator binary is committed.
  (2026-08-03)
- **Hardcoded resource-limit ceilings added.** `eras.yaml` values are clamped at load
  time: `cpu_limit_percent` at 90, `memory_limit_mb` at 75% of the host's real physical
  RAM (queried per process via `GlobalMemoryStatusEx`). Over-ceiling values log a warning
  and use the ceiling for that run; they never raise. (2026-08-09)
- **Job Object naming fixed** to include the launched process PID, so a name can no
  longer collide across concurrent launches.
- **Orphaned tables dropped:** `hash_index_entries` and `emulator_installs`, plus all
  write logic. (2026-08-09)
- **Tooling:** Python dependency management migrated to `uv`; Ruff and Prettier gates
  added and enabled in CI; a tag-triggered Windows release workflow added with the
  version sourced from `constants.yaml` (a tag that does not match fails the build).
  Signing is stubbed pending an OSS certificate.
- **Owner recovery script fixed.** `scripts/setup_admin_user.py` imported a `User` symbol
  that no longer existed and raised `ImportError` on every run. It now imports `UserItem`
  and additionally calls `clear_session()` on the reset owner, so a session issued before
  the reset no longer survives it.
- **Launch exit handling corrected:** a clean exit code 0 is treated as success, not a
  crash. (2026-08-09)
- **PS3 era resolution made authoritative**, and directory structures are verified via
  their real media file rather than the folder. (2026-08-11)

### July 2026, v2 and v3 domain refactors

Two successive rename passes reshaped the domain model and the whole route surface.

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

Also shipped in this window:

- **PS3 (RPCS3) and Xbox 360 (Xenia) support**, including `.pkg` detection, `.SFB`
  disc-format folder detection, XEX folder detection and launch dispatch, and default
  profiles for both. 7-Zip was vendored to handle their `.7z` release assets.
- **Five-state file verification** (`verified` / `caution` / `mismatch` / `not_in_index`
  / `unchecked`) with per-disc SHA-1 at ingest, a fuzzy title-match fallback scoped to
  the resolved era, a bundle-level worst-severity rollup, and a manual re-verify
  endpoint. `suspect` was renamed to `mismatch` and the fuzzy threshold lowered to 0.80.
- **Media and Apps domains** added alongside Games, plus a polymorphic entity-link table
  connecting Game, App, and Media records with two-sided authorization.
- **Chunked upload pipeline consolidated** into three per-domain routers built from one
  factory (`/api/v1/uploads/software-games`, `/software-media`, `/software-apps`), each
  gated by its own permission flag and registered explicitly at startup.
- **Design system pass:** colors converted to RGB-triplet CSS variables with skin-ready
  selectors, Modal/Toast/Tabs/Collapsible migrated onto Radix primitives, and Card,
  Select, Checkbox, and RadioGroup primitives added.
- **Docusaurus site mounted at `/docs`** with `baseUrl` and footer/hero link resolution
  fixed.

### July 2026, platform consolidation

| Date | Decision |
|---|---|
| 2026-07-17 | **Windows-only. Linux support removed from scope.** Process isolation is Windows Job Objects only. The earlier cgroups/namespaces sandbox plan is cancelled. Linux code paths removed from `filesystem.py`, `dosbox.py`, `emulator_installer.py`, `extract_xiso.py`, and `path_utils.py` in the same pass. |
| 2026-07-08 | **Generated files are never committed.** `constants_generated.py`, `generated/constants.ts`, `shared/openapi.json`, and `shared/types.ts` are regenerated by a dedicated `generate-types` CI job that the backend and frontend test jobs depend on via artifact download. Fixes CI failures on fresh checkouts and closes the A/B drift risk between the two type pipelines: CI always tests against output freshly generated from current source. |
| 2026-07-05 | **Environment snapshots descoped in favour of DB plus `/emulators` backup.** Working images are only corruptible by normal use, which base/working reprovisioning already recovers from. The two real single points of failure are the DB and `emulators/<slug>/` (save files, `.ini` state, BIOS placement, none of it DB-tracked). Backup captures the whole `emulators` tree as-is rather than splitting user data from binaries per emulator: correct by construction, at the cost of backing up redownloadable binaries. |
| 2026-07-05 | **Scan and import become stateless.** The `_scan_state` preview cache is removed. Scan re-walks disk on every call; import re-validates submitted paths at request time against the DB. `original_name` (a one-time snapshot at import) matches disk paths to existing rows on later scans. A DB-known path missing on disk fails loud rather than silently dropping. |
| 2026-07-05 | **Full-delete-on-removal is a settings flag, not an `_archive` folder.** `delete_media_on_removal` (bool, default `False`). When true, deleting a collection also removes its slug-named media folder, path-allowlist-validated under `MEDIA_PATH`. Supersedes the `_archive` proposal, which left no code behind to clean up. |
| 2026-07-03 | **CHD era resolved by logical size, not defaulted to PS2.** Redump publishes per-track hashes; a CHD's header-embedded `rawsha1` hashes the internal raw hunk stream, a different hash space that never intersects the Redump index even with a complete DAT. True resolution needs `libchdr` decompression, deferred. Interim: `CHTR`/`CHT2` CHDs split PS1 (CD, up to roughly 800 MB) from PS2 (DVD, several GB) by logical size. |
| 2026-07-02 | **Reverted the shared-environment-drive convergence back to per-item drives** (reset to `951d65e`). The shared design was unsound: installer-versus-ready-to-run cannot be determined before a user runs an item, which caused confirmed cross-item state leakage. Kept from the reverted branch: the AppContainer per-file ACE fix, the autoexec media-drive fallback plus auto-run behavior, and FAT16 cylinder-alignment padding. Backup tag `backup/shared-drives-f6ec3a8`. |
| 2026-07-01 | *(Reversed the next day, see above.)* DOS and Win3.1 converged to environment-style working images, one persistent drive per era shared across all media of that era. |

### P-META, TheGamesDB metadata enrichment

Manual, on-demand enrichment. The user searches TheGamesDB, confirms a match, and applies
cover art and detail fields to the chosen entity. No scan-time auto-fetch, no background
jobs, never blocks launch.

- Encrypted `thegamesdb_api_key` settings field, owner-only write, masked once set.
- Search (`ByGameName`) and confirm/apply (`Images` + `ByGameID`) are separated by an
  explicit user action, so no API credit is spent on selection alone.
- `sessionStorage` caches the search-results list only, keyed by page URL, cleared on a
  successful Keep.
- Cover art is per physical row; description, rating, genre, release date, and platform
  live at bundle level for multi-disc sets.
- `genres`/`developers`/`publishers` come back as raw numeric IDs and are rejected with
  422 rather than silently dropped. Persisting them needs a schema decision that has not
  been made.
- Later extended with `metadata_fetched_at` tracking at bundle and leaf level, a warning
  before re-fetching, and an Accept-All flow that links fetched assets into a Media item.

### PX-2, architecture refactors

Audit-driven refactors needed before console support could be trusted.

- `config/emulators/*.toml` loaded at runtime directly; the `merge_emulators.py` build
  step eliminated.
- Uniform backend launch interface: one kwargs contract, data-driven dispatch, no
  frozenset branching.
- AppContainer grant surface reconciled: broker `path_key` vocabulary aligned with
  `_resolve_path_key` before enabling any console container.
- Launch contract moved into the descriptor (args template, cwd rule, portable sentinel,
  userdata location).
- Drive location contradiction resolved and the dead `DRIVES_PATH` key removed.
- Xbox treated as a consumable: xemu no longer requires an Environment for a single ISO.
- **DOSBox-X per-launch config isolation.** Each launch now writes its conf to its own
  `tempfile.mkdtemp()` directory. Previously all launches shared one location, which a
  concurrent second launch could overwrite mid-read.
- xemu config ownership fixed: `validate_bios_path` checks the per-VM file, the broken
  `configure_emulator` xemu branch removed, flash/bootrom key naming verified against
  xemu's documented schema.

### PX-1, era and console completion

Closed the remaining era gaps and verified every console backend end to end, on the
principle that backend existence is not the same as confirmed launch.

- 86Box PnP hardware-detection loop fixed: hardware fields are written only on first boot
  and left untouched afterward, so Windows stops treating every launch as a hardware
  change. `net_card = none` and `net_type = none` written to `[Network]` on every launch.
- Every console backend verified in order (Mesen, Project64, DuckStation, PCSX2, xemu)
  for launch, media load, Job Object tracking, and clean exit.
- Windows ME era added via DOSBox-X, plus dgVoodoo2 injection for 3D-era Win9x games.
- Networking toggle surfaced in the profile UI.
- Controller remapping UI (frontend only).

After P9 a run of smoke-test fixes landed directly, marked `fix()` and severity-graded in
the commit history rather than tracked as phase items.

### Auth redesign, per-client token auth

- **Session tokens are HMAC-derived per user.** Each user row carries an
  `identity_token_secret` root key; only a SHA-256 hash of the live session token is
  persisted. No separate token table, so one active session per user falls out of the
  design.
- Cookie value is `{user_item_id}.{session_token}`, set as `peach_token` with `HttpOnly`
  and `SameSite=Lax`. No expiry by default unless `session_token_ttl` is set.
- The owner always requires a PIN. There is no unauthenticated owner fallback anywhere.
- `first_run_complete` moved from `settings.yaml` to the DB.
- `SessionMiddleware`, `_FIRST_RUN_EXEMPT_PATHS`, `get_or_generate_session_secret`, and
  `SESSION_SECRET` removed as dead code.
- Launch-history endpoints now require auth; the inline `is_admin` check moved into a
  dependency.
- Frontend `ApiClient` redesigned as a singleton with `credentials: 'include'`, an
  `AbortController` timeout, a global error toast, and 401/403 redirect handling.

| Date | Decision |
|---|---|
| 2026-06-23 | **Argon2id pepper is mixed directly into the hash secret.** Rotating it invalidates every existing hash with no migration path, by construction, so no staleness marker or extra DB field is needed. Enabling or rotating the pepper forces every non-owner account into `pin_required=True` and clears their `pin_hash`; the owner is re-hashed in the same request. Do not add a multi-pepper verification fallback to soften this. Treat a pepper change as a communicated event, not a settings toggle. |
| 2026-06-20 | **Refresh validates and extends, never rotates.** The prior design minted a new token on every refresh, so two near-simultaneous refreshes from one session raced: the first commit invalidated the token the second was still presenting, producing a spurious 401 and auto-logout right after first-run setup. `extend_session()` now updates `session_token_expires_at` only. Token issuance is exclusive to setup-owner and switch. A `useRef` StrictMode guard was added to the frontend as defence in depth, not as the fix. |
| 2026-06-20 | **Docs site mounted via Starlette Host routing.** Registered before the SPA catch-all, because Starlette dispatches to the first `Match.FULL` route in registration order and a Host route matches FULL on any path once the hostname matches. Verified empirically with `TestClient` in both orderings. Exempted from `FirstRunGuardMiddleware` only, so docs are reachable before setup completes; the localhost-only network gate still applies. |

### P-Smart Scan (PSS), executable detection

Two-tier detection for one-click launch accuracy: a bundled offline hash index built from
community Redump/No-Intro DAT files, plus an optional LLM-assisted config path for users
supplying their own API key.

- eXoDOS config extraction pipeline for executable paths, mount commands, and launch
  sequences.
- TOSEC and Redump DAT parsing into a bundled hash index for disc-image identity.
- Hash-based title confirmation wired into the scan flow, falling back to heuristics on
  no match.
- Encrypted `ai_api_key` settings field, never logged, never returned by the API.
- Heuristic blocklist expanded (DEICE, PKUNZIP, LZMA, EXPAND, MSCDEX, SMARTDRV, README,
  UNWISE).
- Default per-era emulator configs reviewed and expanded.

| Date | Decision |
|---|---|
| 2026-06-21 | **`requires_install` scoped to DOS and Win3.1 only.** It previously flagged every `.iso`/`.cue` regardless of era, mislabelling PS1/PS2/Dreamcast discs. Now gated on `era in {dos, win31}` before any suffix or directory check, matching its only real consumer, the DOS loose-file drive-hydration gate. Console disc containers never set it. |
| 2026-06-02 | **xiso detection via magic string at offset `0x10000`.** `MICROSOFT*XBOX*MEDIA` means xiso; `CD001` at `0x8001` with a file size over 4 GB means a raw DVD rip. |
| 2026-06-02 | **CHD platform detection via metadata tag.** `CHGD` (GD-ROM) is an unambiguous Dreamcast discriminator with no payload parsing. `CHTR`/`CHT2` indicate PS2 regardless of track type or sector size. |
| 2026-06-22 | **Single accessor pattern for config-file reads**, piloted on `eras.yaml`. It was parsed by six independent code paths, only one cached, producing redundant hot-path I/O on every launch. Consolidated into `eras_config.py` with `get_eras()`/`get_era()` behind one cache. No call-site error handling changed. |
| 2026-06-25 | **`LibrarySet`/`LibrarySetItem` added for multi-disc media**, additive only. The set holds shared identity plus `launch_disk_id`; set items hold only per-disc media and cover paths. Non-disc-1 items have no standalone launch route by design. No scan-time auto-detection; manual upload-time grouping only. |

### P9, Windows AppContainer isolation

AppContainer layered on top of the existing Job Object wrapper for filesystem, network,
and inter-process containment. Regular AppContainer only.

- Empirical validation gate first: SDL2 + WASAPI + D3D11, Qt 5.15 QPA, and SDL2 + OpenGL
  4.5 test harnesses on Windows 10 22H2 and Windows 11 23H2. No production code until all
  passed.
- `app_container.py` provisioning module: provision, `get_sid`, `grant_path`. Moniker
  scheme `Peach1UP.<slug>.<scope>`. No auto-deletion.
- Sandbox tier displayed on the Emulators page; Reset sandbox state action in Advanced
  Settings.

| Date | Decision |
|---|---|
| 2026-05-21 | **Regular AppContainer adopted, LPAC rejected.** Stripping ALL APPLICATION PACKAGES breaks OpenGL ICD loading from DriverStore and reproduces the `peach_sandbox` silent-failure pattern. Regular AppContainer preserves the audio session and GPU adapter access because the user identity is unchanged. |
| 2026-05-21 | **Per-emulator rollout via `container_enabled`.** An emulator gets AppContainer only after its smoke test and full test matrix pass. Failures ship under Job Object only with a visible warning. There is no unsandboxed fallback, ever. |
| 2026-05-21 | **CPU rate control changed from `HARD_CAP` to `MIN_MAX_RATE`.** `HARD_CAP` starves threads to zero CPU at interval end, muting the host WASAPI audio session. A non-zero `MinRate` reserves a floor for the audio thread. Required before the test matrix to avoid polluting results. |
| 2026-05-22 | **Broker file model replaces direct DACL grants.** `BrokerFile` has three modes: `secure` (apply an ACE to an existing file), `inherit` (open the file and pass the handle to the child), and `grant` (recursive `SetNamedSecurityInfo` with OI/CI on a directory). Descriptors carry `container_broker_files`. |
| 2026-05-22 | **Window station grant required for AppContainer GUI processes.** No visible windows without explicit `GENERIC_ALL` on `WinSta0` and its default desktop, applied once at provisioning time. Required for all SDL2 and Qt emulators. |
| 2026-05-22 | **Watchdog parent pid must be a real process pid.** `sandbox_host.exe` kills the sandboxed child if the parent dies; a placeholder pid fires the watchdog immediately. |
| 2026-05-28 | **Per-emulator `era` in the TOML uses the most demanding era for AppContainer sizing.** 86Box covers win95/98/XP and maps to `winxp` so the container is never under-resourced. Do not retune these to a lighter era to "fix" a mismatch. |
| 2026-05-21 | **xemu `%APPDATA%` write access granted at first launch.** xemu writes its shader cache and settings to `%APPDATA%\xemu\` regardless of portable mode, and AppContainer does not redirect `%APPDATA%`. |
| 2026-06-04 | *(Superseded 2026-08-11.)* xemu permanently excluded from AppContainer on a suspected QEMU TCG `DeviceIoControl` incompatibility. Introduced the TOML hard-cap pattern: `container_enabled = false` in a descriptor locks out AppContainer regardless of settings overrides or UI toggles. |

### P8, native installer and distribution

Packaged as a native Windows installer with no runtime dependencies for end users.

- PyInstaller compiles the FastAPI backend and its dependencies into a standalone
  executable with the Python runtime embedded.
- pystray tray icon with Open, Restart, and Quit; browser auto-opens on first launch.
- NSIS installer packages the compiled backend, React static build, emulators directory,
  and SQLite data path. Registers Peach 1UP as a Windows service. UAC prompt on install
  only.

| Date | Decision |
|---|---|
| 2026-06-11 | **WinSW replaces NSSM as the Windows service wrapper.** NSSM has had no stable release in years. WinSW is actively maintained, GitHub-released, and uses declarative XML config instead of runtime `set` commands. Service-account hardening moves to the `<serviceaccount>` element in `installer/tools/Peach1UP.xml`. |
| 2026-05-14 | Service runs as LocalSystem by default. Locking it down to a dedicated account is a pre-release hardening item. |

### P7, emulator and support software installation

On-demand emulator installation, ROM pack support, and in-app guidance cards with
official download links. No emulator binary is redistributed in the repository.

- Binary detection for every emulator; dead download machinery removed from
  `emulator_installer.py`; HTTP 501 removed from the install route.
- Guidance cards for the 86Box ROM pack (with a Git Clone button) and BIOS files,
  surfaced in the first-run wizard and the emulator catalog page.
- Flycast (Dreamcast) backend added.
- Attribution page in Settings with GPL source links and copyright notices.

### P6.5, household user accounts and parental controls

One owner account plus multiple sub-accounts, each with a 4 to 6 digit PIN secured with
Argon2id.

- `users` and `user_restrictions` tables, seeded at first run.
- `scripts/setup_admin_user.py` creates or overwrites the owner account interactively,
  and doubles as a standalone recovery tool.
- Four consecutive PIN failures lock the account. The increment-and-lock is a single
  atomic `UPDATE`, so concurrent requests cannot both slip past the threshold.
- Content ratings ingested at scan time from NFO sidecars, disc metadata, or filenames.
- Rating enforcement is server-side and **fails closed**: an unrecognised rating, or a
  user ceiling that no longer resolves to a known ordinal, denies rather than passes.
- Permission flags gate every mutating endpoint; the owner bypasses all of them.
- PS4-style profile switcher on the home screen with a PIN entry modal.

| Date | Decision |
|---|---|
| 2026-05-12 | Auth model finalised for P6.5: owner plus sub-accounts, Argon2id PIN hashing, 4-attempt lockout, owner reset via settings, emergency recovery via a local script. Replaces the placeholder profile-switching concept. |

### P6, Windows host isolation and resource limits

| Date | Decision |
|---|---|
| 2026-05-07 | **Job Objects required for all Windows emulator launches.** Every launch is assigned to a Job with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` and a sane default CPU cap, guaranteeing emulator trees are torn down if the backend exits. |
| 2026-05-07 | *(Reversed 2026-05-13.)* Windows emulator launches run under a dedicated low-privilege `peach_sandbox` account, as a stepping stone toward AppContainer. |
| 2026-05-13 | **`peach_sandbox` removed entirely.** The restricted account blocked audio access for all emulators, required the backend to run as Administrator, and added significant setup complexity for marginal gain. Emulators now run as the current user, contained by Job Objects. Account-level isolation deferred to AppContainer. |
| 2026-05-13 | **Conf-merge approach removed; inline `-c` args confirmed sufficient.** The real root cause of the P6 launch failures was `peach_sandbox` lacking ACL read access, not path formatting or conf parsing. `dosbox_paths.py` and all merge machinery removed. |
| 2026-05-07 | **Windows Firewall COM network blocking removed.** Rule creation via COM requires elevation and fails with `E_ACCESSDENIED` on standard installs. **Network isolation is emulator-native instead:** each emulator launches with its network adapter disabled or absent when `enable_networking` is false. No elevation required, and harder for emulated software to work around than a host firewall rule. |
| 2026-05-07 | `enable_networking` added to the profile model, default false. |
| 2026-05-19 | **Qt-based emulators require `skip_memory_limit` in the Job Object.** Qt's platform-plugin startup fast-fails with `STATUS_STACK_BUFFER_OVERRUN` (`0xC0000409`) when `JOB_OBJECT_LIMIT_PROCESS_MEMORY` is applied post-creation. Confirmed on 86Box 5.3 / Qt 5.15.18 on Windows 11. Kill-on-close and CPU rate control are unaffected. |
| 2026-06-01 | **Memory cap model revised.** Era caps had been sized for guest hardware only. Managed-runtime and JIT emulators pre-allocate heap at startup regardless of game load and hit the same fast-fail. Caps now reflect emulator overhead plus headroom, not guest hardware. |
| 2026-06-01 | BIOS paths removed from `settings.yaml`. Every emulator resolves BIOS files relative to its own binary directory. |
| 2026-05-17 | **Environment image path allowlist removed.** Images may live on secondary drives, external volumes, and NAS shares. The tradeoff is explicit: traversal protection for these paths now relies on OS filesystem permissions and the user trust model, not an application-level allowlist. Tracked as a known security gap. |
| 2026-05-17 | Emulator path model set as bundled, catalog-detected, or settings override. *(All but the bundled tier were later removed as dead code, 2026-08-04.)* |
| 2026-05-29 | **`/media` static mount replaced with an authenticated route.** `StaticFiles` bypasses `BaseHTTPMiddleware` entirely, so `SecurityMiddleware` never ran for mounted paths. BIOS, ROM, and OS image files are no longer passively exposed to network clients when `ALLOW_NETWORK_ACCESS=true`. |
| 2026-05-29 | **Library update path fields validated through `normalise_path`.** `PATCH` previously accepted arbitrary strings for `media_path`, `executable_path`, `folder_path`, and `cover_art_path` with no validation. All four now go through null-byte and traversal rejection; the first two additionally assert existence. |
| 2026-05-25 | Persistent drive model added to Profile: DOS and Win3.1 need a writable C: to persist sound config, saves, and installed files. |
| 2026-05-25 | `library/` split into `media/` (user-facing, scanned) and `system/` (OS images, drives, ROMs, BIOS, saves; never scanned or shown). |
| 2026-05-25 | `.exe` and folder media supported for DOS and Win3.1, mounted via `MOUNT D <dir>` rather than `imgmount`. |
| 2026-05-27 | Drive CRUD extracted into `drive_utils.py`; FAT16 minimum size floor set to 10 MB. |
| 2026-05-27 | Era auto-detection on scan and manual add: ISO 9660 PVD, PE headers, directory heuristics, extension fallback. `detection_reason` persisted and surfaced in the UI. |
| 2026-05-27 | Platform and profile auto-assigned at add and scan time via `defaults_for_era`. |
| 2026-05-22 | `-noconfig` added to DOSBox-X launch args, because DOSBox-X otherwise loads its bundled conf from the working directory and overrides the generated `output=surface` with `output=ttf`. |

### P5, architecture consolidation and schema unification

| Date | Decision |
|---|---|
| 2026-05-07 | **FastAPI's OpenAPI spec is the single source of truth for types.** TypeScript types generate from it via `openapi-typescript` into `shared/types.ts`. The hand-maintained frontend type file was deleted. |
| 2026-05-07 | **SQLModel replaces the SQLAlchemy plus Pydantic dual layer.** The three-layer model was a hedge toward a Postgres migration that is not planned. SQLModel collapses ORM and schema into one definition. |
| 2026-05-07 | **Alembic removed in favour of `create_all()` on startup.** Migration overhead is not justified while no real user data exists and the DB can be wiped freely. Revisit when user data must survive schema changes. |

Also: the database moved to `database/data/`, and the static frontend build became a hard
prerequisite for backend start (the Vite dev server is opt-in for frontend work only).

### P4, console backends

Expanded beyond PC using the same profile and launch architecture: DuckStation (PS1),
PCSX2 (PS2), Project64 (N64), Mesen (NES), xemu (Xbox OG), later Flycast (Dreamcast).
Added `.chd` and `.xiso` format support and an in-app cartridge imaging guide.

### P3.5, web UI

Replaced the Textual TUI with a React and TypeScript frontend served by FastAPI.

| Date | Decision |
|---|---|
| 2026-05-06 | **Native installer, replacing Tauri and Docker.** PyInstaller compiles the backend; React is served as static files by FastAPI; pystray provides the tray icon. No Rust, no Docker, no separate web server. |
| 2026-05-06 | **Tailwind CSS pinned to v3.** v4 introduces breaking syntax changes and shadcn/ui does not support it. Do not upgrade until it does. |
| 2026-05-06 | Profile model decoupled from media items: profiles are global and reusable, and an item stores a nullable `selected_profile_id`. Tying profiles to items would force duplication of identical config. |
| 2026-05-06 | Launch requires profile selection; the Launch button is gated until a valid profile is assigned. |
| 2026-05-06 | Platforms and profiles pre-seeded at first run. Seeding is defensive: it warns rather than crashing, and platforms are created even when the binary is absent (the UI then shows the official download link). |
| 2026-05-06 | Library scan path restricted to configured base directories. The previous implementation passed the directory parameter straight to `scan_directory()` with no validation. |
| 2026-05-06 | `SessionMiddleware` added with a generated, persisted secret. *(Later removed entirely by the auth redesign.)* |
| 2026-05-06 | Recorded defect: the Win9x FastAPI launch path had an `OSPlatform` signature mismatch, resolved at the start of P5. |

### P3, maturity

Stability, test coverage, and graceful failure handling across every supported era:
first-run setup wizard, library scanner, per-game config history, manual emulator binary
override, network-block verification on every launch, community known-titles database,
and platform health checks with recovery prompts.

### P2, Windows 95/98/XP direct launch

Register a Windows OS environment and launch software from it through the correct backend.
Two media paths: pre-installed HDD images (primary, zero install friction) and original
installer media (user completes the install manually inside the emulator).

| Date | Decision |
|---|---|
| 2026-05-17 | **Win9x backend flipped from VirtualBox to 86Box.** VirtualBox gives near-native CPU speed but poor compatibility for titles needing cycle-accurate timing, specific chipset behaviour, or legacy peripheral emulation. 86Box is the preservation standard for Win9x software, and these titles are preservation targets, not performance benchmarks. |
| 2026-05-17 | **VirtualBox removed from the emulator stack entirely.** It resists portable mode and requires a system service (`VBoxSDS`) the launcher cannot cleanly manage. All Win9x and XP launches route to 86Box. |
| 2026-05-19 | **86Box VM directory layout follows portable-mode conventions.** 86Box resolves every config path relative to the VM directory. Splitting config, disk images, and binaries across separate trees causes path-resolution failures, so all VM working files live together under `emulators/86box/vms/<slug>/`. The installation ISO stays in `library/os/` as read-only source media, referenced by absolute path. |
| 2026-05-19 | **Environments are a UI abstraction over that layout.** Users see a name, era, hardware profile, and installation media; on disk each environment is a subdirectory under `emulators/86box/vms/<slug>/`. |
| 2026-05-14 | **Platforms renamed to Environments**, and the Platforms page merged into Emulators (it was showing emulator binary status, which belongs there). |
| 2026-05-14 | **Library items and Environments are distinct execution models.** Library items follow launch, play, cleanup, with state torn down after every session. Environments are persistent managed workspaces for software needing installation, registry state, or long-term OS persistence. The distinction is consumable versus persistent, not game versus tool. |
| 2026-05-14 | **Profiles are scoped to emulators, not eras**, because settings are emulator-specific. Tags associate profiles with environments and content types instead of hard FK relationships. |
| 2026-05-14 | Tags system with pre-created system tags for emulators, eras, hardware configs (voodoo, mt32, soundblaster, adlib, ega, vga, svga), and content types. Users add custom tags on top. |
| 2026-05-14 | **Peach 1UP only manages processes it launches directly.** Software launched externally, including emulator installers via `ShellExecute`, runs outside process tracking, Job Objects, and launch history. Intentional, and surfaced in the UI near Run Installer buttons. |
| 2026-05-14 | `images/` renamed to `library/` with per-item folders, so users can drop in cover art and supplementary files without backend involvement. |
| 2026-05-03 | **`OSPlatform` model for Win9x/XP.** Per-game OS installs are impractical. One shared OS image per era with a base plus working copy is the correct architecture, matching eXoDOS, 86Box power users, and VM tooling. |
| 2026-05-03 | **Pre-installed HDD image is the primary media path.** 90s installers are interactive and wildly inconsistent; pre-installed images remove the install step entirely. Original media stays supported as a secondary path. |
| 2026-05-03 | **DOSBox-X scope limited to DOS and Win3.1.** For Win95/98 it is a compatibility fallback only, for DOS applications running under a Windows shell, never for native Win32 software. |

Also shipped: era hardware templates in `config/` (not hardcoded), base and working image
management (the base is locked and never modified), media attachment at launch time with
`autorun.inf` detection, a community-curated known-titles database with a user-facing
Hardware accuracy mode checkbox, an OS platform guidance screen linking to community
sourcing resources without automating any download, basic platform snapshots, and CD-ROM
passthrough for original discs.

### P1.5, polish and documentation

Documentation pass across modules (module docstrings, Google-style docstrings, inline
comments for esoteric code), the first README covering objective, prerequisites, and
setup, a dead-code sweep, and a wizard-flow audit for dead ends and missing feedback.

### P1, core usability (DOS proof of concept)

Per-game YAML profiles, generated DOSBox-X configs tuned per era, persistent virtual hard
drives created and reused per profile, an install-once flow with direct launch thereafter,
media auto-detection, a UAC manifest for auto-elevation, missing-emulator guidance with
official links, and a settings screen.

| Date | Decision |
|---|---|
| 2026-04-16 | P1 scope is DOS direct launch only. Console backends and Win95/98/XP direct launch deferred to P2. The goal: drop in a DOS ISO, pick it, the game runs, no emulator interaction required. |
| 2026-04-16 | Conditional ROM warning on the era selector, shown only when the ROM pack is absent and accuracy mode is available. Checked at render time, so it disappears once the pack is present with no restart. |

### P0, bare minimum working launcher (2026-04-15 to 2026-04-16)

Project scaffold, the Windows Job Objects wrapper, DOSBox-X and 86Box backends, a Textual
TUI with era selector and game picker, the end-to-end launch flow, and an error-handling
layer that surfaces every failure rather than crashing silently.

| Date | Decision |
|---|---|
| 2026-04-15 | **Native Windows plus Job Objects for emulators.** Windows containers are unstable on Home edition and Linux containers have no official emulator binaries. Emulators sandbox game code natively; Job Objects cover host process isolation, resource limits, and filesystem restriction. Read-only mounts enforced from P0. |
| 2026-04-15 | **Networking disabled via Job Objects.** Safety rule, no multiplayer in scope. *(Later replaced by emulator-native blocking, 2026-05-07.)* |
| 2026-04-15 | DOSBox-X for DOS and Win3.1: no ROM requirement, works immediately, strong DOS accuracy. |
| 2026-04-15 | Textual for the TUI: keyboard-driven, Python-native, good docs. GUI deferred. |
| 2026-04-15 | No persistence in P0, disk images only in P0. Physical drive passthrough deferred. |
| 2026-04-15 | `DECISIONS.md` established as a separate append-only decision log, to keep `CLAUDE.md` and `CONTEXT.md` clean. *(Retired 2026-08-12, merged into this file.)* |

## Founding decisions (2026-04-15 to 2026-05-05)

| Date | Decision |
|---|---|
| 2026-05-05 | **Peach 1UP is a preservation automation tool.** The gap it fills is the path from "I have this old media" to "it is running correctly" with no manual emulator configuration. |
| 2026-05-05 | **Library is the primary entity name.** Software, game, tool, application, and utility are metadata tags, not structural distinctions. |
| 2026-05-05 | **A profile is a hardware-era launch preset**, not a per-game config. Bundled presets ship out of the box, fully user-editable and forkable. |
| 2026-05-03 | **The user supplies all ROMs and BIOS assets.** No bundled ROMs, BIOS files, or OS images, and no automated fetching of copyrighted media. Peach 1UP provides guidance and links only. |
| 2026-05-05 | FastAPI as the backend framework, with an auto-generated OpenAPI spec driving a typed React client. |
| 2026-05-05 | React and TypeScript for the frontend, chosen over Vue for ecosystem size. Vite for build tooling. |
| 2026-05-05 | SQLite via SQLAlchemy, sufficient for read-heavy single-library usage. Prisma rejected as Node-native and awkward alongside a Python backend. |
| 2026-05-05 | Docusaurus for documentation: React-based, versioned, MDX, full-text search. |
| 2026-05-03 | **Docker removed from the runtime architecture.** No role in emulator execution or isolation. Supersedes the two 2026-04-15 Docker decisions. |
| 2026-05-03 | Console scope set to PS1, N64, NES, and Xbox OG. |
| 2026-05-05 | PS2 moved from the backlog into P4. |

## Reversed and superseded decisions

Kept for the record. Every one of these was live at the time.

| Date | Decision | Outcome |
|---|---|---|
| 2026-05-05 | Linux-first application platform, running the app in Linux containers | Reversed 2026-07-17. Windows-only. |
| 2026-05-05 | Docker Engine (headless) as the primary install, with `start.bat` as fallback | Reversed 2026-05-06 (native installer) and 2026-05-03 (Docker removed from runtime). |
| 2026-05-05 | cgroups and namespaces replace Job Objects as the isolation layer | Cancelled 2026-07-17 with Linux support. |
| 2026-05-05 | Job Objects bypassed via `launch_direct` for DOS launches, because error 5 blocked assignment on Windows 11 | Superseded by the `CREATE_BREAKAWAY_FROM_JOB` retry path. |
| 2026-05-03 | VirtualBox as the default for Win95/98 and XP | Superseded 2026-05-17. |
| 2026-05-03 | 86Box as opt-in accuracy mode only | Superseded 2026-05-17; 86Box is the only Win9x/XP backend. |
| 2026-05-07 | Windows 7 added to the VirtualBox era mapping | Void; VirtualBox removed. |
| 2026-05-14 | VirtualBox Expert Mode set via `VBoxManage` post-install | Void; VirtualBox removed. |
| 2026-05-14 | Emulator binaries bundled with the project, not downloaded at setup | Reversed 2026-08-03; all emulators install on demand. |
| 2026-05-07 | Emulator launches run under a dedicated low-privilege user | Reversed 2026-05-13. |
| 2026-05-07 | AppContainer deferred to a later phase (P8+) | Delivered in P9. |
| 2026-05-13 | `peach_sandbox` requires explicit ACL grants on emulator and media directories | Void with the account. |
| 2026-06-04 | xemu permanently excluded from AppContainer | Superseded 2026-08-11; the diagnosis was wrong. |
| 2026-05-25 | Persistent drive model added to Profile | Doubly stale; superseded by the per-item then shared-drive churn of 2026-07-01/02. |
| 2026-05-27 | Drive CRUD extracted into `drive_utils.py` | Same. |
| 2026-07-01 | DOS/Win3.1 converged to shared environment-style working images | Reverted 2026-07-02. |
| 2026-05-03 | Basic platform snapshots moved into P2 | Descoped 2026-07-05 in favour of DB plus `/emulators` backup. |
| 2026-04-16 | ROM pack via git clone as a bundled asset | Superseded 2026-05-03 (user supplies all assets). |

## Deferred, not built

Scoped or discussed, deliberately not shipped.

- **Linux support.** Out of scope permanently.
- **Vibepollo / game streaming.** Only relevant if a hosted route is ever taken.
- **Editable memory and CPU limit overrides in the UI.** The per-era values in
  `eras.yaml` are editable by hand only. There is no settings field and no UI control.
- **Platform image compression and deduplication.** Working copies and save backups
  accumulate; no storage-management tooling exists.
- **LLM-assisted emulator navigation.**
- **ROM/BIOS pack builder** for mixing and matching machines and software.
- **86Box floppy support.**
- **RetroArch `.cfg` import/export, SDL_GameControllerDB lookup, and per-emulator
  controller serializers.** The serializers are the piece that would make "map once, use
  everywhere" real; without them Controller Mapping is a storage form. Sequenced last
  because they are launch-path adjacent and need real hardware to test.
- **Owner PIN lockout via unauthenticated `/auth/switch`.** Four wrong owner PIN attempts
  lock the owner, forcing host-script recovery. Rate limited (30 per 60s per IP) but not
  prevented. Accepted under the household-trust threat model; only matters if exposed
  beyond the LAN.
