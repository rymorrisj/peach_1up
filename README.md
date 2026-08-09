# Peach 1UP

[![Windows Only](https://img.shields.io/badge/platform-Windows--10%20%2F%2011-blue.svg)](https://microsoft.com/windows)
[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://www.python.org/downloads/)

Preservation automation tool for PC and console platforms. Point it at a disk image, pick an era, and it launches the correct emulator with the media mounted and sensible defaults applied, no manual emulator configuration required.

Covers PC platforms from DOS through Windows XP and PS1, PS2, PS3, Xbox OG, Xbox 360, Dreamcast, NES, SNES, and N64.

## Prerequisites

### Emulators (installed on the host OS)

| Emulator | Era | Data location | Notes |
|---|---|---|---|
| DOSBox-X | DOS | Portable via config | [dosbox-x.com](https://dosbox-x.com), no ROM required |
| 86Box | Win95/98/XP | Portable via layout | [86box.net](https://86box.net), requires [ROM pack](https://github.com/86Box/roms) |
| DuckStation | PS1 | Portable via sentinel | [duckstation.org](https://www.duckstation.org), requires PS1 BIOS |
| PCSX2 | PS2 | Portable via sentinel | [pcsx2.net](https://pcsx2.net), requires PS2 BIOS |
| xemu | Xbox OG | Portable via sentinel, partial | [xemu.app](https://xemu.app), requires Xbox BIOS |
| Flycast | Dreamcast | Portable via sentinel | [github.com/flyinghead/flycast](https://github.com/flyinghead/flycast), requires DC BIOS |
| Mesen | NES, SNES | Portable via first-run choice | [mesen.ca](https://www.mesen.ca) |
| Project64 | N64 | Portable by default | [pj64-emu.com](https://www.pj64-emu.com) |
| RPCS3 | PS3 | Portable by default | [rpcs3.net](https://rpcs3.net/download), requires PS3 firmware |
| Xenia | Xbox 360 | Portable via sentinel | [xenia.jp](https://xenia.jp) |

Emulators marked "requires BIOS" need a BIOS image sourced from your own hardware. Peach 1UP does not provide BIOS files.

**Data location** describes where each emulator keeps saves, configs, and caches, per
[EMULATORS.md](dev_docs/EMULATORS.md):

- **Portable by default**: writes into its own directory under `emulators/<slug>/` with no
  setup. RPCS3 treats its executable directory as the data root on Windows; Project64
  stores config in `<install dir>\Config\` whenever that directory is writable.
- **Portable via sentinel**: portable once a sentinel file sits next to the binary
  (`portable.txt` for DuckStation, PCSX2, and Xenia; `emu.cfg` for Flycast; `xemu.toml`
  for xemu), which the emulator descriptor's `portable_sentinel` field drives. Without the
  sentinel these fall back to `%APPDATA%\<Emulator>\`, or `Documents\Xenia\` for Xenia.
- **Portable via layout / config**: 86Box detects portable mode from `roms/` and `assets/`
  directories placed next to the binary; DOSBox-X resolves data paths relative to the
  config file passed with `-conf`. Their non-portable fallback is `%APPDATA%\86Box\` and
  `%APPDATA%\DOSBox-X\`.
- **Portable via first-run choice**: Mesen asks on first run where to store data and is
  only portable if the application directory is chosen. Otherwise it uses
  `%APPDATA%\Mesen\`.

Two caveats worth knowing: xemu is only **partially** portable, since its `-config_path`
flag does not redirect the shader cache or log files, which always write to the default
user profile location ([xemu issue #2480](https://github.com/mborgerson/xemu/issues/2480)).
And Mesen's portability depends on an interactive first-run choice rather than anything
Peach 1UP sets, so it cannot be assumed. Follow the startup guide during your first launch
to set your chosen settings

### Python

| Requirement | Notes |
|---|---|
| Python 3.14+ | [python.org](https://www.python.org/downloads/), pinned via `requires-python` in `pyproject.toml`, matches CI |
| uv | [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/), manages the venv and dependencies |

## Vendored packages

Other tools we use (formatscout and wincage will move here once they are completed)

| Tool | License |
|---|---|---|
| [7-Zip (7za)](https://www.7-zip.org/) | RPCS3 archive decompression, `services/vendor/7z/7za.exe` |
| [extract-xiso](https://github.com/XboxDev/extract-xiso) | Xbox DVD-rip to xISO conversion |
| [formatscout](https://github.com/rymorrisj/formatscout) | Fromat detection, classification and detection |
| [wincage](https://github.com/rymorrisj/wincage) | Windows sandboxing and resource control layer |

*Note:* formatscout and wincage are not currently committed under services/vendor/. Clone each into its matching path (services/vendor/formatscout, services/vendor/wincage) before running uv sync, then follow that package's own README for any build steps (wincage specifically needs its native binary compiled via MSYS2 first).

## Development

```bash
# Backend
uv sync --group dev
start.bat

# Frontend (separate terminal)
cd frontend && npm run dev
```

## Build

A root build script bundles all build commands and tasks; parts can also be rebuilt individually. Packaging is Windows-only (`build.bat`).

```bash
build.bat     # Windows
```

**1. Generate the tray icon**

```bash
.venv\Scripts\python.exe scripts\gen_icon.py
```

Writes `assets/peach1up.png` (16×16 solid peach #ff8a5c).

**2. Build the frontend**

```bash
cd frontend && npm run build && cd ..
```

**3. Package with PyInstaller**

```bash
uv sync --group build
.venv\Scripts\python.exe -m PyInstaller peach1up.spec
```

Output: `dist\peach1up\`, a self-contained directory containing `peach1up.exe`. `frontend/dist/` must exist before running PyInstaller.

**4. Build the installer**

Requires [NSIS](https://nsis.sourceforge.io/) and [WinSW](https://github.com/winsw/winsw/releases) (WinSW-x64.exe renamed to `Peach1UP.exe`) placed at `installer\tools\Peach1UP.exe`.

```bash
makensis installer\peach1up.nsi
```

Output: `Peach1UP-Setup.exe`. Installs to `%PROGRAMFILES%\Peach1UP\`, registers a Windows service via WinSW, and creates a Start Menu shortcut. The uninstaller stops the service and removes all files except `database\data\` (settings and library data) and `.env`, which are preserved.

## Process isolation

Each emulator launches inside a Windows AppContainer/Job Object sandbox identified by a moniker of the form `Peach1UP.<slug>.<scope>`. Confirmed real examples: `Peach1UP.duckstation.shared`, `Peach1UP.mesen.shared`.

- `<slug>` matches the emulator catalog's `slug` field. If unsure of an emulator's exact slug, check its TOML descriptor under `config/emulators/` (the `slug` field is on the first line) or the catalog listing.
- `<scope>` is `shared` for the non-per-item container. A per-item-id scope variant also exists, using the decimal `user_item_id` in place of `shared` (e.g. `Peach1UP.duckstation.42`).

Sandboxing itself is handled by [wincage](https://github.com/rymorrisj/wincage), a standalone Windows AppContainer/Job Object sandboxing package extracted from this project.

## Configuration

Runtime settings (binary paths, operational flags, per-emulator overrides) are stored in the `settings` table inside the SQLite database at `database/data/peach1up.db`, there is no settings file to edit. Most are configurable from the Settings page in the app. Secrets (PIN pepper, TheGamesDB API key, etc.) live separately in a root `.env` file, see `.env.template` for the supported keys.

## Documentation

[CHANGELOG.md](CHANGELOG.md) covers project history and notable decisions.

Contributor references live in [`dev_docs/`](dev_docs/):

| Document | Covers |
|---|---|
| [TECH.md](dev_docs/TECH.md) | Full technology stack with reasoning |
| [EMULATORS.md](dev_docs/EMULATORS.md) | Emulator reference, portable mode, BIOS requirements, version coupling notes |
| [BACKEND_FLOW.md](dev_docs/BACKEND_FLOW.md) | Request, launch, ingest, and startup flow atlas |
| [AUTH.md](dev_docs/AUTH.md) | Auth flows, token and cookie lifecycle, permission model |
| [SECURITY.md](dev_docs/SECURITY.md) | Threat model, mandatory implementation rules, known gaps |
| [windows-sandbox.md](dev_docs/windows-sandbox.md) | Job Object isolation and per-era resource caps |
| [TYPES.md](dev_docs/TYPES.md) | Constants and type-generation pipelines, settings key inventory |
| [TESTING.md](dev_docs/TESTING.md) | What the test suites cover today, and what they do not |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contributor guide: branch and commit conventions, static verification, and code style.

## Attributions

Peach 1UP bundles or installs the following third-party emulators and tools

| Emulator | License |
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

See [NOTICE](NOTICE) for full copyright lines, source URLs, and per-emulator license file paths.

## License

GNU General Public License v2.0 or later. See [LICENSE](LICENSE).