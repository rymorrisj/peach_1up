# Peach 1UP: Technology Stack

Peach 1UP is a preservation automation tool. The stack was chosen to maximise
community accessibility, developer familiarity, and long-term maintainability as an
open source project.

Related: [TYPES.md](TYPES.md) for the constants and type pipelines,
[EMULATORS.md](EMULATORS.md) for per-emulator detail,
[BACKEND_FLOW.md](BACKEND_FLOW.md) for the request and launch flows.

---

## Infrastructure

PyInstaller compiles the Python backend to a standalone executable
([`peach1up.spec`](../peach1up.spec)). React builds to static files served by FastAPI.
pystray provides a system tray icon. The Windows installer is built with
[NSIS](https://nsis.sourceforge.io/) ([`installer/peach1up.nsi`](../installer/peach1up.nsi))
and registers a service via [WinSW](https://github.com/winsw/winsw). CI runs on GitHub
Actions ([`.github/workflows/test.yml`](../.github/workflows/test.yml) for tests,
`codeql.yml` for static analysis, `release.yml` for packaging).

## Platform

**Windows-only.**

The application runs natively on Windows 10/11, and emulators run natively on the host
OS. Linux support was removed from scope ([DECISIONS.md](DECISIONS.md) 2026-07-17):
process isolation is Windows Job Objects only, and the Linux-specific code paths in
`filesystem.py`, `dosbox.py`, `emulator_installer.py`, `extract_xiso.py`, and
`path_utils.py` have been removed from the backend.

## Database

**SQLite via SQLModel, `create_all()` on startup.**

The read-heavy usage pattern makes SQLite sufficient, and the SQLAlchemy abstraction
makes Postgres a future config change rather than a rewrite.

*NOTE:* the DB is opened and closed per call. There is no long-lived hot connection.

## Backend

**Python 3.14 or later** (pinned via `requires-python` in
[`pyproject.toml`](../pyproject.toml), matches CI), **FastAPI, Pydantic,
python-dotenv, PyYAML.**

Python was chosen for the existing codebase and the emulator scripting ecosystem.
FastAPI provides async performance, automatic OpenAPI generation, and Pydantic
validation. Argon2 (`argon2-cffi`) handles PIN hashing, `pycdlib` handles ISO parsing,
and `httpx` handles outbound metadata calls.

Two components have been extracted into standalone packages and are consumed as
dependencies, vendored under [`services/vendor/`](../services/vendor/):

- [`formatscout`](../services/vendor/formatscout/): disk-image and directory format
  detection.
- [`wincage`](../services/vendor/wincage/): Windows AppContainer and Job Object
  sandboxing.

## API bridge

**FastAPI auto-generates an OpenAPI spec; `openapi-typescript` generates the typed
client for the React frontend.**

There is no manual type duplication between backend and frontend: schema changes in
Python propagate to the TypeScript client. The generator is wired as the
`generate:api` script in [`frontend/package.json`](../frontend/package.json) and driven
by [`scripts/export_and_build_types.py`](../scripts/export_and_build_types.py). See
[TYPES.md](TYPES.md) § Pipeline B for the full chain and its refresh-trigger caveat.

## Frontend

**TypeScript, React, Vite, React Router, TanStack Query, `useReducer`, Tailwind CSS,
Radix UI primitives (dialog, slot).**

React was chosen for ecosystem size and developer availability. TypeScript is required
throughout. Radix UI primitives back a hand-rolled component library.

## Emulators (PC)

| Emulator | Eras | ROM requirement |
| -------- | ---- | --------------- |
| DOSBox-X | DOS | None |
| 86Box | Windows 95, 98, XP | User supplies the 86Box ROM pack |

### DOSBox-X sound limitation

DOS game sound requires the HDD image install flow. Games that write their sound config
to the install directory (e.g. Doom's `DEFAULT.CFG`) have no in-game sound when launched
directly from a read-only ISO. Sound works correctly once the game is installed to a
writable HDD image via the install flow. Direct ISO launch is intentionally read-only and
cannot persist game config, so no code change is required; this is expected behaviour.

## Emulators (console)

| Emulator | Era |
| -------- | --- |
| DuckStation | PS1 |
| PCSX2 | PS2 |
| RPCS3 | PS3 |
| xemu | Xbox OG |
| Xenia | Xbox 360 |
| Mesen | NES, SNES |
| Project64 | N64 |
| Flycast | Dreamcast |

Every emulator, including DOSBox-X and 86Box, is installed on demand rather than shipped
in the repository. All use `install_type = "github_release"` except Project64, which is
`install_type = "zip"` because the project publishes git tags but no release assets and
must be downloaded manually. See the Legal table in [EMULATORS.md](EMULATORS.md).

## Process isolation

**Windows Job Objects, with AppContainer layered on top where supported.**

Job Objects provide kill-on-close plus optional CPU and memory caps; every emulator
descriptor currently waives both caps, so kill-on-close is what is actually enforced.
Network blocking is enforced at the emulator level on every launch: each emulator starts
with its network adapter disabled when `enable_networking` is false on the active
profile. Linux support, and the earlier cgroups/network-namespaces isolation plan for it,
was removed from scope ([DECISIONS.md](DECISIONS.md) 2026-07-17).

Full detail: [windows-sandbox.md](windows-sandbox.md) and
[SECURITY.md](SECURITY.md) § Windows-specific process rules.

## Documentation

**Docusaurus.**

React-based, versioned, MDX, full-text search. Chosen for consistency with the frontend
stack and suitability for a growing open source project expecting community
contributors. The site source lives in [`docs/`](../docs/); the contributor-facing
reference documents live in [`dev_docs/`](.).

## Media detection

Detection lives in the vendored
[`formatscout`](../services/vendor/formatscout/) package, extracted from this project
and now consumed as a dependency. The Peach-specific launch-target resolvers that stayed
behind (PS3, Xbox 360 XEX, Xbox optical images, MediaTarget) live in
[`backend/service/utils/detection/`](../backend/service/utils/detection/). Backend code
imports the package directly as `formatscout`, mostly through lazy imports at call sites.

### Detection pipeline

Detection runs in tier order and short-circuits on the first confident match:

1. **Hash lookup.** Full-file SHA-1 (with MD5/CRC32 fallback) compared against a bundled
   `hash_index.json` built from No-Intro/Redump DAT files, which key entries by full-file
   hash. Returns the highest-confidence result possible and exits immediately on a hit.
   Coverage is currently limited to PS1 and Xbox; see
   [SECURITY.md](SECURITY.md) § Smart Detection.
2. **Magic bytes.** File header compared against `magic/magic_signatures.toml`. Covers
   GDI, CDI, BIN, ISO, and CHD container signatures.
3. **Structural validation.** A deeper parse of the container format:
   - ISO: reads the ISO 9660 PVD (sector 16) for volume label, publisher, and system-ID
     fields; falls back to scanning the root directory for `.xbe` (Xbox OG) markers.
   - CHD: walks the CHD v5 metadata chain (`CHGD` tag → Dreamcast; `CHTR`/`CHT2` tag →
     PS2).
   - BIN/CUE: resolves the `.cue` sheet to its `.bin` sibling, then runs magic-byte and
     PVD checks on the binary.
4. **Directory heuristics.** Inspects root-level filenames and subdirectory structure for
   OS installer markers (`I386`, `WIN98`, `XPSP`, `SYSTEM.CNF`, `AUTORUN.INF`, DOS tool
   names, `.WAD` files, and similar).
5. **Extension / size fallback.** Lowest-confidence tier; uses file extension and file
   size as weak signals when no structural match is found.

### Known limitations

- **Xbox OG ISOs without `DEFAULT.XBE` at the ISO root** will not resolve platform via
  the structural scan, because the `.xbe` directory scan comes up empty. The magic-byte
  check still applies as a fallback. Standard Xbox rips typically include `DEFAULT.XBE`
  at the root, so this case is expected to be rare.
- **`.bin`/`.cue` pairs without a matching `.cue` sibling** return low confidence and
  `requires_manual_boot = True`. The scanner cannot resolve CD layout without a cue
  sheet.
- **The `requires_install` heuristic** (DOS/Windows installer-only directory detection)
  is approximate: it checks whether every executable at the directory root is on the
  blocklist. Tuning may be needed based on Beta feedback.

## Upload system

Chunked uploads are served by three per-domain routers built from a shared factory in
[`backend/api/routes/uploads.py`](../backend/api/routes/uploads.py). Each mounts at
`/api/v1/uploads/{domain}` and is gated by its own permission flag:

| Router prefix | Domain | Permission | Allowed kinds |
| ------------- | ------ | ---------- | ------------- |
| `/api/v1/uploads/software-games` | `software_games` | `can_manage_game` | file, folder, set |
| `/api/v1/uploads/software-media` | `software_media` | `can_manage_media` | file |
| `/api/v1/uploads/software-apps` | `software_apps` | `can_manage_app` | file, folder |

`POST /init` opens a session and declares the manifest; the per-chunk
`PUT /{upload_id}/chunks/{file_index}/{chunk_index}` calls stream the bytes;
`POST /{upload_id}/complete` finalizes. Domains are registered explicitly at startup by
`_register_upload_domains()` in [`backend/core/lifespan.py`](../backend/core/lifespan.py)
rather than by import-time decorator side effects, so a missing or duplicate registration
fails loudly.

**Size limits.** `DEFAULT_MAX_BYTES` is 25 GB per file and `DEFAULT_CHUNK_MAX_BYTES` is
64 MB per chunk, both in
[`backend/service/utils/upload_utils.py`](../backend/service/utils/upload_utils.py) and
both overridable through settings. No total-folder-size limit exists for folder uploads:
each file is individually capped, but the aggregate is unbounded. Acceptable for local
household use; revisit if a cap is ever needed.

**Folder upload browser support.** Uses the `webkitdirectory` input attribute. Originally
Chrome-specific but now widely supported across Chrome, Edge, Firefox, and Safari.
Browsers that do not support it fall back to a standard file picker silently.

**Path safety.** All uploaded filenames pass through `safe_basename` and `resolve_under`
before any write beneath the destination root. Folder uploads clean up the entire
destination directory on any single-file failure, so no partial folder ingest is
possible.

## Developer tooling

| Tool | Purpose |
| ---- | ------- |
| [uv](https://docs.astral.sh/uv/) | Python dependency management, lockfile (`uv.lock`), virtual environments |
| [Ruff](https://docs.astral.sh/ruff/) | Python linting |
| [pytest](https://docs.pytest.org/) | Python testing |
| ESLint and Prettier | Frontend linting and formatting |
| [Vitest](https://vitest.dev/) | Frontend testing |

See [TESTING.md](TESTING.md) for the current state of the suites and
[CONTRIBUTING.md](../CONTRIBUTING.md) for the static-verification rules that apply
instead of running them locally.
