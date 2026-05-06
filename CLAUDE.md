# Project: Peach 1UP

## Repo name: peach_1up

## Committed Branch: main

## Plan doc: CONTEXT.md

## Decision log: DECISIONS.md

## Project Overview

Preservation automation tool. Point at a disk image, select an era, and the
correct emulator launches with media mounted and sensible defaults applied —
no manual emulator configuration required. Covers PC platforms from DOS
through Windows XP and first-generation consoles (PS1, PS2, Xbox OG, NES,
N64). Process isolation uses cgroups and namespaces on Linux, and Windows Job
Objects on Windows. Primary install is Docker Compose; start.bat provided as
a fallback for Windows users who cannot run Docker.

## Stack

**Backend / API**
- Python 3.11
- FastAPI (REST API, OpenAPI spec auto-generated)
- Pydantic (validation), PyYAML (profiles and config), python-dotenv (env vars)
- SQLite via SQLAlchemy ORM with Alembic migrations

**Frontend**
- React, TypeScript, Vite
- TanStack Query (data fetching), Zustand (state), React Router
- Tailwind CSS, shadcn/ui

**Documentation**
- Docusaurus

**PC Emulators**
- DOSBox-X (DOS and Windows 3.1 — no ROM required)
- VirtualBox (Windows 95, 98, XP — primary virtualization layer)
- 86Box (Windows 95, 98 accuracy mode — user supplies ROM pack)

**Console Emulators**
- DuckStation (PS1), PCSX2 (PS2), xemu (Xbox OG)
- Mesen (NES), Project64 (N64)

**Process Isolation**
- cgroups and network namespaces (Linux)
- Windows Job Objects (Windows host fallback)

## Era → Backend Mapping

| Era         | Primary    | Fallback                            | ROM Required |
| ----------- | ---------- | ----------------------------------- | ------------ |
| DOS         | DOSBox-X   | —                                   | No           |
| Windows 3.1 | DOSBox-X   | —                                   | No           |
| Windows 95  | VirtualBox | DOSBox-X (compat), 86Box (accuracy) | 86Box only   |
| Windows 98  | VirtualBox | DOSBox-X (compat), 86Box (accuracy) | 86Box only   |
| Windows XP  | VirtualBox | —                                   | No           |
| PS1         | DuckStation | —                                  | Yes (PS1 BIOS) |
| PS2         | PCSX2       | —                                  | Yes (PS2 BIOS) |
| Xbox OG     | xemu        | —                                  | Yes (Xbox BIOS) |
| NES         | Mesen       | —                                  | No             |
| N64         | Project64   | —                                  | No             |

## Folder Structure

peach-1up/
├── launcher.py # TUI entry point
├── CLAUDE.md
├── CONTEXT.md
├── DECISIONS.md
├── README.md
├── .env # never committed
├── config/
│ ├── settings.yaml # paths to binaries, images, display config
│ ├── eras.yaml # era → backend mapping and defaults
│ ├── platforms.yaml # registered OS platforms
│ └── known_titles.yaml # community database of titles with hardware requirements
├── profiles/ # one .yaml per game
├── backends/
│ ├── dosbox.py # DOSBox-X container logic
│ ├── box86.py # 86Box container logic
│ └── virtualbox.py # VirtualBox backend
├── utils/
│ ├── media_detect.py # sniff .iso/.img/.cue to suggest era
│ └── profile_builder.py # create/edit game profiles
├── images/ # user-supplied OS base images (never committed)
│ ├── README.md # guidance and official links
│ ├── os/ # OS platform images (base and working copies)
│ │ ├── dos/
│ │ ├── win31/
│ │ ├── win95/
│ │ ├── win98/
│ │ └── winxp/
│ ├── hdd/ # DOS per-game HDD images
│ └── roms/
│ └── 86box/ # 86Box ROM pack
└── tests/

## Key Rules

- Never hardcode paths, secrets, or platform assumptions — use .env and settings.yaml
- Never commit .env, OS images, ROM files, or any user-supplied binaries
- One task at a time — verify it works before moving to the next
- Commit after every working feature with a meaningful message
- Always focus on CURRENT task in CONTEXT.md unless explicitly told otherwise
- Do not jump ahead to NEXT tasks without confirmation
- If completing CURRENT requires touching NEXT, flag it and ask before proceeding
- Never edit CONTEXT.md, CLAUDE.md, or DECISIONS.md — managed by user only
- CRITICAL: Emulators run natively on the host OS under process isolation — never inside application containers
- CRITICAL: Network access must be blocked at the process isolation level for every emulator launch (network namespaces on Linux, Job Objects on Windows)
- CRITICAL: Never attempt to write to or overwrite a mounted image — always read-only
- CRITICAL: Any file delete, overwrite, git operation, or destructive action requires
  explicit user confirmation before proceeding — no exceptions

## Safety Rules

- Fail loudly on every error — surface the message to the user, never swallow exceptions
- Never proceed after a warning or error without user confirmation
- If an emulator or application container fails to start cleanly, abort and report — do not retry automatically
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
- If a task seems parallelizable, still run it sequentially to avoid race conditions or conflicting state
- Do not use multi-agent workflows unless explicitly requested

## Known Gotchas

- 86Box requires a ROM pack to function. If ROMs are missing, fail gracefully
  with the official ROM pack link, do not attempt to launch with missing ROMs.
- game profile .yaml files are user-editable — validate them on load and fail
  clearly if required fields are missing or malformed.
- Emulators run natively on the host OS. On Linux, isolation is via cgroups
  and network namespaces. On Windows, isolation is via Job Objects.
  Never run emulators inside application containers.
- Read-only mount must be explicitly enforced for every media file passed to
  an emulator. Never pass a writable path.
- DOS profiles remain standalone with per-game HDD images. Win95/98/XP use the
  OSPlatform model with a locked base image and a working copy — two image copies
  per platform will be stored on disk.

## Official Download Links

- DOSBox-X: https://dosbox-x.com
- 86Box: https://86box.net
- 86Box ROM pack: https://github.com/86Box/roms
- VirtualBox: https://www.virtualbox.org
- DuckStation: https://www.duckstation.org
- PCSX2: https://pcsx2.net
- xemu: https://xemu.app
- Mesen: https://www.mesen.ca
- Project64: https://www.pj64-emu.com

## Environment Variables (.env)

Binary paths and runtime configuration live in `config/settings.yaml`. The
`.env` file is a legacy override only — values present in `.env` take
precedence over `settings.yaml` but are not required for a standard install.
`.env` is reserved for secrets and machine-specific overrides that should not
be committed.

Supported legacy overrides (also accepted in settings.yaml):
- DOSBOX_PATH — path to dosbox-x.exe
- BOX86_PATH — path to 86Box.exe
- VIRTUALBOX_PATH — path to VBoxManage.exe
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

- tui — Textual interface (legacy)
- dosbox — DOSBox-X backend
- 86box — 86Box backend
- virtualbox — VirtualBox backend
- profiles — game profile system
- detection — media or system detection logic
- config — settings, .env, yaml files
- settings — settings.yaml and config migration
- launcher — main entry point
- frontend — React/TypeScript frontend
- docs — CLAUDE.md, CONTEXT.md, DECISIONS.md, README

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

## Build Phases

- P0 — Bare minimum working launcher (see CONTEXT.md)
- P1 — Core usability
- P2 — Meaningful expansion
- P3 — Maturity and automation
- P3.5 — Web UI replacing TUI, FastAPI backend, React frontend, Docker Compose primary install
- P4 — Console backends (PS1, PS2, Xbox OG, NES, N64)
- PX — Nice to haves, no timeline
