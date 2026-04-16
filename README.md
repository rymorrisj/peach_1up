# Peach 1UP

Retro game launcher and VM manager for DOS through Windows XP era games.

## Quick Start

TODO: Setup and usage instructions will be added as features are implemented.

## Requirements

- Python 3.11+
- Docker Desktop (with WSL2 on Windows Home)
- VcXsrv X Server

### ROM Pack Setup (Windows 95, 98, XP)

Games from the Windows 95, 98, and XP era require the 86Box emulator and a ROM pack to function. These are copyrighted but required for 86Box to work.

**Option 1 — Automatic (recommended)**
Open Peach 1UP, go to Settings, and select "Download ROM pack". The launcher will clone the official ROM pack from https://github.com/86Box/roms into your configured ROM_PATH automatically.

**Option 2 — Manual**
Clone or download the ROM pack yourself from https://github.com/86Box/roms and place the files in the path set by ROM_PATH in your .env file.

If the ROM pack is not detected, a warning will appear next to Windows 95, 98, and XP in the era selector. The warning disappears automatically once the pack is in place.

## Documentation

- [CLAUDE.md](CLAUDE.md) - Project overview and technical details
- [CONTEXT.md](CONTEXT.md) - Current development roadmap
- [DECISIONS.md](DECISIONS.md) - Design decision log
