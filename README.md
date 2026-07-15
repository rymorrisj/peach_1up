# Peach 1UP

Preservation automation tool for PC and console platforms. Point it at a disk
image, pick an era, and it launches the correct emulator with the media mounted
and sensible defaults applied — no manual emulator configuration required.

Covers PC platforms from DOS through Windows XP and first-generation consoles
(PS1, PS2, Xbox OG, Dreamcast, NES, SNES, N64).

---

## Prerequisites

### Emulators (installed on the host OS)

| Emulator    | Era              | Notes                                                                                     |
| ----------- | ---------------- | ----------------------------------------------------------------------------------------- |
| DOSBox-X    | DOS              | [dosbox-x.com](https://dosbox-x.com) — no ROM required                                    |
| 86Box       | Win95/98/XP      | [86box.net](https://86box.net) — requires ROM pack                                        |
| 86Box ROMs  | Win95/98/XP      | [github.com/86Box/roms](https://github.com/86Box/roms)                                    |
| DuckStation | PS1              | [duckstation.org](https://www.duckstation.org) — requires PS1 BIOS                        |
| PCSX2       | PS2              | [pcsx2.net](https://pcsx2.net) — requires PS2 BIOS                                        |
| xemu        | Xbox OG          | [xemu.app](https://xemu.app) — requires Xbox BIOS                                         |
| Flycast     | Dreamcast        | [github.com/flyinghead/flycast](https://github.com/flyinghead/flycast) — requires DC BIOS |
| Mesen       | NES, SNES        | [mesen.ca](https://www.mesen.ca)                                                          |
| Project64   | N64              | [pj64-emu.com](https://www.pj64-emu.com)                                                  |

Emulators marked "requires BIOS" need a BIOS image sourced from your own hardware. Peach 1UP does not provide BIOS files.

### Python

| Requirement         | Notes                                                                              |
| ------------------- | ---------------------------------------------------------------------------------- |
| Python 3.11 or later | [python.org](https://www.python.org/downloads/) — `build.bat` requires ≥ 3.11; CI runs on 3.14.6 |

---

## Development

```bash
# Backend
pip install -r backend/requirements-dev.txt
./start.sh    # Linux
start.bat     # Windows

# Frontend (separate terminal)
cd frontend && npm run dev
```

## Build

There is a build script at the root you can run which bundles all the build commands and tasks. You can also rebuild parts individually. Packaging is currently Windows-only (`build.bat`) — Linux packaging (.deb/AppImage) is planned but not yet built (see SCOPE.md PX-3).

```bash
build.bat     # Windows
```

### 1. Generate the tray icon

```bash
.venv\Scripts\python.exe scripts\gen_icon.py
```

Writes `assets/peach1up.png` (16×16 solid peach #ff8a5c).

### 2. Build the frontend

```bash
cd frontend && npm run build && cd ..
```

### 3. Package with PyInstaller

```bash
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\python.exe -m PyInstaller peach1up.spec
```

Output: `dist\peach1up\` — a self-contained directory containing `peach1up.exe`.

> `frontend/dist/` must exist before running PyInstaller.

### 4. Build the installer

Requires [NSIS](https://nsis.sourceforge.io/) and [WinSW](https://github.com/winsw/winsw/releases) (WinSW-x64.exe renamed to `Peach1UP.exe`) placed at `installer\tools\Peach1UP.exe`.

```bash
makensis installer\peach1up.nsi
```

Output: `Peach1UP-Setup.exe`. Installs to `%PROGRAMFILES%\Peach1UP\`, registers a
Windows service via WinSW, and creates a Start Menu shortcut. The uninstaller stops
the service and removes all files except `database\data\` (settings and library data)
and `.env`, which are preserved.

---

## Documentation

- [SCOPE.md](dev_docs/SCOPE.md) — Development roadmap and current task
- [DECISIONS.md](dev_docs/DECISIONS.md) — Design decision log
- [CLAUDE.md](dev_docs/CLAUDE.md) — Project technical reference
- [TECH.md](dev_docs/TECH.md) — Full technology stack with reasoning
- [EMULATORS.md](dev_docs/EMULATORS.md) — Emulator reference, portable mode, BIOS requirements, version coupling notes

---

## Configuration

Runtime settings (binary paths, operational flags, per-emulator overrides) are
stored in the `settings` table inside the SQLite database at
`database/data/peach1up.db` — there is no settings file to edit. Most are
configurable from the Settings page in the app. Secrets (PIN pepper,
TheGamesDB API key, etc.) live separately in a root `.env` file — see
`.env.template` for the supported keys.


