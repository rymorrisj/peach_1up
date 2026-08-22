# Technology Stack

What Peach 1UP is built on and why.

Related: [TYPES.md](TYPES.md) (constants and type pipelines) · [EMULATORS.md](EMULATORS.md)
(per-emulator detail) · [BACKEND_FLOW.md](BACKEND_FLOW.md) (request and launch flows).

## At a glance

| Layer | Choice |
|---|---|
| Platform | Windows 10/11 only |
| Backend | Python 3.14+, FastAPI, Pydantic, SQLModel |
| Database | SQLite, `create_all()` on startup, no Alembic |
| Frontend | TypeScript, React, Vite, TanStack Query, Tailwind v3, Radix primitives |
| Type bridge | FastAPI OpenAPI spec to `openapi-typescript` to `shared/types.ts` |
| Isolation | Windows Job Objects, AppContainer layered on top where supported |
| Packaging | PyInstaller, NSIS, WinSW, pystray |
| Docs | Docusaurus, served at `/docs` |
| Tooling | uv, Ruff, pytest, ESLint, Prettier, Vitest |

## Platform

Windows-only. The app runs natively on Windows 10/11 and emulators run natively on the
host OS. Linux support was removed from scope on 2026-07-17; the Linux code paths in
`filesystem.py`, `dosbox.py`, `emulator_installer.py`, `extract_xiso.py`, and
`path_utils.py` are gone.

## Backend

Python 3.14 or later, pinned via `requires-python` in [`pyproject.toml`](../pyproject.toml)
and matched by CI. FastAPI provides async performance, automatic OpenAPI generation, and
Pydantic validation.

| Library | Use |
|---|---|
| `argon2-cffi` | PIN hashing |
| `pycdlib` | ISO parsing |
| `httpx` | Outbound metadata calls |
| `PyYAML` | `eras.yaml`, `constants.yaml` |
| `python-dotenv` | `.env` secrets |

Two components are extracted into standalone packages and consumed as regular PyPI
dependencies:

