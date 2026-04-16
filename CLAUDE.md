# Project: Peach 1UP

## Repo name: peach_1up

## Committed Branch: main

## Plan doc: CONTEXT.md

## Decision log: DECISIONS.md

## Project Overview

Retro game launcher and VM manager. Point at a disk image, select an era,
and a pre-configured isolated container spins up with the correct emulator,
media mounted, and sensible defaults applied. Covers DOS through Windows XP.
Runs on Windows (Home edition). Docker is the isolation layer. Built with
Python and a keyboard-driven TUI.

## Stack

- Python 3.11
- Textual (TUI framework, keyboard-driven, no mouse required at P0)
- Docker Desktop (Linux containers, networking disabled by default)
- VcXsrv (X server for GUI display forwarding from container to Windows host)
- DOSBox-X (DOS and Windows 3.1 era — no ROM required)
- 86Box (Windows 95, 98, XP era — user supplies ROM pack)
- PyYAML (game profiles and configuration)
- python-dotenv (environment configuration)

## Era → Backend Mapping

| Era         | Backend  | ROM Required |
| ----------- | -------- | ------------ |
| DOS         | DOSBox-X | No           |
| Windows 3.1 | DOSBox-X | No           |
| Windows 95  | 86Box    | Yes          |
| Windows 98  | 86Box    | Yes          |
| Windows XP  | 86Box    | Yes          |

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
│ └── eras.yaml # era → backend mapping and defaults
├── profiles/ # one .yaml per game
├── backends/
│ ├── dosbox.py # DOSBox-X container logic
│ └── box86.py # 86Box container logic
├── docker/
│ ├── dosbox/
│ │ └── Dockerfile
│ └── 86box/
│ └── Dockerfile
├── utils/
│ ├── media_detect.py # sniff .iso/.img/.cue to suggest era
│ └── profile_builder.py # create/edit game profiles
├── images/ # user-supplied OS base images (never committed)
│ └── README.md # guidance and official links
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
- CRITICAL: Docker networking must be disabled by default on every container launch
- CRITICAL: Never attempt to write to or overwrite a mounted image — always read-only
- CRITICAL: Any file delete, overwrite, git operation, or destructive action requires
  explicit user confirmation before proceeding — no exceptions

## Safety Rules

- Fail loudly on every error — surface the message to the user, never swallow exceptions
- Never proceed after a warning or error without user confirmation
- If a container fails to start cleanly, abort and report — do not retry automatically
- If media detection is uncertain, ask the user to confirm before launching
- Memory and file operations must always err toward doing nothing over doing something wrong
- All mounts inside containers are read-only unless explicitly approved

## Known Gotchas

- VcXsrv must be running on the host before any container with a GUI is launched.
  If DISPLAY is not set or VcXsrv is not detected, fail with a clear install message.
- 86Box requires a ROM pack to function. If ROMs are missing, fail gracefully with
  the official ROM pack link, do not attempt to launch with missing ROMs.
- Docker Desktop on Windows Home requires WSL2 to be enabled. Check for this on
  startup and surface a clear error if it is not present.
- Linux containers on Windows cannot access the host display natively.
  DISPLAY must be set to host.docker.internal:0.0 for VcXsrv forwarding.
- DOSBox-X and 86Box behave differently inside containers vs native.
  Always test container behaviour, not just binary behaviour.
- game profile .yaml files are user-editable — validate them on load and fail
  clearly if required fields are missing or malformed.

## Official Download Links

- Docker Desktop: https://www.docker.com/products/docker-desktop
- VcXsrv: https://sourceforge.net/projects/vcxsrv
- DOSBox-X: https://dosbox-x.com
- 86Box: https://86box.net
- 86Box ROM pack: https://github.com/86Box/roms
- Textual: https://textual.textualize.io

## Environment Variables (.env)

- DISPLAY=host.docker.internal:0.0
- DOSBOX_IMAGE=peach1up/dosbox-x:latest
- BOX86_IMAGE=peach1up/86box:latest
- ROM_PATH=./images/roms
- PROFILES_PATH=./profiles

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

- tui — Textual interface
- dosbox — DOSBox-X backend
- 86box — 86Box backend
- docker — Dockerfiles or container config
- profiles — game profile system
- detection — media or system detection logic
- config — settings, .env, yaml files
- launcher — main entry point
- docs — CLAUDE.md, CONTEXT.md, DECISIONS.md, README

### Examples

chore(docker): add initial Dockerfile for DOSBox-X container
feat(tui): add era selector screen with keyboard navigation
fix(86box): fail gracefully when ROM path is missing
safety(launcher): abort on DISPLAY not found, show VcXsrv link
feat(profiles): add YAML save and load for game profiles
docs(decisions): log Docker over VirtualBox decision

### Rules

- Summary line must be 72 characters or fewer
- Use present tense — "add" not "added", "fix" not "fixed"
- Never write vague messages: "fix bug", "update", "changes", "misc"
- One logical change per commit — do not bundle unrelated changes
- If a commit touches CONTEXT.md task steps, reference the step:
  feat(tui): add main menu skeleton [P0-5]

## Build Phases

- P0 — Bare minimum working launcher (see CONTEXT.md)
- P1 — Core usability
- P2 — Meaningful expansion
- P3 — Maturity and automation
- PX — Nice to haves, no timeline
