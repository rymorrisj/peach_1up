# Peach 1UP

Retro game launcher for DOS through Windows XP era games. Point it at a disk
image, pick an era, and it spins up the correct emulator with the media
mounted and sensible defaults applied — no manual emulator configuration
required. Currently a keyboard-driven TUI; a GUI is planned for a later phase.

Covers DOS, Windows 3.1 (via DOSBox-X) and Windows 95, 98, XP (via 86Box).
Emulators run natively on the Windows host under Windows Job Objects for
process isolation and network blocking.

---

## Prerequisites

| Requirement                            | Notes                                                                                   |
| -------------------------------------- | --------------------------------------------------------------------------------------- |
| Windows 10/11 (Home edition supported) | WSL2 must be enabled                                                                    |
| Python 3.11                            | [python.org](https://www.python.org/downloads/)                                         |
| DOSBox-X                               | Required for DOS and Windows 3.1 — [dosbox-x.com](https://dosbox-x.com)                 |
| VirtualBox                             | Required for Windows 95, 98, XP — [virtualbox.org](https://www.virtualbox.org)          |
| 86Box                                  | Required for Win95/98 accuracy mode — [86box.net](https://86box.net)                    |
| 86Box ROM pack                         | Required for 86Box to function — [github.com/86Box/roms](https://github.com/86Box/roms) |

### ROM pack setup

Clone the ROM pack into a local directory:

```terminal
git clone https://github.com/86Box/roms C:\path\to\roms
```

Then set `ROM_PATH` in your `.env` file to that directory (see below).

If the ROM pack is absent, a warning will appear next to Windows 95/98/XP in
the era selector. The warning clears automatically once the pack is in place.

---

## Installation

1. Clone the repo

```terminal
git clone https://github.com/rymorrisj/peach_1up
cd peach_1up
```

2. Install dependencies

```terminal
pip install -r requirements.txt
```

3. Create your `.env` file

Copy the template and fill in paths for your machine:

```terminal
cp .env.template .env
```

Required variables:

```py
DOSBOX_PATH=C:\Program Files\DOSBox-X\dosbox-x.exe
BOX86_PATH=C:\Program Files\86Box\86Box.exe
VIRTUALBOX_PATH=C:\Program Files\Oracle\VirtualBox\VBoxManage.exe
ROM_PATH=C:\path\to\86box-roms
IMAGES_PATH=.\images\games
PROFILES_PATH=.\profiles
```

4. Run the launcher

```py
python launcher.py
```

The launcher requests administrator privileges on startup (required for
Windows Job Objects and Firewall rule management). A UAC prompt will appear
on first run.

---

## Documentation

- [CONTEXT.md](CONTEXT.md) — Development roadmap and current task
- [DECISIONS.md](DECISIONS.md) — Design decision log
- [CLAUDE.md](CLAUDE.md) — Project technical reference
