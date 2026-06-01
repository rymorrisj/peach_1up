# Peach 1UP — Technology Stack

Peach 1UP is a preservation automation tool. The stack was chosen to maximise
community accessibility, developer familiarity, and long-term maintainability
as an open source project.

---

## Infrastructure

PyInstaller compiles the Python backend to a standalone executable. React builds to static files served by FastAPI. pystray provides a system tray icon. Windows installer via NSIS/WiX, Linux via deb/AppImage. GitHub Actions handles release builds. P7.

## Platform

**Linux-first.**

The application runs natively on Linux and Windows. Emulators run natively on the host OS regardless of platform. This keeps a single clean codebase without platform-specific application code paths.

_Note:_ The Alpha build will be tested and run specifically on Windows 10/11 first. Linux support will be added for the Beta.

## Database

**SQLite via SQLModel, create_all() on startup.**

Read-heavy usage pattern makes SQLite sufficient. SQLAlchemy abstraction means
Postgres is a future config change not a rewrite.

## Backend

**Python 3.11, FastAPI, Pydantic, python-dotenv, PyYAML.**

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

- **DOSBox-X** — DOS, Windows 3.1. No ROM required.
- **86Box** — Windows 95, 98 accuracy mode. User supplies ROM pack.

### Limitations

DOSBox-X: DOS game sound requires HDD image install flow — games that write their sound config to the install directory (e.g. Doom DEFAULT.CFG) will have no in-game sound when launched directly from a read-only ISO. Sound works correctly once the game is installed to a writable HDD image via the install flow. Direct ISO launch is intentionally read-only and cannot persist game config. No code change required — this is expected behaviour.

## Emulators (Console)

- DuckStation — PS1
- PCSX2 — PS2
- xemu — Xbox OG
- Mesen — NES
- Project64 — N64
- Flycast - Dreamcast

## Process Isolation

**cgroups and network namespaces on Linux. Windows Job Objects as host fallback on Windows.**

Network blocking enforced at the process level on every emulator launch.
Linux-first architecture makes cgroups the correct primitive. Job Objects
retained as the Windows host fallback for direct emulator launches.

## Documentation

**Docusaurus.**

React-based, versioned, MDX, full-text search. Chosen for consistency with the
frontend stack and suitability for a growing open source project expecting
community contributors.

## Developer Tooling

- Ruff — Python linting
- pytest — Python testing
- ESLint and Prettier — Frontend linting and formatting
- Vitest — Frontend testing
