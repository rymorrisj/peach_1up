# Project: Peach 1UP

## Repo name: peach_1up

## Committed Branch: main

## Plan doc: CONTEXT.md

## Decision log: DECISIONS.md

## Security log: SECUIRTY.md

## Tech log: TECH.md

## Emulator log: EMULATORS.md

## Project Overview

Preservation automation tool. Point at a disk image, select an era, and the
correct emulator launches with media mounted and sensible defaults applied —
no manual emulator configuration required. Covers PC platforms from DOS
through Windows XP and first-generation consoles (PS1, PS2, Xbox OG, NES,
N64, Dreamcast). Process isolation uses Windows Job Objects (Alpha). Linux
sandbox via cgroups/namespaces is planned for Beta (P8).

## Stack

**Backend / API**

- Python 3.11
- FastAPI (REST API, OpenAPI spec auto-generated)
- Pydantic (validation), PyYAML (profiles and config), python-dotenv (env vars)
- SQLite via SQLModel, create_all() on startup, no Alembic

**Frontend**

- React, TypeScript, Vite
- TanStack Query (data fetching), useReducer (state), React Router
- Tailwind CSS, Radix UI primitives (dialog, slot) with hand-rolled components

**Documentation**

- Docusaurus

**PC Emulators**

- DOSBox-X (DOS and Windows 3.1 — no ROM required)
- 86Box (Windows 95, 98, XP — user supplies ROM pack)

**Console Emulators**

- DuckStation (PS1)
- PCSX2 (PS2)
- xemu (Xbox OG)
- Mesen (NES, SNES)
- Project64 (N64)
- Flycast (Dreamcast)

**Process Isolation**

- Windows Job Objects (current — Alpha)
- cgroups and network namespaces (Linux — planned for Beta, P8)

## Era → Backend Mapping

| Era         | Primary     | Fallback | ROM Required         |
| ----------- | ----------- | -------- | -------------------- |
| DOS         | DOSBox-X    | —        | No                   |
| Windows 3.1 | DOSBox-X    | —        | No                   |
| Windows 95  | 86Box       | —        | Yes (86Box ROM pack) |
| Windows 98  | 86Box       | —        | Yes (86Box ROM pack) |
| Windows XP  | 86Box       | —        | Yes (86Box ROM pack) |
| PS1         | DuckStation | —        | Yes (PS1 BIOS)       |
| PS2         | PCSX2       | —        | Yes (PS2 BIOS)       |
| Xbox OG     | xemu        | —        | Yes (Xbox BIOS)      |
| Dreamcast   | Flycast     | —        | Yes (DC BIOS)        |
| NES         | Mesen       | —        | No                   |
| SNES        | Mesen       | —        | No                   |
| N64         | Project64   | —        | No                   |

## Folder Structure

peach_1up/
├── README.md
├── start.bat / start.sh
├── .env # never committed
├── .env.template
├── .gitignore
├── backend/
│ ├── api/
│ │ ├── middleware/
│ │ └── routes/
│ ├── core/
│ │ ├── database.py
│ │ ├── dependencies.py
│ │ ├── lifespan.py
│ │ ├── process_registry.py
│ │ └── settings.py
│ ├── models/
│ ├── service/
│ │ ├── backends/
│ │ └── utils/
│ ├── tests/
│ └── main.py
├── frontend/
│ ├── src/
│ │ ├── api/
│ │ ├── components/
│ │ ├── context/
│ │ ├── hooks/
│ │ ├── pages/
│ │ ├── styles/
│ │ └── ui/
│ └── package.json
├── config/
│ ├── templates/
│ ├── constants.yaml
│ ├── emulators.yaml
│ ├── eras.yaml
│ ├── known_titles.yaml
│ ├── platforms.yaml
│ └── settings.yaml
├── database/
│ └── data/ # peach1up.db lives here (never committed)
├── shared/
│ ├── openapi.json # auto-generated at startup
│ └── types.ts # auto-generated from openapi.json
├── docs/
├── scripts/
│ ├── export_and_build_types.py
│ ├── gen_constants.py
| ├── gen_icon.py
| ├── run_tests.py
│ └── setup_admin_user.py
├── emulators/
│ ├── 86box/
│ ├── ...
└── library/ # user-supplied, never committed
├── games/ # games/{era}/{slug}/
├── os/ # os/{era}/
├── roms/
│ └── 86box/ # 86Box ROM pack
├── bios/
│ ├── ps1/
│ ├── ps2/
│ └── xbox/
├── tools/ # tools/{slug}/
└── saves/

