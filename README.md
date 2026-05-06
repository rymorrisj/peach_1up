# Peach 1UP

Preservation automation tool for PC and console platforms. Point it at a disk
image, pick an era, and it launches the correct emulator with the media mounted
and sensible defaults applied — no manual emulator configuration required.

Covers PC platforms from DOS through Windows XP and first-generation consoles
(PS1, PS2, Xbox OG, NES, N64).

---

## Prerequisites

### Primary install (Docker Compose)

| Requirement         | Notes                                                                                      |
| ------------------- | ------------------------------------------------------------------------------------------ |
| Docker Engine       | Linux: [docs.docker.com](https://docs.docker.com/engine/install/). Windows: via WSL2.     |
| WSL2 (Windows only) | Enable via `wsl --install` in an elevated PowerShell prompt.                               |
| Docker Compose      | Included with Docker Engine.                                                               |

### Emulators (installed on the host OS)

| Emulator   | Era               | Notes                                                                              |
| ---------- | ----------------- | ---------------------------------------------------------------------------------- |
| DOSBox-X   | DOS, Windows 3.1  | [dosbox-x.com](https://dosbox-x.com) — no ROM required                            |
| VirtualBox | Windows 95/98/XP  | [virtualbox.org](https://www.virtualbox.org)                                       |
| 86Box      | Win95/98 accuracy | [86box.net](https://86box.net) — opt-in accuracy mode, requires ROM pack           |
| 86Box ROMs | Win95/98 accuracy | [github.com/86Box/roms](https://github.com/86Box/roms)                             |
| DuckStation | PS1              | [duckstation.org](https://www.duckstation.org) — requires PS1 BIOS                |
| PCSX2      | PS2               | [pcsx2.net](https://pcsx2.net) — requires PS2 BIOS                                |
| xemu       | Xbox OG           | [xemu.app](https://xemu.app) — requires Xbox BIOS                                 |
| Mesen      | NES               | [mesen.ca](https://www.mesen.ca)                                                   |
| Project64  | N64               | [pj64-emu.com](https://www.pj64-emu.com)                                          |

Emulators marked "requires BIOS" need a BIOS image sourced from your own
hardware. Peach 1UP does not provide BIOS files.

### Python fallback (no Docker)

| Requirement | Notes                                                  |
| ----------- | ------------------------------------------------------ |
| Python 3.11 | [python.org](https://www.python.org/downloads/)        |

---

## Installation

### Option 1 — Docker Compose (recommended)

```terminal
git clone https://github.com/rymorrisj/peach_1up
cd peach_1up
docker compose up
```

Open `http://localhost:3000` in your browser. On first run, the setup wizard
will detect installed emulators and guide you through initial configuration.
Binary paths are auto-detected or set via `config/settings.yaml`.

**Windows:** requires Docker Engine running under WSL2. Run
`wsl --install` in an elevated PowerShell prompt if WSL2 is not yet enabled.

### Option 2 — start.bat (Windows fallback)

For Windows users who cannot run Docker:

```terminal
git clone https://github.com/rymorrisj/peach_1up
cd peach_1up
start.bat
```

`start.bat` installs dependencies, starts the FastAPI backend, and opens the
frontend in your default browser.

### Option 3 — Python direct

```terminal
git clone https://github.com/rymorrisj/peach_1up
cd peach_1up
pip install -r requirements.txt
python launcher.py
```

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
