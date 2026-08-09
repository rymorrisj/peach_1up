# Changelog

Project history for Peach 1UP, assembled from the maintainer-managed
[`dev_docs/SCOPE.md`](dev_docs/SCOPE.md) (phase plan) and
[`dev_docs/DECISIONS.md`](dev_docs/DECISIONS.md) (decision log). Those two files remain
the authoritative sources; this is a condensed, chronological read of them.

The project has not cut a tagged release yet. `VERSION` reads `0.1.0` and the work below
is pre-alpha, running from 2026-04-15 to 2026-08-08. Entries are grouped by development
phase, newest first, with the decisions that shaped each one.

## Unreleased

### Platform consolidation (July to August 2026)

- **Windows-only.** Linux support and the earlier cgroups/network-namespaces isolation
  plan were removed from scope entirely. Process isolation is Windows Job Objects only,
  and the Linux code paths were deleted from the backend. (2026-07-17)
- **Detection and sandboxing extracted into standalone packages.** Disk-image and
  directory format detection became `formatscout`; Windows AppContainer and Job Object
  sandboxing became `wincage`. Both are vendored under `services/vendor/` and consumed as
  dependencies rather than living in-tree.
- **Generated files are never committed.** `constants_generated.py`,
  `generated/constants.ts`, `shared/openapi.json`, and `shared/types.ts` are regenerated
  by a dedicated CI job that the backend and frontend test jobs depend on, closing the
  A/B drift risk between the two type pipelines. (2026-07-08)
- **CI added.** GitHub Actions now runs the backend pytest suite with coverage on
  `windows-latest`, the frontend vitest suite with coverage, type generation, and CodeQL
  static analysis on every push and pull request to `main`.
- **Storage model simplifications.** Environment snapshots were descoped in favour of DB
  plus `/emulators` backup; scan/import became stateless with the preview cache removed;
  full-delete-on-removal became a settings flag rather than an `_archive` folder.
  (2026-07-05)
- **Per-item Drive model restored.** The DOS/Win31 shared-environment-drive convergence
  was reverted back to per-item drives. (2026-07-02)
- **CHD era resolution fixed.** PS1 versus PS2 CHD ambiguity is now broken by logical
  size instead of hard-defaulting to PS2, since Tier-1 hash lookup cannot resolve CHD era.
  (2026-07-03)

### P-META, TheGamesDB metadata enrichment

Manual, on-demand metadata enrichment. The user searches TheGamesDB, confirms a match,
and applies cover art and detail fields to the chosen entity. No scan-time auto-fetch and
no background jobs.

### PX-2, architecture refactors

Audit-driven refactors needed before console support could be trusted, including the
DOSBox-X per-launch config isolation fix (each launch now writes its conf to its own
`tempfile.mkdtemp()` directory instead of a shared location a concurrent launch could
clobber mid-read).

### PX-1, era and console completion

Closed the remaining era gaps and verified every console backend launches end to end, on
the principle that backend existence is not the same as confirmed launch. PS3 (RPCS3) and
Xbox 360 (Xenia) joined the supported set alongside the original PS1, PS2, Xbox OG, NES,
SNES, N64, and Dreamcast targets.

### Auth redesign, per-client token auth

- **Session tokens are HMAC-derived per user.** Each user row carries an
  `identity_token_secret` root key; only a SHA-256 hash of the live session token is
  persisted. There is no separate token table, so one active session per user falls out of
  the design.
- **Refresh validates and extends, never rotates.** The prior design minted a new token on
  every refresh, so two near-simultaneous refreshes from the same session raced and
  spuriously signed the user out. Token issuance is now exclusive to setup-owner and
  switch. (2026-06-20)
- **Argon2id pepper is mixed directly into the hash secret**, with the documented
  consequence that rotating it invalidates every existing hash with no migration path.
  (2026-06-23)

### P-Smart Scan, executable detection

Two-tier detection for one-click launch accuracy: a bundled offline hash index built from
community Redump/No-Intro datasets, plus an optional LLM-assisted config path for users
supplying their own API key.

- xiso detection via magic string at offset `0x10000`, and CHD platform detection via
  metadata tag. (2026-06-02)
- `requires_install` scoped to DOS and Windows 3.1 only. (2026-06-21)

### P9, Windows AppContainer isolation

Layered AppContainer on top of the existing Job Object wrapper for filesystem, network,
and inter-process containment.

- **Regular AppContainer adopted, LPAC rejected.** Stripping ALL APPLICATION PACKAGES
  breaks OpenGL ICD loading from DriverStore and reproduced an earlier silent-failure
  pattern. (2026-05-21)
- **Per-emulator rollout** via the `container_enabled` flag; emulators that have not
  passed the test matrix ship under Job Object only, with no unsandboxed fallback ever.
  (2026-05-21)
- **CPU rate control switched from `HARD_CAP` to `MIN_MAX_RATE`.** `HARD_CAP` starves
  threads to zero CPU at interval end, muting the host WASAPI audio session; a non-zero
  `MinRate` reserves a floor for the audio thread. (2026-05-21)