## Key Rules

- Never hardcode paths, secrets, or platform assumptions — use .env and settings.yaml
- Never commit .env, OS images, ROM files, or any user-supplied binaries
- One task at a time — verify it works before moving to the next
- Commit after every working feature with a meaningful message
- Always focus on CURRENT task in CONTEXT.md unless explicitly told otherwise
- Do not jump ahead to NEXT tasks without confirmation
- If completing CURRENT requires touching NEXT, flag it and ask before proceeding
- Never edit CONTEXT.md, CLAUDE.md, or DECISIONS.md — managed by user only
- CRITICAL: Emulators run natively on the host OS under process isolation
- CRITICAL: Network isolation is emulator-native — each emulator is launched with its network adapter disabled when enable_networking is false on the active profile. Never rely on host OS firewall rules or process isolation for network blocking
- CRITICAL: Never attempt to write to or overwrite a mounted image — always read-only
- CRITICAL: Any file delete, overwrite, git operation, or destructive action requires
  explicit user confirmation before proceeding — no exceptions

## Safety Rules

- Fail loudly on every error — surface the message to the user, never swallow exceptions
- Never proceed after a warning or error without user confirmation
- If an emulator fails to start cleanly, abort and report — do not retry automatically
- If media detection is uncertain, ask the user to confirm before launching
- Memory and file operations must always err toward doing nothing over doing something wrong
- All mounts inside containers are read-only unless explicitly approved

## Error Handling

When an error occurs:

1. **Stop immediately** — do not attempt auto-fixes, retries, or workarounds on your own
2. **Explain the issue concisely** — what failed, why it failed, and what the options are
3. **Wait for direction** — do not continue until I confirm how to proceed

Format error reports like this:
❌ Error: [brief description]
Cause: [what went wrong]
Options:
A) [option 1]
B) [option 2]
Awaiting your decision.

## Agent & Parallelism Rules

- Do **not** spawn parallel sub-agents or run concurrent tasks
- Execute all tasks sequentially, one step at a time
- If a task seems parallelizable, still run it sequentially to avoid race conditions or conflicting state if
  you are doing write operations as well. Parallel agents for read only
- Do not use multi-agent workflows unless explicitly requested

## Known Gotchas

- 86Box requires a ROM pack to function. If ROMs are missing, fail gracefully
  with the official ROM pack link, do not attempt to launch with missing ROMs.
- game profile .yaml files are user-editable — validate them on load and fail
  clearly if required fields are missing or malformed.
- Emulators run natively on the host OS. On Windows, isolation is via Job
  Objects (current). Linux isolation via cgroups/namespaces is planned for
  Beta (P8) — no hardened Linux sandbox exists today.
- Read-only mount must be explicitly enforced for every media file passed to
  an emulator. Never pass a writable path.
- DOS profiles remain standalone with per-game HDD images. Win95/98/XP use the
  DB-backed Platform model with a locked base image and a working copy — two image copies
  per platform will be stored on disk.
  game data files, not an ISO or image.
- `export_and_build_types.py` must include every router that `main.py` mounts. A router
  added to `main.py` but missing from `export_and_build_types.py` silently produces a stale
  OpenAPI spec and broken TypeScript types. This has been a recurring bug — always
  check both files when adding or removing routers.
- Emulator binary path keys (`DOSBOX_PATH`, `BOX86_PATH`, etc.) are intentionally
  absent from `_PATH_KEYS` in `settings.py`. These keys resolve to bundled-directory
  paths via `get_install_path()`, not stored path strings. Do not re-add them to
  `_PATH_KEYS` or `_DEFAULTS`.
