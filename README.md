# Peach 1UP

Preservation automation tool for PC and console platforms. Point it at a disk
image, pick an era, and it launches the correct emulator with the media mounted
and sensible defaults applied — no manual emulator configuration required.

Covers PC platforms from DOS through Windows XP and first-generation consoles
(PS1, PS2, Xbox OG, NES, N64).

---

## Prerequisites

### Emulators (installed on the host OS)

| Emulator    | Era                | Notes                                                                                     |
| ----------- | ------------------ | ----------------------------------------------------------------------------------------- |
| DOSBox-X    | DOS, Windows 3.1   | [dosbox-x.com](https://dosbox-x.com) — no ROM required                                    |
| 86Box       | Win95/98/XP        | [86box.net](https://86box.net) — requires ROM pack                                        |
| 86Box ROMs  | Win95/98/XP        | [github.com/86Box/roms](https://github.com/86Box/roms)                                    |
| ScummVM     | DOS/Win adventures | [scummvm.org](https://www.scummvm.org) — no ROM required, point at game data folder       |
| DuckStation | PS1                | [duckstation.org](https://www.duckstation.org) — requires PS1 BIOS                        |
| PCSX2       | PS2                | [pcsx2.net](https://pcsx2.net) — requires PS2 BIOS                                        |
| xemu        | Xbox OG            | [xemu.app](https://xemu.app) — requires Xbox BIOS                                         |
| Flycast     | Dreamcast          | [github.com/flyinghead/flycast](https://github.com/flyinghead/flycast) — requires DC BIOS |
| Mesen       | NES                | [mesen.ca](https://www.mesen.ca)                                                          |
| Project64   | N64                | [pj64-emu.com](https://www.pj64-emu.com)                                                  |

Emulators marked "requires BIOS" need a BIOS image sourced from your own hardware. Peach 1UP does not provide BIOS files.

### Python

| Requirement | Notes                                           |
| ----------- | ----------------------------------------------- |
| Python 3.11 | [python.org](https://www.python.org/downloads/) |

---

## Development

```bash
# Backend
pip install -r backend/requirements.txt
./start.sh    # Linux
start.bat     # Windows

# Frontend (separate terminal)
cd frontend && npm run dev
```

## Build

There is a build script at the root you can run which bundles all the build commands and tasks. You can also rebuild parts individually

```bash
./build.sh    # Linux
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

Requires [NSIS](https://nsis.sourceforge.io/) and [NSSM](https://nssm.cc/) placed at `installer\tools\nssm.exe`.

```bash
makensis installer\peach1up.nsi
```

Output: `Peach1UP-Setup.exe`. Installs to `%PROGRAMFILES%\Peach1UP\`, registers a
Windows service via NSSM, and creates a Start Menu shortcut. The uninstaller stops
the service and removes all files; `config\settings.yaml` is preserved.

---

## Configuration

Binary paths and runtime settings live in `config/settings.yaml`. A `.env`
file is supported as a legacy override — values in `.env` take precedence over
`settings.yaml`. See `settings.yaml` for documented defaults.

---

## Documentation

- [CONTEXT.md](CONTEXT.md) — Development roadmap and current task
- [DECISIONS.md](DECISIONS.md) — Design decision log
- [CLAUDE.md](CLAUDE.md) — Project technical reference
- [TECH.md](TECH.md) — Full technology stack with reasoning
- [EMULATORS.md](docs/EMULATORS.md) — Emulator reference, portable mode, BIOS requirements, version coupling notes