- **xemu permanently excluded from AppContainer**, since QEMU's TCG backend calls
  `DeviceIoControl` for qcow2 disk geometry and AppContainer blocks it. (2026-06-04)
- **Broker file model replaced direct DACL grants**, and a window station grant was found
  to be required for AppContainer GUI processes. (2026-05-22)

### P8, native installer and distribution

Packaged as a native Windows installer with no runtime dependencies for end users:
PyInstaller for the backend, NSIS for the installer, and WinSW to register the service.

### P7, emulator and support software installation

On-demand emulator installation from upstream GitHub releases, ROM pack support, and
in-app guidance cards with official download links. No emulator binary is redistributed
in the repository.

### P6.5, household user accounts and parental controls

One owner account plus multiple sub-accounts, each with a 4 to 6 digit PIN secured with
Argon2id. Restricted accounts hide content above their rating ceiling, with the filter
failing closed. Permission flags gate every mutating endpoint, and the owner bypasses all
of them.

### P6, Windows host isolation and resource limits

- **Job Objects required for all Windows emulator launches**, with kill-on-close and a CPU
  cap. (2026-05-07)
- **The dedicated low-privilege account approach was tried and removed.** The
  `peach_sandbox` account required explicit ACL grants on emulator and media directories
  and produced silent failures; emulators now run as the current user, contained by Job
  Objects. (2026-05-07, reversed 2026-05-13)
- **Memory cap model revised.** Era caps were sized for guest hardware, but managed-runtime
  and Qt emulators pre-allocate heap at startup and fast-fail with
  `STATUS_STACK_BUFFER_OVERRUN` when a process memory cap is applied post-creation, so
  those emulators set `skip_memory_limit`. (2026-05-19, revised 2026-06-01)
- **Network isolation is emulator-native.** Windows Firewall COM blocking was removed in
  favour of launching each emulator with its network adapter disabled when
  `enable_networking` is false on the active profile. (2026-05-07)
- **Environment image path allowlist removed**, so images may live on secondary drives,
  external volumes, and NAS shares. Documented as an accepted trade-off. (2026-05-17)

### P5, architecture consolidation and schema unification

- **FastAPI's OpenAPI spec became the single source of truth for types**, generating the
  TypeScript client and removing manual duplication across the stack. (2026-05-07)
- **SQLModel replaced the SQLAlchemy plus Pydantic dual layer**, and Alembic was dropped
  in favour of `create_all()` on startup. (2026-05-07)

### P4, console backends

Expanded beyond PC to console platforms using the same profile and launch architecture:
PS1 (DuckStation), PS2 (PCSX2), Xbox OG (xemu), NES and SNES (Mesen), N64 (Project64),
and Dreamcast (Flycast).

### P3.5, web UI

Replaced the Textual TUI with a React and TypeScript frontend served by FastAPI.

- **Docker removed from the runtime architecture** and the native installer chosen over
  Tauri and Docker packaging. (2026-05-03, 2026-05-06)
- Tailwind CSS pinned to v3. (2026-05-06)

### P3, maturity

Stability, test coverage, and graceful failure handling across every supported era.

### P2, Windows 95/98/XP direct launch

Register a Windows OS environment and launch software from it through the correct backend.
Two media paths: pre-installed HDD images (primary, zero install friction) and original
installer media.

- **86Box replaced VirtualBox as the Win9x/XP backend**, and VirtualBox was then removed
  from the emulator stack entirely. (2026-05-17)
- **Environments are a UI abstraction over the 86Box VM directory layout**, which itself
  follows 86Box portable-mode conventions. (2026-05-19)
- **Platforms renamed to Environments**, and the Platforms page merged into Emulators.
  (2026-05-14)

### P1.5, polish and documentation

Documentation pass across modules, plus the first README covering objective,
prerequisites, and setup.

### P1, core usability (DOS proof of concept)

Per-game YAML profiles, generated DOSBox-X configs tuned per era, persistent virtual hard
drives, an install-once flow with direct launch thereafter, and media auto-detection.

### P0, bare minimum working launcher

Project scaffold, the Windows Job Objects wrapper, DOSBox-X and 86Box backends, a Textual
TUI with era selector and game picker, the end-to-end launch flow, and an error-handling
layer that surfaces every failure rather than crashing silently. (2026-04-15 to
2026-04-16)

## Founding decisions (2026-04-15 to 2026-05-05)

- **Peach 1UP is a preservation automation tool**: point it at a disk image, pick an era,
  and the correct emulator launches with media mounted and sensible defaults applied.
- Native Windows plus Job Objects chosen for emulator isolation, with networking disabled
  at launch.
- The user supplies all ROMs and BIOS assets. Peach 1UP never provides, links to, or
  assists with acquiring them.
- FastAPI, React and TypeScript, SQLite, and Docusaurus chosen as the stack.
- A profile is a hardware-era launch preset, and the library is the primary entity.
- `DECISIONS.md` established as a separate append-only decision log.

> Note: a Linux-first platform decision (2026-05-05) and a Docker-headless install
> decision (2026-05-05) appear in the log but were both later reversed. See the
> Windows-only entry at the top of this file.
