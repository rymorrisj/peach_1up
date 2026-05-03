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

### Goal

The project is clean, documented, and understandable before complexity increases in P2. A new user can drop in a DOS ISO, run the launcher, create a profile, install once, and return to the game on subsequent launches without touching a config file or command line outside of DOSBox. The README covers prerequisites, installation, and project objectives.

### CURRENT

- [P1.5-1] Documentation pass — module docstrings, inline comments for complex/esoteric code, Google-style docstrings for classes and non-trivial functions. Priority files: vhd.py, job_objects.py, dosbox_config.py, profile.py, backend_router.py. Functional code should remain self-documenting via clear naming. Flag any misleading or incorrect names without changing them.
- [P1.5-2] README update — project objective, prerequisites (Python 3.11, DOSBox-X, 86Box, ROM pack), installation steps, how to run
- [P1.5-3] Dead code sweep — remove any remaining stale comments, unused imports, or leftover scaffolding from P0/P1 bug fixes
- [P1.5-4] Launcher wizard flow audit — walk the full create → install → launch path and confirm there are no confusing prompts, dead ends, or missing feedback messages
- [P1.5-5] P1.5 committed and pushed to main

### NEXT

## P2 — Win95/98/XP Direct Launch

### Goal

A user can launch a Win95, Win98, or XP game from a pre-built base OS image via 86Box with correct hardware profile and config generation. The PC era is fully covered end to end.

### NEXT

- [P2-1] 86Box config generation — generate per-game hardware config per era (95, 98, XP)
- [P2-2] 86Box hardware profiles — pre-configured machine, CPU, RAM, sound, video per era
- [P2-3] Win95/98/XP launch flow — base OS image selection, game installation into image, direct launch via 86Box
- [P2-4] Base OS image guidance — detect images folder, show setup instructions and links if empty
- [P2-5] Physical drive support — CD-ROM and floppy hardware passthrough
- [P2-6] dgVoodoo2 injection — 3D-era games, injected into 86Box config
- [P2-7] Expanded file format support — .chd, .pbp per platform as scope expands
- [P2-8] P2 committed and pushed to main

## P3 — Maturity

- [P3-1] First-run setup wizard — detect missing binaries, guide through setup
- [P3-2] Game library scanner — scan a directory, auto-build profiles from found media
- [P3-3] Per-game config history — track changes to profiles over time
- [P3-4] Manual emulator binary override — user drops in custom build, tool detects it
- [P3-5] Network block verification — confirm Job Objects network restriction is enforced on every launch
- [P3-6] Container hardening revisit — evaluate isolation improvements based on beta feedback
- [P3-7] P3 committed and pushed to main

## P4 — Console Backends

### Goal

Expand beyond PC to console platforms using the same profile and launch architecture.

- [P4-1] Console backends — DuckStation (PS1), PCSX2 (PS2), Project64 (N64), mGBA (GB/GBC/GBA), Snes9x (SNES), BlastEm (Genesis)
- [P4-2] Era/platform selector expansion — add console platforms to era selector
- [P4-3] Expanded file format support — .chd, .pbp, .pkg, .xiso, .god, .xex per platform
- [P4-4] P4 committed and pushed to main

## PX — Nice to Haves (no timeline)

- Mouse support in TUI
- Full graphical GUI replacing TUI — drag and drop media and profiles
- Host-side .exe scanner — scan mounted HDD image for executables, present as file browser for auto-launch
- Multiplayer / networking toggle per profile
- Cloud sync for game profiles
- Controller remapping UI
- Plugin system for additional emulator backends
- Auto-update for emulator binaries
- Bundle DOSBox-X and 86Box binaries — eliminates manual install and env var setup
- Expanded file format support — .chd, .pbp, .pkg, .xiso, .god, .xex per platform
- PS3 support via RPCS3
- Xbox support via xemu
- Xbox 360 support via Xenia
