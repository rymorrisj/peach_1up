# Peach 1UP — Technology Stack

Peach 1UP is a preservation automation tool. The stack was chosen to maximise
community accessibility, developer familiarity, and long-term maintainability
as an open source project.

---

## Infrastructure

PyInstaller compiles the Python backend to a standalone executable. React builds to static files served by FastAPI. pystray provides a system tray icon. Windows installer via NSIS/WiX. CI/CD pipeline planned (P7).

## Platform

**Windows-only.**

The application runs natively on Windows 10/11. Emulators run natively on the host OS.
Linux support was removed from scope (DECISIONS.md 2026-07-17) — process isolation is
Windows Job Objects only, and Linux-specific code paths (filesystem.py, dosbox.py,
emulator_installer.py, extract_xiso.py, path_utils.py) have been removed from the backend.

## Database

**SQLite via SQLModel, create_all() on startup.**

Read-heavy usage pattern makes SQLite sufficient. SQLAlchemy abstraction means
Postgres is a future config change not a rewrite.

*NOTE* Currently, the DB is open/closed per call. There is no long lived hot connection

## Backend

**Python 3.14 or later (pinned via `requires-python` in `pyproject.toml`, matches CI), FastAPI, Pydantic, python-dotenv, PyYAML.**

Python chosen for existing codebase and emulator scripting ecosystem. FastAPI
for async performance, automatic OpenAPI generation, and Pydantic validation.

## API Bridge

**FastAPI auto-generates an OpenAPI spec. openapi-typescript or Orval generates a typed API client for the React frontend.**

No manual type duplication between backend and frontend. Schema changes in
Python propagate automatically to the TypeScript client.

## Frontend

**TypeScript, React, Vite, React Router, TanStack Query, useReducer, Tailwind CSS, Radix UI primitives (dialog, slot).**

React chosen for ecosystem size and developer availability. TypeScript required
throughout. Radix UI primitives (dialog, slot) with hand-rolled component library.

## Emulators (PC)

- **DOSBox-X** — DOS. No ROM required.
- **86Box** — Windows 95, 98, XP. User supplies ROM pack.

### Limitations

DOSBox-X: DOS game sound requires HDD image install flow — games that write their sound config to the install directory (e.g. Doom DEFAULT.CFG) will have no in-game sound when launched directly from a read-only ISO. Sound works correctly once the game is installed to a writable HDD image via the install flow. Direct ISO launch is intentionally read-only and cannot persist game config. No code change required — this is expected behaviour.

## Emulators (Console)

- DuckStation — PS1
- PCSX2 — PS2
- xemu — Xbox OG
- Mesen — NES, SNES
- Project64 — N64
- Flycast — Dreamcast
- RPCS3 — PS3
- Xenia — Xbox 360

