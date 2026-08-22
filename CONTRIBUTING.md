# Contributing

Peach 1UP is a solo project today. There is no review rotation and no release cadence, so
treat this as "how to send a change that can actually be merged" rather than a process.

## Quick start

```bash
# 1. Install and run
uv sync --group dev
start.bat

# 2. Branch
git checkout -b feat/your-topic
```

Windows only. There is no Linux dev path and there will not be one.

## Verify statically

**Never run the test suite (`pytest`, `vitest`, or any harness) and never install, update,
or remove packages as part of a contribution.** Verify correctness by reading the code and
tracing call sites. If a dependency looks missing, stop and say so rather than routing
around it.

```bash
# TypeScript
cd frontend && npx tsc --noEmit

# Frontend lint and format
cd frontend && npm run lint && npm run format:check

# Python lint
uv run ruff check backend
```

CI runs the suites on every push and pull request to `main`: Ruff plus `pytest --cov` on
Windows, ESLint, Prettier, a production build, `vitest run --coverage`, and a packaging
smoke test that builds with PyInstaller and asserts the frozen exe serves
`/api/openapi.json`.

## Commit format

```
<type>(<scope>): <summary under 72 chars>

[optional body: what changed and why, not how]
[optional footer: breaking changes, refs]
```

**Types:** `feat` · `fix` · `chore` · `docs` · `refactor` · `test` · `safety`

**Scopes** name the area being changed. The ones in active use:

| Group | Scopes |
|---|---|
| Domains | `software` · `games` · `media` · `apps` · `environments` · `profiles` · `tags` · `users` · `links` |
| Launch and isolation | `launch` · `launches` · `sandbox` · `emulators` · `dosbox` · `86box` · `xemu` · `rpcs3` |
| Ingest and detection | `uploads` · `detection` · `hashing` · `metadata` |
| Platform and infra | `api` · `auth` · `backend` · `frontend` · `ui` · `config` · `settings` · `jobs` · `system` · `build` · `ci` · `vendor` · `docs` · `tests` |

`library` and `platforms` are pre-v2 names, superseded by `software`/`games` and
`environments`. Do not use them for new commits.

**Rules**

- Present tense: `add`, not `added`
- No vague summaries. `fix bug`, `update`, and `misc` are not acceptable
- One logical change per commit. Do not bundle unrelated work

**Examples**

```
feat(uploads): add folder upload with per-file size cap
fix(sandbox): abort launch if Job Object creation fails
safety(api): reject emulator path overrides from request input
docs(security): correct AppContainer status table
```

## Code style

| Area | Rules |
|---|---|
| Python | PEP 8 via Ruff. No hardcoded paths or secrets: runtime settings go in the `settings` DB table, secrets in `.env` |
| TypeScript | ESLint and Prettier. Avoid `any`. Use the generated client in `shared/types.ts` |
| Generated files | `shared/types.ts`, `shared/openapi.json`, `backend/constants_generated.py`, and `frontend/src/generated/constants.ts` come from `scripts/gen_constants.py` and `scripts/export_and_build_types.py`. Regenerate; never hand-edit |
| Comments | Explain why, not what. Skip the ones that restate the line below them |

## Hard rules

These are not style preferences. A change that breaks one of them is not mergeable.

- **Never accept user input into an emulator binary path.** No exceptions. See
  [SECURITY.md](dev_docs/SECURITY.md) § Input validation.
- **All media passed to an emulator is mounted read-only.**
- **Never add an unsandboxed launch fallback.** If Job Object creation or assignment fails,
  the launch aborts.
- **Fail loud.** Surface the error. Do not swallow an exception to keep a flow moving.
- **Never commit** `.env`, OS images, ROM files, BIOS files, or any user-supplied binary.
- **Never force-push or rewrite history on `main`** without explicit owner confirmation.
- `dev_docs/SCOPE.md` and `dev_docs/CLAUDE.md` are maintainer-managed. Do not edit them.

Before writing code that touches auth, path handling, subprocess spawning, launch flows,
disk image operations, settings, destructive operations, network binding, or secrets:
read [SECURITY.md](dev_docs/SECURITY.md) first. If an approach requires working around a
rule in it, stop and raise it instead.

## Pull requests

- Target `main`.
- Say what changed and why. Link the relevant `dev_docs/` section if the change contradicts
  something written there, and update that document in the same PR.
- If your change makes a documented claim false, fixing the document is part of the change.

## Security

Report vulnerabilities **privately** via
[GitHub Security Advisories](https://github.com/rymorrisj/peach_1up/security/advisories),
not a public issue. See [SECURITY.md](dev_docs/SECURITY.md) for the threat model.
