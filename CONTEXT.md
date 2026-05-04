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

### Goal

A user can register a Windows OS platform and launch software from it via the correct
emulator backend. Two media paths are supported: pre-installed HDD images (primary,
zero install friction) and original installer media (supported, user completes install
manually inside the emulator). The user never selects or configures an emulator directly.

### Emulator Strategy

| Era     | OS            | Primary    | Fallback                             | Logic                                          |
| ------- | ------------- | ---------- | ------------------------------------ | ---------------------------------------------- |
| DOS     | MS-DOS        | DOSBox-X   | —                                    | Always DOSBox-X                                |
| Win 3.x | Windows 3.1   | DOSBox-X   | —                                    | Runs inside DOS session                        |
| Win 9x  | Windows 95/98 | VirtualBox | DOSBox-X (compat) / 86Box (accuracy) | VirtualBox default. See selection logic below. |
| Win XP  | Windows XP    | VirtualBox | —                                    | Always VirtualBox                              |

**Win 9x selection logic:**

- Default → VirtualBox (hardware virtualization, near-native performance)
- DOS app running under Windows → DOSBox-X (better DOS compatibility)
- User enables accuracy mode OR title is in known titles database → 86Box

**Accuracy mode:**
A user-facing "Hardware accuracy mode" checkbox on profile creation. Never exposes
emulator names. Clear tradeoff language: "Slower but required for some games with
specific hardware needs." When checked, Win9x routes to 86Box.

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

### CURRENT

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

### NEXT

- [P3-1] First-run setup wizard — detect missing binaries and platforms, guide through setup
- [P3-2] Game library scanner — scan a directory, auto-build profiles from found media
- [P3-3] Per-game config history — track changes to profiles over time
- [P3-4] Manual emulator binary override — user drops in custom build, tool detects it
- [P3-5] Network block verification — confirm Job Objects network restriction is enforced on every launch
- [P3-6] Known titles database — community YAML of titles with hardware requirements, used by accuracy detection
- [P3-7] Platform health checks — detect degraded or broken OS images, prompt for recovery
- [P3-8] P3 committed and pushed to main

## P4 — Console Backends

### Goal

Expand beyond PC to first-generation console platforms using the same profile and launch architecture.

### NEXT

- [P4-1] Console backends — DuckStation (PS1), Project64 (N64), Mesen (NES), xemu (Xbox OG)
- [P4-2] Era/platform selector expansion — add console platforms to era selector
- [P4-3] Cartridge imaging guide — in-app guide for users to dump cartridge media per platform (NES, N64, Game Boy etc.) with recommended hardware
- [P4-4] Expanded file format support — .chd, .xiso per platform
- [P4-5] P4 committed and pushed to main

## PX — Nice to Haves (no timeline)

- [!IMPORTANT] Installation wizard — guided flow for original installer media. Detects
  autorun.inf, scans ISO for common installer executables (SETUP.EXE, INSTALL.EXE,
  INSTALL.BAT), runs installer inside emulator, scans HDD image post-install for new
  executables, prompts user to confirm launch target. Primary QoL gap — pull forward
  before other PX items when capacity allows.
- Full graphical GUI replacing TUI — drag and drop media and profiles
- Host-side .exe scanner — scan mounted HDD image for executables, present as file browser for auto-launch
- Windows ME support via DOSBox-X
- PS2 support via PCSX2
- Multiplayer / networking toggle per profile
- Cloud sync for game profiles
- Controller remapping UI
- Plugin system for additional emulator backends
- Auto-update for emulator binaries
- Bundle emulator binaries — eliminates manual install and env var setup
- Linux runtime packaging — ship a minimal Linux environment with all emulators pre-configured
- dgVoodoo2 injection for 3D-era Win9x games
- PS3 support via RPCS3
- Xbox 360 support via Xenia
- Guide Users on how to image their media for the app
- Platform image compression — working copies and save backups will accumulate
  and consume significant disk space over time. Add compression, deduplication,
  and storage management tooling to reduce bloat. Warn users at registration
  that duplicate images will be created and space usage will grow.
- Save data backup and restore — extract save files from working images before
  reset, re-inject after. Reduces data loss risk when restoring from base.
- Platform snapshot management — compression, auto-snapshots before risky installs,
  snapshot history, and storage cleanup tooling. Basic create/restore ships in P2.
