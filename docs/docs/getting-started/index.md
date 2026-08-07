---
slug: /getting-started
---

# Getting Started

Peach 1UP is a preservation automation tool. Point it at a disk image, pick an era, and it
launches the correct emulator with the media mounted and sensible defaults applied, no manual
emulator configuration required. It covers PC platforms from DOS through Windows XP and
first-generation consoles (PS1, PS2, Xbox OG, Dreamcast, NES, SNES, N64).

This page gets you from a fresh checkout to a running app. For deployment behind a domain see
[Self-Hosting](./self-hosting.mdx); for cover art and metadata see
[Metadata Enrichment](./metadata-enrichment.mdx).

:::note Platform support
The Alpha is built and tested on **Windows 10/11**. Peach 1UP is Windows-only, the hardened
sandbox relies on Windows Job Objects, and there are no plans to support other platforms.
:::

## Prerequisites

| Requirement | Why | Where |
| ----------- | --- | ----- |
| **Python 3.11 or later** | Backend runtime | [python.org](https://www.python.org/downloads/), on Windows, check "Add Python to PATH" |
| **Node.js 18+** | Frontend build & dev server | [nodejs.org](https://nodejs.org/) |
| **Emulators** | Run on the host OS; Peach 1UP launches them | See the table below |
| **BIOS / ROMs** | Required by some emulators; sourced from your own hardware | Peach 1UP never provides these |

### Emulators

Install the emulators for the eras you care about, you don't need all of them.

| Emulator | Era | Notes |
| -------- | --- | ----- |
| DOSBox-X | DOS | No ROM required |
| 86Box (+ ROM pack) | Windows 95 / 98 / XP | Requires the [86Box ROM pack](https://github.com/86Box/roms) |
| DuckStation | PS1 | Requires PS1 BIOS |
| PCSX2 | PS2 | Requires PS2 BIOS |
| xemu | Xbox OG | Requires Xbox BIOS |
| Flycast | Dreamcast | Requires DC BIOS |
| Mesen | NES / SNES |, |
| Project64 | N64 |, |

DOSBox-X and 86Box can run in **portable mode** bundled under `emulators/`; the console emulators
are detected at known install locations. See the
[Emulator Reference](../contributor-guide/emulators.mdx) for portable-mode setup and BIOS placement.

## Run it (development)

Clone the repository, then run the setup script for your OS from the project root. It creates a
Python virtual environment, installs backend and frontend dependencies, generates the typed API
client, and starts every service.

```bash
start.bat
```

When it finishes you'll have:

| Service | URL | Notes |
| ------- | --- | ----- |
| Frontend | http://localhost:5173 | The app UI, open this |
| Backend API | http://localhost:8000 | FastAPI; interactive docs at `/api/docs` |
| Docs site | http://localhost:3000 | This documentation |

The backend binds to `127.0.0.1` only, it is not reachable from other machines unless you
explicitly enable network access (see [Self-Hosting](./self-hosting.mdx)).

### First run

1. Open **http://localhost:5173**.
2. You'll be guided through **first-run setup**: create the **owner account** with a name and a
   4–6 digit PIN. The owner has full control and is the only account that can manage users and
   settings.
3. From there you can add sub-accounts (each with its own PIN and permissions) on the **Users**
   page.

If you ever lock yourself out, reset the owner account with `reset_owner.bat` (packaged build) or
`python scripts/setup_admin_user.py` (from source).

### Add your first game

1. Go to **Library → Add Media** and point it at a disk image (`.iso`, `.cue/.bin`, `.chd`, a game
   folder, or a `.zip`).
2. Peach 1UP scans the media, detects the platform and era, and assigns a launch profile.
3. Press **Launch**. The correct emulator starts with the media mounted read-only.

Multi-disc games (e.g. a 4-CD title) are added as a **Library Set**, one entry that groups the
discs and tracks which disc to boot from. Single-disc games are ordinary **Library Items**.

:::tip
All mounted media is **read-only**. DOS games that need to save configuration or run an installer
use a writable HDD image created through the install flow, see the
[Era Guide](../user-guide/era-guide.mdx).
:::

## Build from source

To produce a standalone Windows executable:

```bash
build.bat
```

This builds the frontend, generates the API types and OpenAPI docs, compiles the Windows sandbox
host (requires [MSYS2 UCRT64](https://www.msys2.org/) with `g++` for a rebuild; a prebuilt binary
is used otherwise), and runs PyInstaller. The output is a self-contained directory at
`dist/peach1up/` containing `peach1up.exe`.

Building the NSIS installer additionally requires [NSIS](https://nsis.sourceforge.io/) and
[WinSW](https://github.com/winsw/winsw/releases), see the project `README.md` for the installer
steps.

## Configuration

Runtime settings and binary paths are stored in the `settings` table inside the SQLite
database (`database/data/peach1up.db`), not in a config file, most are configurable from the
Settings page in the app. A root `.env` file (see `.env.template`) holds secrets (PIN pepper,
TheGamesDB API key, etc.) and is never committed.

## Where to next

- **[User Guide](../user-guide/index.md)**, eras, BIOS sourcing, controllers, media formats, and
  multi-disc games.
- **[Contributor Guide](../contributor-guide/index.md)**, architecture, the technology stack,
  security model, and Windows sandboxing.
- **[Self-Hosting](./self-hosting.mdx)**, running behind your own domain or reverse proxy.
