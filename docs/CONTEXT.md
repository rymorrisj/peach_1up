# Peach 1UP — Session Context

## P0 — Bare Minimum Working Launcher

### DONE

- [P0-1] Project scaffold — folders, empty files, .env template, .gitignore
- [P0-2] Windows Job Objects wrapper — isolate emulator process, enforce resource limits, restrict filesystem access, block network
- [P0-3] DOSBox-X backend — locate binary via DOSBOX_PATH, mount media read-only, launch under Job Objects
- [P0-4] TUI skeleton — Textual app, keyboard navigation, main menu
- [P0-5] Era selector screen — DOS / Win 3.1 / Win 95 / Win 98 / Win XP
- [P0-6] Game picker screen — browse filesystem for .iso / .img / .cue files
- [P0-7] Launch flow — era + media → correct backend → Job Objects → emulator running
- [P0-8] Error handling layer — all failures surface to TUI with message, no silent crashes
- [P0-9] 86Box backend — locate binary via BOX86_PATH, validate ROM path, launch under Job Objects
- [P0-10] P0 committed and pushed to main

## P1 — Core Usability (DOS proof of concept)

### DONE

- [P1-1] Game profile system — save/load per-game YAML (era, media path, backend, dosbox conf path, hdd image path, notes)
- [P1-2] DOSBox-X config generation — generate .conf per game profile with correct cpu cycles, memory, sound defaults tuned per era
- [P1-3] Virtual hard drive management — auto-create and persist .img per game profile, reused on subsequent launches
- [P1-4] Game installation flow — detect installer ISOs, run install once, save installed flag to profile
- [P1-5] Direct launch — on subsequent launches boot straight to DOS prompt with drives mounted, no reinstall
- [P1-6] Profile screen in TUI — create, edit, launch from saved profile
- [P1-7] Media auto-detection — sniff .iso/.img/.cue and suggest era (best effort)
- [P1-8] Auto-elevation — UAC manifest so launcher requests admin on startup, no manual run as admin required
- [P1-9] Missing emulator guidance — detect missing binaries, show official links in TUI
- [P1-10] Settings screen — paths, display config, ROM path, editable in TUI
- [P1-11] Refactor is_rom_pack_present() — replace empty string sentinel with explicit Optional[str] parameter signature
- [P1-12] P1 committed and pushed to main

## P1.5 — Polish, Documentation, and Complete Core Experience

### DONE

- [P1.5-1] Documentation pass — module docstrings, inline comments for complex/esoteric code, Google-style docstrings for classes and non-trivial functions
- [P1.5-2] README update — project objective, prerequisites, installation steps, how to run
- [P1.5-3] Dead code sweep — remove stale comments, unused imports, leftover scaffolding
- [P1.5-4] Launcher wizard flow audit — confirm no dead ends, missing feedback, or confusing prompts
- [P1.5-5] P1.5 committed and pushed to main

## P2 — Win95/98 and XP Direct Launch

> VirtualBox removed 2026-05-17 — all Win9x and XP now handled by 86Box

### Goal

A user can register a Windows OS platform and launch software from it via the correct
emulator backend. Two media paths are supported: pre-installed HDD images (primary,
zero install friction) and original installer media (supported, user completes install
manually inside the emulator). The user never selects or configures an emulator directly.

### Emulator Strategy

| Era     | OS            | Primary  | Fallback          | Logic                                     |
| ------- | ------------- | -------- | ----------------- | ----------------------------------------- |
| DOS     | MS-DOS        | DOSBox-X | —                 | Always DOSBox-X                           |
| Win 3.x | Windows 3.1   | DOSBox-X | —                 | Runs inside DOS session                   |
| Win 9x  | Windows 95/98 | 86Box    | DOSBox-X (compat) | 86Box default. See selection logic below. |
| Win XP  | Windows XP    | 86Box    | —                 | Always 86Box                              |

**Win 9x selection logic:**