- sandbox_host.exe must be compiled from backend/service/utils/sandbox/src/ before the backend
  can run. build.bat does this automatically via MSYS2 when bash is on PATH; without MSYS2 a
  pre-built binary must be present. The binary is not committed to git.

## Official Download Links

- DOSBox-X: https://dosbox-x.com
- 86Box: https://86box.net
- 86Box ROM pack: https://github.com/86Box/roms
- Flycast: https://github.com/flyinghead/flycast
- DuckStation: https://www.duckstation.org
- PCSX2: https://pcsx2.net
- xemu: https://xemu.app
- Mesen: https://www.mesen.ca
- Project64: https://www.pj64-emu.com

## Emulator Path Model

Emulator binary path resolution follows three tiers, highest priority first:

1. **User override** — absolute path stored in `settings.yaml`, set via the Emulators or Settings page in the UI. Never accepted from request input.
2. **Bundled** — portable emulators (DOSBox-X, 86Box) ship inside `emulators/{slug}/` under the project root. Presence detected by checking the known project-relative path on startup.
3. **Catalog-detected** — system-installed emulators (DuckStation, Project64) are located via known installation paths declared in `emulators.yaml`. No registry scanning.

No emulator binary path is ever accepted from request input at launch time. This rule has no exceptions.

## Environment Variables (.env)

Binary paths and runtime configuration live in `config/settings.yaml`. The
`.env` file is a legacy override only — values present in `.env` take
precedence over `settings.yaml` but are not required for a standard install.
`.env` is reserved for secrets and machine-specific overrides that should not
be committed.

Supported legacy overrides (also accepted in settings.yaml):

- DOSBOX_PATH — path to dosbox-x.exe
- BOX86_PATH — path to 86Box.exe
- ROM_PATH — path to 86Box ROM pack directory
- PROFILES_PATH — path to game profiles directory

## Git & Version Control

- Assume Git is the primary version control system
- Never force-push or rewrite history without explicit user confirmation
- Never run git commit, git push, git merge, or any destructive git operation
  without explicit user confirmation — no exceptions

### Commit Message Format

All commits must follow this structure:

<type>(<scope>): <short summary>

[optional body — what changed and why, not how]
[optional footer — breaking changes, refs]

### Type (required)

- feat — new feature or capability
- fix — bug fix
- chore — setup, config, scaffolding, dependencies
- docs — documentation only
- refactor — code change with no behaviour change
- test — adding or fixing tests
- safety — error handling, validation, fail-safe logic

### Scope (required for this project)

Use the area of the project being changed:

- dosbox — DOSBox-X backend
- 86box — 86Box backend
- profiles — game profile system
- detection — media or system detection logic
- config — settings, .env, yaml files
- settings — settings.yaml and config migration
- launcher — main entry point
- frontend — React/TypeScript frontend
- docs — CLAUDE.md, CONTEXT.md, DECISIONS.md, README
- api — FastAPI routes and API layer
- auth — authentication and session handling
- sandbox — process isolation and Job Objects
- launches — launch flow and process tracking
- library — game library management
- platforms — OS platform management
- backend — backend-wide changes

### Examples

chore(emulator): adding a new extension to bundle with the application
feat(tui): add era selector screen with keyboard navigation
fix(86box): fail gracefully when ROM path is missing
safety(launcher): abort on DISPLAY not found, show VcXsrv link
feat(profiles): add YAML save and load for game profiles
docs(decisions): log over VirtualBox decision

### Rules

- Summary line must be 72 characters or fewer
- Use present tense — "add" not "added", "fix" not "fixed"
- Never write vague messages: "fix bug", "update", "changes", "misc"
- One logical change per commit — do not bundle unrelated changes
- If a commit touches CONTEXT.md task steps, reference the step:
  feat(tui): add main menu skeleton [P0-5]

### Output Rules

- Report findings as concise summaries only. Skip internal reasoning and intermediate steps.
- Confirm each change in one line: what file, what was done.
- Do not output diffs or show file contents after changes.
- Only show code if flagging something complex, critical, or a potential issue.
- Flag anything that could pose security, safety, or systems issues such as memory leaks, unsafe code, or resource handling problems.
