# Peach 1UP — Session Context

## P0 — Bare Minimum Working Launcher

### DONE

- [P0-1] Project scaffold — folders, empty files, .env template, .gitignore
- [P0-2] Windows Job Objects wrapper — isolate emulator process, enforce resource limits, restrict filesystem access, block network
- [P0-3] DOSBox-X backend — locate binary via DOSBOX_PATH, mount media read-only, launch under Job Objects
- [P0-4] TUI skeleton — Textual app, keyboard navigation, main menu
- [P0-5] Era selector screen — DOS / Win 3.1 / Win 95 / Win 98 / Win XP
- [P0-6] Game picker screen — browse filesystem for .iso / .img / .cue files

### CURRENT

- [P0-7] Launch flow — era + media → correct backend → Job Objects → emulator running

### NEXT

- [P0-8] Error handling layer — all failures surface to TUI with message, no silent crashes
- [P0-9] 86Box backend — locate binary via BOX86_PATH, validate ROM path, launch under Job Objects
- [P0-10] P0 committed and pushed to main

## P1 — Core Usability

- [P1-1] Game profile system — save/load per-game YAML (era, media path, backend, notes)
- [P1-2] Profile screen in TUI — create, edit, launch from saved profile
- [P1-3] Media auto-detection — sniff .iso/.img/.cue and suggest era (best effort)
- [P1-4] Network block verification — confirm Job Objects network restriction is enforced on every launch
- [P1-5] Missing emulator guidance — detect missing binaries, show official links in TUI
- [P1-6] Settings screen — paths, display config, ROM path, editable in TUI
- [P1-7] P1 committed and pushed to main
- [P1-8] Refactor is_rom_pack_present() — replace empty string sentinel with explicit Optional[str] parameter signature

## P2 — Meaningful Expansion

- [P2-1] Physical drive support — CD-ROM and floppy hardware passthrough to container
- [P2-2] QEMU backend — full Windows XP VM option
- [P2-3] dgVoodoo2 injection — 3D-era games, injected into 86Box config
- [P2-4] 86Box hardware profiles — pre-configured per era (95, 98, XP)
- [P2-5] Base OS image guidance — detect images folder, show setup links if empty
- [P2-6] P2 committed and pushed to main
- [P2-7] Container hardening revisit — evaluate isolation improvements based on beta feedback

## P3 — Maturity

- [P3-1] First-run setup wizard — step through Docker, VcXsrv, ROMs, images
- [P3-2] Game library scanner — scan a directory, auto-build profiles from found media
- [P3-3] Per-game config history — track changes to profiles over time
- [P3-4] Manual emulator binary override — user drops in custom build, tool detects it
- [P3-5] P3 committed and pushed to main

## PX — Nice to Haves (no timeline)

- Mouse support in TUI
- Full graphical UI replacing TUI
- Multiplayer / networking toggle per profile
- Cloud sync for game profiles
- Controller remapping UI
- Plugin system for additional emulator backends
- Auto-update for Docker images