- Default → 86Box (accuracy and game compatibility).
- DOS app running under Windows → DOSBox-X (better DOS compatibility)
- User enables accuracy mode OR title is in known titles database → 86Box (Note: 86Box is now the default for all Win9x; this condition is obsolete as of 2026-05-17.)

**Accuracy mode:**
A user-facing "Hardware accuracy mode" checkbox on profile creation. Never exposes
emulator names. Clear tradeoff language: "Slower but required for some games with
specific hardware needs." When checked, Win9x routes to 86Box. Note: with 86Box as the 2026-05-17 default, this checkbox no longer changes the backend route — its current function and UI status should be reviewed before P9.

### Media Paths

**Primary — Pre-installed HDD image**
User provides a HDD image with OS and software already present. Peach 1UP registers
the image as a platform, creates a working copy, and launches directly. No installation
step required.

**Secondary — Original installer media**
User provides an installer ISO or disc image. Peach 1UP mounts the media, boots the
platform, and presents the user at the desktop with the disc attached. User completes
the installer manually. We detect autorun.inf and surface the correct entry point
where possible.

### DONE

- [P2-1] OSPlatform data model — new OSPlatform dataclass with name, era, emulator
  backend, config path, base image path, working image path, notes, and status.
  Stored in platforms.yaml. Profiles reference a platform instead of owning a machine.
- [P2-2] Platform registration flow — TUI screen with: file picker (.img, .vhd,
  .iso), OS dropdown, auto-selected emulator shown as read-only, file size and
  header validation with trust warning, and for Win95/98: hardware accuracy mode
  checkbox and "This is an installer disc or image, not a pre-installed image.
  You will need to run the installation manually" checkbox.
- [P2-3] Era hardware templates — pre-built emulator config templates per era:
  DOSBox-X for DOS and Win3.1, VirtualBox for Win95/98 (default) and XP, 86Box for
  Win95/98 accuracy mode only. Stored in config/ as YAML, not hardcoded in Python.
  (Note: default flipped to 86Box as of 2026-05-17; see DECISIONS.md.)
- [P2-4] Base and working image management — on first registration, base image
  is locked and a working copy is created in images/os/{era}/. All launches use
  the working copy. Base is never modified. User is warned at registration that
  two copies of the image will be stored and disk usage will grow over time.
- [P2-5] Media attachment logic — attach game ISO or disc image to the platform at
  launch time. DOSBox-X via autoexec imgmount, VirtualBox via Python API. Detect
  autorun.inf and surface entry point to user where found.
- [P2-6] Known titles database and accuracy toggle — YAML database of titles known
  to require 86Box accuracy mode. User-facing "Hardware accuracy mode" checkbox on
  profile creation. Default to VirtualBox for performance. User can override if they
  encounter issues. Community-extensible.
- [P2-7] 86Box accuracy path — when user enables accuracy mode or title is in known
  titles database, route Win95/98 to 86Box with era hardware config from template.
  Show clear warning: accuracy mode is slower and only needed for specific hardware
  requirements.
- [P2-8] VirtualBox backend — new backends/virtualbox.py using VirtualBox Python API.
  Register VM from image, attach media, launch, monitor under Job Objects.
- [P2-9] OS platform guidance screen — shown when no platforms are registered.
  Explains both media paths, links to WinWorldPC and community resources for sourcing
  images, explains licensing clearly without automating any downloads.
- [P2-10] Platform snapshots (basic) — create a named snapshot of the working image
  before risky operations (new software install, major config change). Restore from
  any snapshot to replace the working image. Delete snapshots manually to reclaim
  space. No compression or auto-management — that stays in PX. User is warned that
  each snapshot is a full image copy and will consume significant disk space.
- [P2-11] Physical drive support — CD-ROM passthrough for users playing from original
  discs rather than ISO images.
- [P2-12] Known titles database schema — YAML schema for community-curated titles.
  Fields: name, era, requires_86box (bool), hardware notes, renderer notes. Shipped
  with the project and community-extensible via pull request.
- [P2-13] P2 committed and pushed to main

## P3 — Maturity

### Goal