| Package | Covers |
|---|---|
| [`formatscout`](https://pypi.org/project/formatscout/) | Disk-image and directory format detection, hashing, verification |
| [`wincage`](https://pypi.org/project/wincage/) | Windows AppContainer and Job Object sandboxing, plus `sandbox_host.exe` |

Both install via `uv sync` like any other dependency. `wincage`'s wheel is Windows-only
(`win_amd64`) and ships a prebuilt `sandbox_host.exe` inside the installed package
directory, no MSYS2 or other native build step required.

## Database

SQLite via SQLModel, `create_all()` on startup. Read-heavy single-library usage makes
SQLite sufficient, and the SQLAlchemy abstraction keeps Postgres a config change rather
than a rewrite. The connection is opened and closed per call; there is no long-lived hot
connection.

## API bridge

FastAPI emits the OpenAPI spec; `openapi-typescript` generates the typed client. There is
no manual type duplication between backend and frontend. Driven by
[`scripts/export_and_build_types.py`](../scripts/export_and_build_types.py) and wired as
the `generate:api` script in `frontend/package.json`. See [TYPES.md](TYPES.md) for the
full chain.

## Frontend

React for ecosystem size and developer availability, TypeScript throughout. Radix UI
primitives (dialog, tabs, toast, collapsible, slot) back a hand-rolled component library
on an RGB-triplet CSS variable color system with `data-skin` scaffolding.

Tailwind is pinned to v3. Do not upgrade until shadcn/ui supports v4.

## Emulators

| Emulator | Era | ROM or BIOS required |
|---|---|---|
| DOSBox-X | DOS | No |
| 86Box | Windows 95, 98, XP | Yes, 86Box ROM pack |
| DuckStation | PS1 | Yes, PS1 BIOS |
| PCSX2 | PS2 | Yes, PS2 BIOS |
| RPCS3 | PS3 | Yes, PS3 firmware |
| xemu | Xbox OG | Yes, Xbox BIOS |
| Xenia | Xbox 360 | No |
| Mesen | NES, SNES | No |
| Project64 | N64 | No |
| Flycast | Dreamcast | Yes, DC BIOS |

Every emulator installs on demand rather than shipping in the repository. Nine use
`install_type = "github_release"`. Project64 is `install_type = "zip"`: the project
publishes git tags but no release assets, so the user downloads it from pj64-emu.com and
extracts it into `emulators/project64/`. See the Legal table in
[EMULATORS.md](EMULATORS.md).

### DOSBox-X sound limitation

DOS games that write sound config to their install directory (Doom's `DEFAULT.CFG`, for
example) have no in-game sound when launched from a read-only ISO. Installing the game to
a writable HDD image through the install flow fixes it. Direct ISO launch is intentionally
read-only and cannot persist game config; no code change is required.

## Process isolation

Windows Job Objects, with AppContainer layered on top where the emulator supports it.

Job Objects provide kill-on-close plus a per-era CPU rate cap and per-process memory cap.
**All three are enforced today.** Every descriptor in [`config/emulators/`](../config/emulators/)
sets `skip_cpu_limit = false` and `skip_memory_limit = false`, so there are no active
waivers.

Network blocking is emulator-native, applied on every launch: each emulator starts with
its network adapter disabled when `enable_networking` is false on the active profile.

Full detail: [windows-sandbox.md](windows-sandbox.md) and [SECURITY.md](SECURITY.md)
§ Windows-specific process rules.

## Media detection

Detection lives in the [`formatscout`](https://pypi.org/project/formatscout/) package.
The Peach-specific launch-target resolvers that stayed behind (PS3, Xbox 360 XEX, Xbox
optical images, `MediaTarget`) live in
[`backend/service/utils/detection/`](../backend/service/utils/detection/). Backend code
imports the package as `formatscout`, mostly through lazy imports at call sites.

### Pipeline

Tiers run in order and short-circuit on the first confident match.

| Tier | Method | Notes |
|---|---|---|
| 1 | Full-file SHA-1, falling back to MD5 then CRC32 | Compared against a bundled `hash_index.json` built from No-Intro/Redump DATs. Confidences 1.0 / 0.85 / 0.75. For `.chd`, raw bytes never match Redump, so the CHD v5 header's embedded `rawsha1` is read instead. |
| 2 | Magic bytes | `magic/magic_signatures.toml`. Covers GDI, CDI, BIN, ISO, CHD. |
| 3 | Structural validation | ISO: ISO 9660 PVD at sector 16 for volume label, publisher, system ID; falls back to scanning the root for `.xbe`. CHD: `CHGD` means Dreamcast, `CHTR`/`CHT2` means PS1 or PS2 split by logical size. BIN/CUE: resolve the cue sheet to its bin sibling, then re-run magic and PVD. |
| 4 | Directory heuristics | Root filenames and subdirectory structure: `I386`, `WIN98`, `XPSP`, `SYSTEM.CNF`, `AUTORUN.INF`, DOS tool names, `.WAD` files. |
| 5 | Extension and size | Lowest confidence, weak signals only. |

PS1 versus PS2 is resolved consistently by `SYSTEM.CNF` `BOOT`/`BOOT2` in both the
raw-sector and extracted-file paths.

### Known limitations

- **Hash-index coverage is PS1 and Xbox only.** Every other era falls through to the
  lower-confidence tiers regardless of whether the file is corrupted.
- **Xbox OG ISOs without `DEFAULT.XBE` at the root** do not resolve platform structurally;
  the magic-byte check is the fallback. Standard rips include it, so this is rare.
- **`.bin`/`.cue` pairs with no matching `.cue` sibling** return low confidence and
  `requires_manual_boot = True`. CD layout cannot be resolved without a cue sheet.
- **`requires_install` is approximate.** It checks whether every executable at a directory
  root is on the blocklist, and is gated to DOS and Win3.1 only.

## Upload system

Three per-domain routers built from one factory in
[`backend/api/routes/uploads.py`](../backend/api/routes/uploads.py).

| Prefix | Domain | Permission | Allowed kinds |
|---|---|---|---|
| `/api/v1/uploads/software-games` | `software_games` | `can_manage_game` | file, folder, set |
| `/api/v1/uploads/software-media` | `software_media` | `can_manage_media` | file |
| `/api/v1/uploads/software-apps` | `software_apps` | `can_manage_app` | file, folder |

```
POST /init                                    open session, declare manifest, create job
PUT  /{upload_id}/chunks/{file_idx}/{chunk}   stream bytes
POST /{upload_id}/complete                    always 202, finalizes as a BackgroundTask
DELETE /{upload_id}                           abort
```

The job entry is created at `/init`, before any bytes transfer, so the nav bell tracks an
upload from the start. It is attached to the session rather than returned for the client
to echo back, so `/complete` resolves it itself instead of trusting a client-supplied ID.
There is no inline-finalize path.

Domains are registered explicitly by `_register_upload_domains()` in
[`backend/core/lifespan.py`](../backend/core/lifespan.py) rather than by import-time
decorator side effects, so a missing or duplicate registration fails loudly.

**Limits.** `DEFAULT_MAX_BYTES` is 25 GB per file, `DEFAULT_CHUNK_MAX_BYTES` is 64 MB per
chunk, both in `upload_utils.py` and both overridable through settings. Session creation
is rate limited to 10 per 60s across all domains; per-chunk PUTs are not (a legitimate
large upload is hundreds of requests). There is no total-folder-size cap: each file is
capped individually, the aggregate is unbounded. Acceptable for local household use.

**Path safety.** Every uploaded filename passes through `safe_basename` and `resolve_under`
before any write beneath the destination root. Folder uploads clean up the whole
destination directory on any single-file failure, so no partial folder ingest is possible.

**Browser support.** Folder upload uses the `webkitdirectory` input attribute, now widely
supported. Browsers without it fall back to a standard file picker silently.

## CI

| Workflow | Jobs |
|---|---|
| [`test.yml`](../.github/workflows/test.yml) | `generate-types` (ubuntu, `uv lock --check`, regenerate constants and types), `backend` (windows, Ruff then `pytest --cov`), `frontend` (ubuntu, ESLint, Prettier, production build, `vitest run --coverage`), `packaging-smoke` (windows, PyInstaller build, size assertion, frozen-exe smoke launch) |
| `codeql.yml` | Static analysis |
| `release.yml` | Tag-triggered Windows release build. The tag must match the version in `constants.yaml` or the build fails. Signing is stubbed pending an OSS certificate. |

Runs on every push and pull request to `main`.

> **The generated-file staleness check in `generate-types` cannot fail.** It runs
> `git diff --exit-code` against `constants_generated.py`, `generated/constants.ts`,
> `openapi.json`, and `types.ts`, but all four are gitignored and untracked, so `git diff`
> has nothing to compare and always exits 0. Fixing it means either committing the
> generated files or replacing the check with a content diff against a pre-generation
> copy.

## Developer tooling

| Tool | Purpose |
|---|---|
| [uv](https://docs.astral.sh/uv/) | Python dependencies, `uv.lock`, virtual environments |
| [Ruff](https://docs.astral.sh/ruff/) | Python lint, gated in CI |
| [pytest](https://docs.pytest.org/) | Python tests, `fail_under = 65` |
| ESLint, Prettier | Frontend lint and format, both gated in CI |
| [Vitest](https://vitest.dev/) | Frontend tests, coverage collected but no thresholds |

See [TESTING.md](TESTING.md) for suite state and
[CONTRIBUTING.md](../CONTRIBUTING.md) for the static-verification rules that apply instead
of running them locally.
