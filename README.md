# Peach 1UP

[![platform](https://img.shields.io/badge/platform-Windows%2010%20%2F%2011-blue.svg)](https://microsoft.com/windows)
[![python](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://www.python.org/downloads/)
[![license](https://img.shields.io/badge/license-GPL--2.0--or--later-blue.svg)](LICENSE)

Preservation automation for old PC and console software. Point it at a disk image, pick an
era, and the right emulator launches with the media mounted and sensible defaults applied.
No manual emulator configuration.

Covers DOS through Windows XP, plus PS1, PS2, PS3, Xbox OG, Xbox 360, Dreamcast, NES, SNES,
and N64.

> Pre-alpha. `VERSION` reads `0.1.0` and no tagged release has been cut. See
> [CHANGELOG.md](CHANGELOG.md).

## Highlights

- **One-click launch.** Detection resolves the platform and era from the media itself, then
  assigns an emulator and a launch profile. You press Launch.
- **Ten emulators, one interface.** Installed on demand from Peach 1UP's own bundle repo,
  configured per launch.
- **Real process isolation.** Every launch runs inside a Windows Job Object with kill-on-close
  and per-era CPU and memory caps, with AppContainer layered on top where the emulator
  supports it. If isolation cannot be applied, the launch aborts. There is no unsandboxed
  fallback.
- **Network off by default.** Blocking is emulator-native, not a host firewall rule, so it
  needs no elevation and cannot be bypassed by a COM failure.
- **Household accounts.** One owner plus PIN-protected sub-accounts, per-account permission
  flags, and content-rating filtering that fails closed.
- **Media integrity, not just lookup.** Disc images are SHA-1 checked against community
  Redump and No-Intro data at ingest, with a five-state verification result per disc.
- **Metadata on demand.** TheGamesDB or IGDB, triggered by an explicit user action. No
  scan-time auto-fetch, no background jobs, never blocks a launch.
- **Local first.** Binds `127.0.0.1`, stores everything in one SQLite file, and never
  phones home.

## Requirements

| | |
|---|---|
| OS | Windows 10 or 11. Windows-only, permanently |
| [Python 3.14+](https://www.python.org/downloads/) | Pinned via `requires-python` in `pyproject.toml`, matches CI |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | Manages the virtualenv and dependencies |
| [Node.js 22+](https://nodejs.org/) | Frontend build and dev server |
| Emulators | Installed from the app, on demand. You only need the ones for eras you care about |
| BIOS and ROMs | You supply them, from your own hardware. Peach 1UP never provides, links to, or assists with acquiring them |

## Quick start

```bash
uv sync --group dev
start.bat
```

`start.bat` builds the frontend if `frontend/dist` is missing, starts the backend, and opens
a browser. For frontend development, run the Vite dev server in a second terminal:

```bash
cd frontend && npm run dev
```

| Service | URL |
|---|---|
| App | http://localhost:8000 |
| Frontend dev server | http://localhost:5173 |
| API docs | http://localhost:8000/api/docs |
| Documentation site | http://localhost:8000/docs |

### First run

1. Open the app. You are redirected to first-run setup.
2. Create the **owner account**: a name and a 4 to 6 digit PIN. The owner has full control
   and is the only account that can create or delete sub-accounts.
3. Install the emulators you want and place any BIOS files they require.
4. Add media, then press Launch.

Locked out of the owner account? Run `reset_owner.bat` (packaged build) or
`python scripts/setup_admin_user.py` (from source).

## Emulators

| Emulator | Era | Data location | Requires |
|---|---|---|---|
| [DOSBox-X](https://dosbox-x.com) | DOS | Portable via config | Nothing |
| [86Box](https://86box.net) | Win95, Win98, WinXP | Portable via layout | [ROM pack](https://github.com/86Box/roms) |
| [DuckStation](https://www.duckstation.org) | PS1 | Portable via sentinel | PS1 BIOS |
| [PCSX2](https://pcsx2.net) | PS2 | Portable via sentinel | PS2 BIOS |
| [RPCS3](https://rpcs3.net/download) | PS3 | Portable by default | PS3 firmware |
| [xemu](https://xemu.app) | Xbox OG | Portable via sentinel, partial | Xbox BIOS, HDD image |
| [Xenia](https://xenia.jp) | Xbox 360 | Portable via sentinel | Nothing |
| [Mesen](https://www.mesen.ca) | NES, SNES | Portable via first-run choice | Nothing |
| [Project64](https://www.pj64-emu.com) | N64 | Portable by default | Nothing |
| [Flycast](https://github.com/flyinghead/flycast) | Dreamcast | Portable via sentinel | DC BIOS |

BIOS images must be sourced from your own hardware.

**Data location** is where each emulator keeps saves, configs, and caches:

| Mode | Meaning |
|---|---|
| Portable by default | Writes into `emulators/<slug>/` with no setup. RPCS3 treats its executable directory as the data root on Windows; Project64 stores config in `<install dir>\Config\` whenever that directory is writable |
| Portable via sentinel | Portable once a sentinel file sits next to the binary: `portable.txt` for DuckStation, PCSX2, and Xenia; `emu.cfg` for Flycast; `xemu.toml` for xemu. Driven by the descriptor's `portable_sentinel` field |
| Portable via layout or config | 86Box detects portable mode from `roms/` and `assets/` next to the binary; DOSBox-X resolves data paths relative to the config file passed with `-conf` |
| Portable via first-run choice | Mesen asks on first run where to store data. It is portable only if you pick the application directory |

Without a sentinel, these fall back to `%APPDATA%\<Emulator>\`, or `Documents\Xenia\` for
Xenia.

Two caveats worth knowing:

- **xemu is only partially portable.** Its `-config_path` flag does not redirect the shader
  cache or log files, which always write to the default user profile location
  ([xemu #2480](https://github.com/mborgerson/xemu/issues/2480)).
- **Mesen's portability depends on an interactive choice** Peach 1UP cannot make for you, so
  it cannot be assumed. Follow the startup guide on your first launch.

Full detail, including BIOS filenames, version coupling, and per-emulator limitations:
[dev_docs/EMULATORS.md](dev_docs/EMULATORS.md).

## Process isolation

Every emulator launches inside a Windows Job Object with kill-on-close and per-era CPU and
memory caps. Where the emulator supports it, an AppContainer is layered on top, identified by
a moniker of the form `Peach1UP.<slug>.<scope>` (for example `Peach1UP.duckstation.shared`).

- `<slug>` matches the emulator catalog's `slug` field. Check the TOML descriptor under
  `config/emulators/` if you are unsure.
- `<scope>` is `shared`, or the decimal user item ID for a per-item container.

Sandboxing itself is handled by [wincage](https://github.com/rymorrisj/wincage), a standalone
Windows AppContainer and Job Object package extracted from this project. See
[dev_docs/windows-sandbox.md](dev_docs/windows-sandbox.md) for the caps and how to tune them.

## Configuration

Runtime settings (binary paths, operational flags, per-emulator overrides) live in the
`settings` table inside `database/data/peach1up.db`. There is no settings file to edit, and
most values are configurable from the Settings page.

Secrets (PIN pepper, TheGamesDB and IGDB credentials) live in a root `.env` file. See
`.env.template` for the supported keys.

## Build

```bash
build.bat
```

That bundles every step. To run them individually:

**1. Tray icon**

```bash
.venv\Scripts\python.exe scripts\gen_icon.py
```

Writes `assets/peach1up.png`.

**2. Frontend**

```bash
cd frontend && npm run build && cd ..
```

**3. PyInstaller**

```bash
uv sync --group build
.venv\Scripts\python.exe -m PyInstaller peach1up.spec
```

Output: `dist\peach1up\`, a self-contained directory containing `peach1up.exe`.
`frontend/dist/` must exist first.

**4. Installer**

Requires [NSIS](https://nsis.sourceforge.io/) and
[WinSW](https://github.com/winsw/winsw/releases) (`WinSW-x64.exe` renamed to `Peach1UP.exe`)
at `installer\tools\Peach1UP.exe`.

```bash
makensis installer\peach1up.nsi
```

Output: `Peach1UP-Setup.exe`. Installs to `%PROGRAMFILES%\Peach1UP\`, registers a Windows
service via WinSW, and creates a Start Menu shortcut. The uninstaller stops the service and
removes everything except `database\data\` and `.env`, which are preserved.

## Documentation

[CHANGELOG.md](CHANGELOG.md) is the project's single historical record: what shipped, when,
and which decisions shaped it.

Contributor references live in [`dev_docs/`](dev_docs/):

| Document | Covers |
|---|---|
| [TECH.md](dev_docs/TECH.md) | The stack and why each part was chosen |
| [EMULATORS.md](dev_docs/EMULATORS.md) | Per-emulator reference: portable mode, BIOS, version coupling, limitations |
| [BACKEND_FLOW.md](dev_docs/BACKEND_FLOW.md) | Startup, launch, ingest, and upload flow atlas |
| [AUTH.md](dev_docs/AUTH.md) | Auth flows, token and cookie lifecycle, permission model |
| [SECURITY.md](dev_docs/SECURITY.md) | Threat model, mandatory implementation rules, known gaps |
| [windows-sandbox.md](dev_docs/windows-sandbox.md) | Job Object and AppContainer isolation, resource caps |
| [TYPES.md](dev_docs/TYPES.md) | Constants and type-generation pipelines, settings inventory |
| [TESTING.md](dev_docs/TESTING.md) | What the suites cover, and what they do not |

The Docusaurus site under [`docs/`](docs/) carries the user-facing guides and the generated
API reference.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Attributions

Peach 1UP redistributes the following third-party software via its own bundle repo. Per-emulator
`NOTICE` and `SOURCE_OFFER.txt` files cover GPL source-offer compliance.

| Project | License |
|---|---|
| [86Box](https://github.com/86Box/86Box) | GPL-2.0-or-later |
| [DOSBox-X](https://github.com/joncampbell123/dosbox-x) | GPL-2.0-or-later |
| [DuckStation](https://github.com/stenzek/duckstation) | CC BY-NC-ND 4.0 |
| [Flycast](https://github.com/flyinghead/flycast) | GPL-2.0-or-later |
| [Mesen](https://github.com/SourMesen/Mesen2) | GPL-3.0-or-later |
| [PCSX2](https://github.com/PCSX2/pcsx2) | GPL-3.0-or-later |
| [Project64](https://github.com/project64/project64) | GPL-2.0-or-later |
| [RPCS3](https://github.com/RPCS3/rpcs3) | GPL-2.0-or-later |
| [xemu](https://github.com/xemu-project/xemu) | GPL-2.0-or-later |
| [Xenia](https://github.com/xenia-project/xenia) | BSD-3-Clause |
| [extract-xiso](https://github.com/XboxDev/extract-xiso) | BSD-3-Clause |
| [7-Zip (7za)](https://www.7-zip.org/) | LGPL-2.1-or-later |
| [formatscout](https://github.com/rymorrisj/formatscout) | MIT |
| [wincage](https://github.com/rymorrisj/wincage) | MIT |

See [NOTICE](NOTICE) for full copyright lines, source URLs, and per-emulator license file
paths.

## License

GNU General Public License v2.0 or later. See [LICENSE](LICENSE).