The launcher is stable, well-tested, and handles failure gracefully across all supported eras.

### DONE

- [P3-1] First-run setup wizard — detect missing binaries and platforms, guide through setup
- [P3-2] Game library scanner — scan a directory, auto-build profiles from found media
- [P3-3] Per-game config history — track changes to profiles over time
- [P3-4] Manual emulator binary override — user drops in custom build, tool detects it
- [P3-5] Network block verification — confirm Job Objects network restriction is enforced on every launch
- [P3-6] Known titles database — community YAML of titles with hardware requirements, used by accuracy detection
- [P3-7] Platform health checks — detect degraded or broken OS images, prompt for recovery
- [P3-8] P3 committed and pushed to main

## P3.5 — Web UI and Docker Compose

### Goal

Replace the TUI with a web-based frontend. FastAPI serves the backend. React
and TypeScript power the frontend. Docker Compose is the primary install
method. start.bat provided as a fallback for Windows users who cannot run Docker.

### DONE

- [P3.5-1] Migrate config from .env to settings.yaml — move all path variables
  (DOSBOX_PATH, BOX86_PATH, VIRTUALBOX_PATH, ROM_PATH, IMAGES_PATH, PROFILES_PATH)
  into settings.yaml as top-level keys. settings.py reads them from there. Keep .env
  as a legacy override — values present in .env take precedence over settings.yaml.
  .env.template updated to reflect secrets-only purpose going forward.
- [P3.5-2] FastAPI backend service — REST API, OpenAPI spec auto-generated,
  Pydantic models, SQLite database via SQLAlchemy, Alembic migrations
- [P3.5-3] React/TypeScript frontend — Vite build, TanStack Query, Zustand,
  React Router, Tailwind CSS, shadcn/ui. Replaces the Textual TUI entirely.
- [P3.5-4] Docker Compose install — single compose up brings up backend and
  frontend. Volumes for profiles, images, and config. Linux-first, WSL2 on Windows.
- [P3.5-5] start.bat fallback — for Windows users who cannot run Docker. Launches
  FastAPI backend and serves the React build directly.
- [P3.5-6] First-run wizard (web) — replace the TUI wizard with a web-based
  guided setup flow for binary detection, platform registration, and first launch.
- [P3.5-7] One-click emulator install — wizard downloads and places small
  emulators (DOSBox-X, 86Box, DuckStation, Mesen, Project64, xemu, PCSX2)
  directly into peach_1up/emulators/{slug}/. VirtualBox triggers the official
  Oracle installer. Existing installations can be used via manual override.
  Backend auto-detects binaries in the project emulators/ directory on startup.
- [P3.5-8] Remove Docker artifacts — delete docker-compose.yml,
  backend/Dockerfile, frontend/Dockerfile, frontend/nginx.conf,
  docker-start.sh, docker-start.bat. Update README.md, TECH.md, and CLAUDE.md
  to remove all Docker references. Update .gitignore. start.sh and start.bat
  retained for development only.

## P4 — Console Backends

### Goal

Expand beyond PC to first-generation console platforms using the same profile and launch architecture.

### DONE

- [P4-1] Console backends — DuckStation (PS1), PCSX2 (PS2), Project64 (N64), Mesen (NES), xemu (Xbox OG)
- [P4-2] Era/platform selector expansion — add console platforms to era selector
- [P4-3] Cartridge imaging guide — in-app guide for users to dump cartridge media per platform (NES, N64, Game Boy etc.) with recommended hardware
- [P4-4] Expanded file format support — .chd, .xiso per platform
- [P4-5] P4 committed and pushed to main

## P5 — Architecture Consolidation and Schema Unification

### Goal

Eliminate type duplication across the stack. FastAPI OpenAPI spec becomes the single
source of truth for all types. Database and shared artifacts are relocated and
consolidated. Static frontend build is always present.

### DONE

- [P5-1] Move database to /database/data/ — relocate peach1up.db, update engine
  config, .gitignore, .env, and all path references. /database/ owns schema and config.
  No direct db path references outside of config.