All console emulators (and DOSBox-X/86Box) are installed on demand via
`install_type = "github_release"` (Project64 is the one manual-download exception — see
EMULATORS.md's Legal table). None ship bundled inside the repository.

## Process Isolation

**Windows Job Objects.**

Network blocking enforced at the emulator level on every launch — each emulator is
started with its network adapter disabled when `enable_networking` is false on the
active profile. Job Objects provide kill-on-close, CPU cap, and memory cap on Windows.
Linux support, and the earlier cgroups/network-namespaces isolation plan for it, was
removed from scope — see DECISIONS.md 2026-07-17.

## Documentation

**Docusaurus.**

React-based, versioned, MDX, full-text search. Chosen for consistency with the
frontend stack and suitability for a growing open source project expecting
community contributors.

## Smart Scanner

`smart_media_detector` is the self-contained media detection package that identifies platform and era from a disk image or directory path. It lives at `backend/service/utils/smart_media_detector/` and is designed to be vendored into its own standalone repository after the Beta ships. It is not fully import-clean today: both `detector.py` and `directory_detect.py` still import `backend.core.logger` for their module loggers, and `iso_detect.py` imports a sibling module, `backend/service/utils/xbox_image.py`, that lives outside the package folder. The package no longer imports `backend.service.backends.rpcs3` — `is_disc_format_folder`/`find_eboot` moved into `directory_detect.py` as part of the MediaTarget refactor (Step 3), closing the one backend-into-detector dependency this package had (that inversion was the more significant gap; the two `backend.core.logger` imports are a much smaller remaining seam). See the package's own README.md for the full standalone-package-readiness rundown, including dead code that was already removed as part of getting closer to this goal.

### Detection pipeline

Detection runs in tier order and short-circuits on the first confident match:

1. **Hash lookup** — full-file SHA-1 (with MD5/CRC32 fallback) compared against a bundled `hash_index.json` built from No-Intro/Redump DAT files, which key entries by full-file hash. Returns the highest-confidence result possible; exits immediately on a hit.
2. **Magic bytes** — file header compared against `magic/magic_signatures.toml`. Covers GDI, CDI, BIN, ISO, and CHD container signatures.
3. **Structural validation** — deeper parse of the container format:
   - ISO: reads the ISO 9660 PVD (sector 16) for volume label, publisher, and system-ID fields; falls back to scanning the root directory for `.xbe` (Xbox OG) markers.
   - CHD: walks the CHD v5 metadata chain — `CHGD` tag → Dreamcast; `CHTR`/`CHT2` tag → PS2.
   - BIN/CUE: resolves the `.cue` sheet to its `.bin` sibling, then runs magic-byte and PVD checks on the binary.
4. **Directory heuristics** — inspects root-level filenames and subdirectory structure for OS installer markers (`I386`, `WIN98`, `XPSP`, `SYSTEM.CNF`, `AUTORUN.INF`, DOS tool names, `.WAD` files, etc.).
5. **Extension / size fallback** — lowest-confidence tier; uses file extension and file size as weak signals when no structural match is found.

## Upload System

Single-file and folder uploads are handled by the chunked upload router at
`/api/v1/software/uploads/*` — `POST /init` opens a session and the per-chunk
`PUT /{upload_id}/chunks/{file_index}/{chunk_index}` calls stream the bytes. All
upload routes require `can_manage_software` permission.

**File size limits:** enforced per-file via `stream_upload_to_disk` (see
`upload_utils.py` for the current cap). No total-folder-size limit exists
for folder uploads — each file in a multipart folder upload is individually
capped, but the aggregate is unbounded. Acceptable for local household use;
revisit if a cap is ever needed.

**Folder upload browser support:** uses the `webkitdirectory` input attribute.
Originally Chrome-specific but now widely supported across all major browsers
(Chrome, Edge, Firefox, Safari). Browsers that do not support it will fall
back to a standard file picker silently.

**Path safety:** all uploaded filenames pass through `sanitize_filename` +
`resolve_under` before any write to `MEDIA_PATH`. Folder uploads clean up
the entire destination directory on any single file failure — no partial
folder ingest is possible.

### Known limitations

- **Xbox OG ISOs without `DEFAULT.XBE` at the ISO root** will not resolve platform via structural scan (the `.xbe` directory scan comes up empty). The magic-byte check still applies as a fallback. Standard Xbox rips typically include `DEFAULT.XBE` at the root, so this case is expected to be rare in practice.
- **`.bin`/`.cue` pairs without a matching `.cue` sibling** return low confidence and `requires_manual_boot = True`. The scanner cannot resolve CD layout without a cue sheet.
- **`requires_install` heuristic** (DOS/Windows installer-only directory detection) is approximate — it checks whether every executable at the directory root is on the blocklist. Tuning may be needed based on Beta feedback.

## Developer Tooling

- uv — Python dependency management, lockfile (`uv.lock`), and virtual environments
- Ruff — Python linting
- pytest — Python testing
- ESLint and Prettier — Frontend linting and formatting
- Vitest — Frontend testing
