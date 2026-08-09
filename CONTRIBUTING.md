# Contributing to Peach 1UP

## Quick start

1. **Clone and run**, follow [Getting Started](docs/docs/getting-started/index.md) to get the dev server running (`start.bat`; Windows-only, see [Technology Stack](docs/docs/contributor-guide/tech-stack.mdx)). The script creates the virtual environment, installs dependencies, generates the typed API client, and starts every service.
2. **Branch**, create a feature branch off `main`: `git checkout -b feat/your-topic`.
3. **Verify statically**, type-check and lint before committing (see [Static verification](#static-verification)).
4. **Commit**, follow the [commit format](#commit-format) below.
5. **Open a PR** against `main`.

## Static verification

Never run the test suite (`pytest`, `vitest`, or any harness) or install/remove packages as part of a contribution. Verify correctness by reading the code, tracing call sites, and checking logic by inspection.

**TypeScript type check:**

```bash
cd frontend && npx tsc --noEmit
```

**Frontend lint and format check:**

```bash
cd frontend && npm run lint && npm run format:check
```

**Python linting** (Ruff is installed by `uv sync --group dev`; config lives under
`[tool.ruff]` in [`pyproject.toml`](pyproject.toml)):

```bash
uv run ruff check backend
```

## Commit format

```
<type>(<scope>): <summary under 72 chars>

[optional body, what changed and why, not how]
[optional footer, breaking changes, refs]
```

**Types:** `feat` · `fix` · `chore` · `docs` · `refactor` · `test` · `safety`

**Scopes:** use the area of the project being changed. The scopes in active use are:

| Group | Scopes |
|---|---|
| Domains | `software` · `games` · `media` · `apps` · `environments` · `profiles` · `tags` · `users` · `links` |
| Launch and isolation | `launch` · `launches` · `sandbox` · `emulators` · `dosbox` · `86box` · `xemu` · `rpcs3` |
| Ingest and detection | `uploads` · `detection` · `hashing` · `metadata` |
| Platform and infra | `api` · `auth` · `backend` · `frontend` · `ui` · `config` · `settings` · `jobs` · `system` · `build` · `ci` · `vendor` · `docs` · `tests` |

`library` and `platforms` are pre-v2 scope names, superseded by `software`/`games` and
`environments` respectively. Do not use them for new commits.

**Rules:**

- Present tense: `add`, not `added`
- No vague summaries: `fix bug`, `update`, `misc` are not acceptable
- One logical change per commit, do not bundle unrelated changes
- If a commit touches a roadmap task, append the task ID: `feat(api): add upload endpoint [P4-3]`

**Examples:**

```
feat(library): add folder upload with per-file size cap
fix(sandbox): abort launch if Job Object creation fails
docs(contributing): add static verification guidance
safety(api): reject emulator path overrides from request input
```

## Code style

- **Python**, PEP 8 enforced via Ruff; no hardcoded paths or secrets; runtime settings live in the `settings` DB table, secrets in `.env`
- **TypeScript**, ESLint + Prettier; avoid `any`; use the generated API client in `shared/types.ts`
- Generated files (`shared/types.ts`, `shared/openapi.json`, `backend/constants_generated.py`, `frontend/src/generated/constants.ts`) are produced by `scripts/gen_constants.py` and `scripts/export_and_build_types.py`. Regenerate rather than hand-editing them
- Never accept user input into emulator binary paths at launch time, no exceptions
- All media passed to emulators must be mounted read-only

## What not to do

- Never force-push or rewrite history on `main` without explicit owner confirmation
- Never install, update, or remove packages as part of a contribution, if a dependency is missing, stop and report it
- Never commit `.env`, OS images, ROM files, BIOS files, or user-supplied binaries
- Never edit [`dev_docs/SCOPE.md`](dev_docs/SCOPE.md), [`dev_docs/CLAUDE.md`](dev_docs/CLAUDE.md), or [`dev_docs/DECISIONS.md`](dev_docs/DECISIONS.md), these are maintainer-managed files
- Never commit generated output as a hand-edited change, regenerate it instead

## Security

Report security vulnerabilities privately rather than opening a public issue. See [Security Architecture](docs/docs/contributor-guide/security.mdx) for the threat model and contact information.