- [P5-2] Replace SQLAlchemy + Pydantic dual-layer with SQLModel — one class drives
  the database schema, API response shape, and OpenAPI spec. Remove Alembic entirely.
  SQLModel create_all() on startup replaces migration management. Revisit migrations
  only when real user data exists that cannot be wiped
- [P5-3] /shared directory and OpenAPI type generation — export OpenAPI spec to
  /shared/openapi.json on startup and via a standalone dev command. Use
  openapi-typescript to generate /shared/types.ts. Frontend imports all API types
  from /shared/types.ts only. Delete frontend/src/types/index.ts.
- [P5-4] Static frontend always built and served — frontend/dist must exist before
  backend starts. Pre-start check builds if missing or stale. StaticFiles mount in
  main.py is unconditional. Vite dev server is opt-in for frontend development only.
- [P5-5] Update start.sh and start.bat — build frontend if dist missing, start
  backend, open browser. Document dev workflow: npm run dev is opt-in, not default.
- [P5-6] P5 committed and pushed to main.

## P6 — Windows Host Isolation and Resource Limits

### Goal

Emulators launched on Windows run under a dedicated low-privilege account
and are contained in Job Objects with CPU limits and kill-on-close semantics.
This improves host safety without blocking on AppContainer or Linux namespaces.

### DONE

- [P6-1] Design Windows sandbox model and config surface
- [P6-2] Create and manage low-privilege `peach_sandbox` user at install time
- [P6-3] Implement Job Object wrapper with CPU (and optional memory) limits
- [P6-4] Integrate sandboxed launch path into emulator backends
- [P6-5] Update LaunchHistory and diagnostics for sandboxed sessions
- [P6-6] Add configuration and UX for per-profile resource caps
- [P6-7] Hardening and regression tests on Windows 10/11
- [P6-8] Documentation updates (DECISIONS.md, SECURITY.md, user docs)
- [P6-9] P6 committed and pushed to main.

## P6.5 — Household User Accounts and Parental Controls

### Goal

Auth was removed in a prior change and we re-worked it to amtch the system intended use.
A household can create one owner account and multiple sub-accounts. Each account
uses a 4–6 digit PIN secured with Argon2id. Restricted accounts hide content
above their rating threshold and cannot access features beyond their permission
flags. The owner can reset any PIN via settings. If the owner is locked out,
a local recovery script resets the owner account.

### DONE

- [P6.5-1] users and user_restrictions tables — SQLModel models, seeded at first run
- [P6.5-2] scripts/setup_admin_user.py — creates or overwrites owner account interactively; called by lifespan on first run, available as standalone recovery tool
- [P6.5-3] PIN verification endpoint — Argon2id verify, increment failed_pin_attempts, lock on 4th failure
- [P6.5-4] Session handling — active user_id in server session; default to owner if auth disabled
- [P6.5-5] Permission enforcement — FastAPI dependency checks flags on protected endpoints
- [P6.5-6] Content rating ingestion — scan NFO/metadata at library scan time, store on LibraryItem
- [P6.5-7] Rating enforcement — filter library query by active user's max_content_rating and block_unrated_media; server-side, not client-side
- [P6.5-8] Frontend — PS4-style profile switcher on home screen, PIN entry modal, hidden restricted items
- [P6.5-9] Owner settings — reset any user PIN, unlock locked accounts, manage sub-accounts
- [P6.5-10] P6.5 committed and pushed to main

## P7 — Emulator and Support Software Installion

### Goal

Add download support and include emulators that can be bundled and distributed with the app. This
includes ROM packs, extensions, updating /guides to give user instructions and including links.

### DONE

