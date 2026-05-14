# Peach 1UP

Preservation automation tool for PC and console platforms. Point it at a disk
image, pick an era, and it launches the correct emulator with the media mounted
and sensible defaults applied — no manual emulator configuration required.

Covers PC platforms from DOS through Windows XP and first-generation consoles
(PS1, PS2, Xbox OG, NES, N64).

---

## Prerequisites

### Emulators (installed on the host OS)

| Emulator    | Era               | Notes                                                                    |
| ----------- | ----------------- | ------------------------------------------------------------------------ |
| DOSBox-X    | DOS, Windows 3.1  | [dosbox-x.com](https://dosbox-x.com) — no ROM required                   |
| VirtualBox  | Windows 95/98/XP  | [virtualbox.org](https://www.virtualbox.org)                             |
| 86Box       | Win95/98 accuracy | [86box.net](https://86box.net) — opt-in accuracy mode, requires ROM pack |
| 86Box ROMs  | Win95/98 accuracy | [github.com/86Box/roms](https://github.com/86Box/roms)                   |
| DuckStation | PS1               | [duckstation.org](https://www.duckstation.org) — requires PS1 BIOS       |
| PCSX2       | PS2               | [pcsx2.net](https://pcsx2.net) — requires PS2 BIOS                       |
| xemu        | Xbox OG           | [xemu.app](https://xemu.app) — requires Xbox BIOS                        |
| Mesen       | NES               | [mesen.ca](https://www.mesen.ca)                                         |
| Project64   | N64               | [pj64-emu.com](https://www.pj64-emu.com)                                 |

Emulators marked "requires BIOS" need a BIOS image sourced from your own
hardware. Peach 1UP does not provide BIOS files.

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

## Production (coming in P5)

- **Windows:** download and run `Peach1UP-Setup-Windows-x64.exe`
- **Linux:** download `peach1up-linux-x64.deb` or `.AppImage`

---

## Configuration

Binary paths and runtime settings live in `config/settings.yaml`. A `.env`
file is supported as a legacy override — values in `.env` take precedence over
`settings.yaml`. See `settings.yaml` for documented defaults.

There aer several default paths that you can update such as \images for the .iso, .cud, etc. files.
If you update this path you MUST restart the backend service. During runtime startup, a script is ran
in order to grant correct permissions to all folder and files that need them.

---

## Documentation

- [CONTEXT.md](CONTEXT.md) — Development roadmap and current task
- [DECISIONS.md](DECISIONS.md) — Design decision log
- [CLAUDE.md](CLAUDE.md) — Project technical reference
- [TECH.md](TECH.md) — Full technology stack with reasoning
