# Peach 1UP — Session Context

## P0 — Bare Minimum Working Launcher

### DONE

- [P0-1] Project scaffold — folders, empty files, .env template, .gitignore

### CURRENT

- [P0-2] Docker setup — Dockerfile for DOSBox-X, verify container builds and runs

### NEXT

- [P0-3] VcXsrv detection — check DISPLAY on launch, fail clearly if not found
- [P0-4] DOSBox-X backend — mount .iso/.img/.cue read-only, launch in container
- [P0-5] TUI skeleton — Textual app, keyboard navigation, main menu
- [P0-6] Era selector screen — DOS / Win 3.1 / Win 95 / Win 98 / Win XP
- [P0-7] Media picker screen — browse filesystem for .iso / .img / .cue files
- [P0-8] Launch flow — era + media → correct backend → container up → emulator running
- [P0-9] Error handling layer — all failures surface to TUI with message, no silent crashes
- [P0-10] Dockerfile for 86Box — verify container builds, ROM path validation
- [P0-11] 86Box backend — mount media read-only, fail if ROMs missing with link
- [P0-12] P0 committed and pushed to main

## P1 — Core Usability

- [P1-1] Game profile system — save/load per-game YAML (era, media path, backend, notes)
- [P1-2] Profile screen in TUI — create, edit, launch from saved profile
- [P1-3] Media auto-detection — sniff .iso/.img/.cue and suggest era (best effort)
- [P1-4] Network disable verification — confirm Docker --network none is enforced
- [P1-5] Missing emulator guidance — detect missing binaries, show official links in TUI
- [P1-6] WSL2 detection — check on startup, surface clear error if not enabled
- [P1-7] Settings screen — paths, display config, ROM path, editable in TUI
- [P1-8] P1 committed and pushed to main

## P2 — Meaningful Expansion

- [P2-1] Physical drive support — CD-ROM and floppy hardware passthrough to container
- [P2-2] QEMU backend — full Windows XP VM option
- [P2-3] dgVoodoo2 injection — 3D-era games, injected into 86Box config
- [P2-4] 86Box hardware profiles — pre-configured per era (95, 98, XP)
- [P2-5] Base OS image guidance — detect images folder, show setup links if empty
- [P2-6] P2 committed and pushed to main

## P3 — Maturity

- [P3-1] First-run setup wizard — step through Docker, VcXsrv, ROMs, images
- [P3-2] VcXsrv automated install — winget or bundled installer, silent option
- [P3-3] Game library scanner — scan a directory, auto-build profiles from found media
- [P3-4] Per-game config history — track changes to profiles over time
- [P3-5] Manual emulator binary override — user drops in custom build, tool detects it
- [P3-6] P3 committed and pushed to main

## PX — Nice to Haves (no timeline)

- Mouse support in TUI
- Full graphical UI replacing TUI
- Multiplayer / networking toggle per profile
- Cloud sync for game profiles
- Controller remapping UI
- Plugin system for additional emulator backends
- Auto-update for Docker images