- [P7-1] — Binary detection for all bundled emulators; remove the dead download machinery from emulator_installer.py; wire VirtualBox installer launch via ShellExecute; poll for binary post-install; remove HTTP 501 from install route
- [P7-2] — Guidance cards for VirtualBox (with Run Installer button), BIOS files, 86Box ROM pack (with Git Clone button); surface in first-run wizard Step 2 and emulator catalog page
- [P7-2a] — Add ScummVM backend — locate binary, auto-detect games from data directory, launch under Job Objects, no BIOS required
- [P7-2b] — Add Flycast backend — locate binary, validate DC BIOS, launch under Job Objects
- [P7-3] — Attribution page in Settings (GPL source links, copyright notices, contributor section scaffold); update /guides for any emulator or asset requiring manual steps
- [P7-4] — Commit and push

## P8 — Native Installer and Distribution

### Goal

Package Peach 1UP as a native installer for Windows and Linux. No runtime
dependencies required for end users.

### DONE

- [P8-1] PyInstaller backend compilation — compile FastAPI backend and all
  dependencies into a standalone executable. Python runtime embedded. Tested
  on Windows.
- [P8-2] pystray tray icon — system tray icon with Open, Restart, and Quit
  options. Pure Python. Auto-opens browser on first launch.
- [P8-3] Windows installer — NSIS or WiX packages the compiled backend,
  React static build, emulators directory, and SQLite data path into a
  signed .exe installer. Registers Peach 1UP as a Windows service. UAC
  prompt on install only.
- [P8-4] P8 committed and pushed to main.

## P9 — Windows AppContainer Isolation

### Goal

Layer AppContainer isolation on top of the existing Job Object wrapper for security
containment (filesystem, network, inter-process). Regular AppContainer only — LPAC
rejected. Per-emulator rollout via container_enabled flag; emulators that fail testing
ship with Job Object only.

### DONE

- [P9-1] Empirical validation gate — SDL2+WASAPI+D3D11, Qt 5.15 QPA, SDL2+OpenGL 4.5
  test harnesses on Windows 10 22H2 and Windows 11 23H2. No production code until all pass.
- [P9-2] CPU rate control fix — replace HARD_CAP with MIN_MAX_RATE; add MinRate floor
  to prevent WASAPI audio thread starvation. Prerequisite for clean test matrix.
- [P9-3] AppContainer provisioning module — new app_container.py; provision, get_sid,
  grant_path. Moniker scheme: Peach1UP.<emulator_id>. No auto-deletion.
- [P9-4] DACL grant table — add container_dacl_grants per emulator in emulators.yaml.
  No hardcoded paths in Python.
- [P9-5] Integrate AppContainer into launch sequence — update job_objects.py. Abort on
  failure; no unsandboxed fallback.
- [P9-6] Per-emulator smoke test and test matrix — OS × GPU × audio × controller ×
  install path × locale. Set container_enabled per emulator on pass.
- [P9-7] Settings and UI — sandbox tier display on Emulators page; Reset sandbox state
  action in Advanced Settings.
- [P9-8] Update SECURITY.md and DECISIONS.md.
- [P9-9] P9 committed and pushed to main.

## Fixes

As a note, right after P9, I implemented a series of fixes which you can see in the commit history
marked as C/H/M/L or descending letters or marked with fix(). I did not add these to cnotext because they were found
during smoke testing and fixed in place. I also refactored some code marked as refactor().

## P-Smart Scan — Executable Detection and LLM-Assisted Config

### Goal

Improve one-click launch accuracy for DOS and console software through a
two-tier detection system: a bundled trained model using community datasets
for offline accuracy, and an optional LLM-assisted config path for users who
provide their own API key.

### NEXT

- [PSS-1] eXoDOS config extraction pipeline — parse DOSBox configs from
  eXoDOS dataset to extract executable paths, mount commands, and launch
  sequences per title. Output: structured dataset for model training.
- [PSS-2] TOSEC and Redump DAT parsing — build a hash index from TOSEC and
  Redump DAT files for disc image identity confirmation. Decide: bundled index
  vs first-run download. Output: title and platform from ISO hash.
- [PSS-3] Trained executable detection model — train a decision tree or
  random forest on eXoDOS-derived features (file names, depths, extensions,
  sizes, directory structure). Bundle compiled model with Peach 1UP. No
  internet required at runtime.
