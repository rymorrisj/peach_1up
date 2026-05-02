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

### Goal

A user drops in a DOS game ISO, picks it from the launcher, and the game runs. No emulator interaction required. Win95/98/XP shows a clear "not yet supported for direct launch" message.

### DONE

### CURRENT

- [P1-1] Game profile system — save/load per-game YAML (era, media path, backend, dosbox conf path, hdd image path, executable path, notes)

### NEXT

- [P1-2] DOSBox-X config generation — generate .conf per game profile with correct cpu cycles, memory, sound defaults tuned per era
- [P1-3] Virtual hard drive management — auto-create and persist .img per game profile, reused on subsequent launches
- [P1-4] Game installation flow — detect installer ISOs, run install once, save executable path to profile
- [P1-5] Direct launch — boot straight to game executable, no DOS prompt shown to user
- [P1-6] Profile screen in TUI — create, edit, launch from saved profile
- [P1-7] Media auto-detection — sniff .iso/.img/.cue and suggest era (best effort)
- [P1-8] Auto-elevation — UAC manifest so launcher requests admin on startup, no manual run as admin required
- [P1-9] Missing emulator guidance — detect missing binaries, show official links in TUI
- [P1-10] Settings screen — paths, display config, ROM path, editable in TUI
- [P1-11] Refactor is_rom_pack_present() — replace empty string sentinel with explicit Optional[str] parameter signature
- [P1-12] P1 committed and pushed to main

## P2 — Meaningful Expansion

### Goal

Expand beyond DOS to console platforms. Win95/98/XP direct launch. Physical media support.

- [P2-1] Console backends — DuckStation (PS1), PCSX2 (PS2), Project64 (N64), mGBA (GB/GBC/GBA), Snes9x (SNES), BlastEm (Genesis)
- [P2-2] Era/platform selector expansion — add console platforms to era selector
- [P2-3] Win95/98/XP direct launch — pre-built base OS images, game installation into image, 86Box config generation
- [P2-4] 86Box hardware profiles — pre-configured per era (95, 98, XP)
- [P2-5] Physical drive support — CD-ROM and floppy hardware passthrough
- [P2-6] dgVoodoo2 injection — 3D-era games, injected into 86Box config
- [P2-7] Base OS image guidance — detect images folder, show setup links if empty
- [P2-8] Expanded file format support — .chd, .pbp per platform as scope expands
- [P2-9] P2 committed and pushed to main

## P3 — Maturity

- [P3-1] First-run setup wizard — detect missing binaries, guide through setup
- [P3-2] Game library scanner — scan a directory, auto-build profiles from found media
- [P3-3] Per-game config history — track changes to profiles over time
- [P3-4] Manual emulator binary override — user drops in custom build, tool detects it
- [P3-5] Network block verification — confirm Job Objects network restriction is enforced on every launch
- [P3-6] Container hardening revisit — evaluate isolation improvements based on beta feedback
- [P3-7] P3 committed and pushed to main

## PX — Nice to Haves (no timeline)

- Mouse support in TUI
- Full graphical UI replacing TUI
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