- [PSS-4] Hash-based title confirmation — integrate TOSEC/Redump hash lookup
  into the scan flow. Confirmed title feeds the trained model as a strong
  signal. Falls back to heuristic scan if no match.
- [PSS-5] API key settings field — add encrypted ai_api_key field to settings
  model. Never logged, never returned by API. UI field in Settings page.
- [PSS-6] LLM-assisted scan path — when API key is present, offer optional
  LLM scan that sends file listing, disc name, and era to the configured LLM
  and returns an ordered launch_commands list. Degrades gracefully on failure.
- [PSS-7] Improve heuristic scanner blocklist — add DEICE, PKUNZIP, LZMA,
  EXPAND, MSCDEX, SMARTDRV, README, UNWISE to deprioritisation list as
  stopgap until trained model ships.
- [PSS-8] Default emulator configs — review and expand bundled default
  configs per era to ensure out-of-box experience is solid regardless of
  detection tier.
- [PSS-9] PSS committed and pushed to main.

## PX-1 — Linux Namespace and cgroup Isolation (Scaffold)

### Goal

Replace the current Linux process isolation placeholder with a concrete implementation
based on namespaces and cgroups (either via nsjail or a native implementation).
Emulators remain host-native but run in a restricted view of the filesystem and with
per-launch CPU/memory caps.

### NEXT

- [PX-1-1] Select Linux isolation backend (nsjail vs native namespaces+cgroups)
- [PX-1-2] Define per-launch sandbox filesystem layout and allowed mounts
- [PX-1-3] Implement CPU and memory limits via cgroup v2
- [PX-1-4] Integrate Linux sandboxed launch into emulator backends
- [PX-1-5] Update SECURITY.md and DECISIONS.md and any other documentation for Linux isolation
- [PX-1-6] Linux packages — fpm produces .deb and AppImage. Registers systemd
  service on deb install. AppImage runs standalone.
- [PX-1-7] Include Linux in the native installation and distribution flow (depends on P8 Windows installer being stable)
- [PX-1-8] PX-1 committed and pushed to main.

## PX — Nice to Haves

- GitHub Actions release pipeline — on version tag: build Windows and
  Linux installers, sign with OSS certificate via ossign.org, attach to GitHub
  release automatically.
- Docusaurus documentation site — technical docs, user guide,
  contributor guide. Versioned, MDX, full-text search.
- Windows ME support via DOSBox-X
- Multiplayer / networking toggle per profile
- Controller remapping UI
- Plugin system for additional emulator backends
- Auto-update for emulator binaries
- Linux runtime packaging — ship a minimal Linux environment with all emulators pre-configured
- dgVoodoo2 injection for 3D-era Win9x games
- PS3 support via RPCS3
- Xbox 360 support via Xenia
- Platform image compression — working copies and save backups will accumulate
  and consume significant disk space over time. Add compression, deduplication,
  and storage management tooling to reduce bloat. Warn users at registration
  that duplicate images will be created and space usage will grow (package?)
- Save data backup and restore — extract save files from working images before
  reset, re-inject after. Reduces data loss risk when restoring from base.
- Platform snapshot management — compression, auto-snapshots before risky installs,
  snapshot history, and storage cleanup tooling. Basic create/restore ships in P2.
- Support a key,value (emulator, path) for users to add and configure their own emulators/eras in settings.yaml
- Add a Check All Health button to Platform page so user can check all platforms at once instead of one at a time
- Drag drop jsut adds image name not path so Users see a warning anyway. (drag drop may present security concerns)
- Add a note in the UI and docs: "if you change media paths, restart the backend to apply permissions."
- GitHub Action — weekly scheduled job that checks each emulator's
  release page for a version newer than the pinned version in its
  config/emulators/<slug>.toml. Opens a draft PR with the diff if a
  newer version is found. Runs offline (no emulator binaries, no downloads).
  One action per emulator slug, driven by release_url in the TOML.
- Launch history needs to be pruned or a delete flow of some sort
