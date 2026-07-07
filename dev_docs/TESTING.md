# Peach 1UP — Testing State

Discovery-grounded snapshot of the test suite as it exists today. Describes
what is actually present and run, not an aspirational target. Cross-references
the "hard rules" in `dev_docs/CLAUDE.md` (never run suites in-sandbox, static
verification only) and the security-sensitive surface in `SECURITY.md`.

---

## 1. Suites that exist

| Layer | Runner | Config | Files | Cases |
| --- | --- | --- | --- | --- |
| Backend | pytest | `pyproject.toml` (`[tool.pytest.ini_options]`, `testpaths=["backend/tests"]`) | 35 `test_*.py` | ~421 `test_` functions |
| Frontend | Vitest (jsdom) | `frontend/vitest.config.ts` | 31 `*.test.{ts,tsx}` | co-located with source + `*.acceptance.test.tsx` |
| E2E smoke | Playwright | `playwright/playwright.config.js` | 4 `*.spec.js` | serial, `workers: 1` |

**Coverage thresholds are declared but not CI-enforced:**
- Backend: `pyproject.toml` `[tool.coverage.report] fail_under = 65`, but only
  applies when run manually as `pytest --cov=backend --cov-report=term-missing`
  (requires `pytest-cov`, which is not a committed dependency).
- Frontend: `vitest.config.ts` thresholds — lines/functions/statements 65,
  branches 60. Enforced only on a local `vitest --coverage` run.
- Playwright: no coverage; smoke assertions only.

---

## 2. What is tested

**Backend (`backend/tests/`)** — security-sensitive areas are the best-covered:

- **Auth / session / identity:** `test_auth_dependencies`, `test_identity`,
  `test_pin_auth`, `test_owner_guard`, `test_rate_limit`.
- **HTTP security middleware:** `test_security_middleware` — CSRF double-submit
  cookie (match/mismatch/absent/empty cases) and CORS/localhost-origin handling.
- **Confirmation tokens (destructive-op gate):** `test_confirmation_tokens`.
- **Process isolation / sandbox:** `test_sandbox` — Job Object era-limit load,
  pre-create checks, lifecycle, and a real-process assignment
  (`test_manual_launch_under_job_object_real_process`).
- **Path handling:** `test_normalise_path`, `test_disk_utils`, `test_drive_utils`.
- **Upload/ingest:** `test_upload`, `test_folder_ingest`.
- **Detection:** `test_iso_detect`, `test_xbox_image`.
- **Launch flow:** `test_launch_guards`, `test_launch_error_detection`,
  `test_process_registry`, `test_prepare_config`.
- **Domain/data:** `test_library_items`, `test_library_scan`, `test_enrich`,
  `test_era_defaults`, `test_emulator_catalog`, `test_health_storage`,
  `test_platforms_routes`, `test_bios_placement`, `test_bios_routes`,
  `test_backend_router`, `test_schema_migrations`, `test_startup_cleanup`,
  `test_fat_writer`, `test_dosbox_autoexec`, `test_dosbox_chs_geometry`,
  `test_drive_hydration`.

**Frontend (`frontend/src/`)** — UI primitives + page acceptance:
- Primitives: `Button`, `Input`, `Textarea`, `FormField`, `Modal`,
  `PageHeader`, `StatusBadge`.
- Hooks: `useConfirmToken`, `useLaunch`, `useLibraryScan`.
- API client: `client.test.ts` (`credentials: 'include'` singleton behaviour).
- Pages/components: `Emulators`, `Library`, `Tags` (each with `.test` +
  `.acceptance.test`), `Settings/LaunchProfiles`, `OwnerBroken`, `UserSwitcher`,
  `LaunchHistory`, `TagChips`, `EraSelector`, `ConfirmModal`, etc.

**Playwright smoke (`playwright/tests/`):** `first-run`, `login-switch`,
`add-media-launch`, `multi-disc-launch` — full-stack happy paths requiring a
live backend (`:8000`) + frontend (`:5173`), started manually.

---

## 3. What is NOT tested (gaps)

- **CI: none.** No `.github/`, no pre-commit, no husky (confirmed;
  matches SECURITY.md "No CI, pre-commit, or husky config exists anywhere").
  Every threshold in §1 is opt-in on a developer's machine.
- **`environments.py` platform status strings** — the
  `healthy/degraded/unconfigured/error/ok/missing` producer
  (`environments.py:88–112`) has no dedicated `test_environments`;
  `test_platforms_routes` exercises routes but the status-string vocabulary
  itself is not directly asserted. These are untyped bare strings (TYPES.md §3),
  so a rename would not fail any type check *or* test.
- **AppContainer / `sandbox_host.exe` delegation** — `test_sandbox` covers the
  Job Object layer, but the native `sandbox_host.exe` path
  (`SECURITY_CAPABILITIES`, `CREATE_SUSPENDED`, `ResumeThread`) is a compiled
  binary and is not covered by any Python test. AppContainer smoke/test-matrix
  validation is manual per emulator (SECURITY.md § AppContainer not yet
  validated; SCOPE.md P9-6).
- **Platform image-path traversal gap** — intentionally *not* validated
  (`base_image_path`/`working_image_path` may point anywhere; SECURITY.md Known
  Gaps). No test asserts this behaviour either way; it is a documented,
  accepted tradeoff rather than tested enforcement.
- **DB Literal enforcement** — there is no test that a bad `media_type`/`era`
  string is rejected at persist time, because the DB does not reject it
  (TYPES.md §6). The known `media_type_from_path` → `bin/gdi/cdi/rom` drift is
  not guarded by a test.
- **TheGamesDB proxy responses** — untyped end-to-end (no OpenAPI schema per
  TYPES_AUDIT.md §3); no contract test.
- **Type-generation freshness** — no test/CI asserts that `constants_generated.*`
  and `shared/types.ts` are regenerated together. The only mechanical guard is
  `_check_router_parity()` in `export_and_build_types.py`, which catches
  missing routers at export time — not stale enums.

---

## 4. Current verification practices (as they show up in code/docs)

- **Static verification is the mandated default** (CLAUDE.md hard rules):
  Claude Code must **never** run pytest/vitest/any suite in-sandbox, never
  install/update packages, and must verify by reading code and tracing call
  sites. Live runs are handed to Ryan to execute manually.
- **Playwright is explicitly a manual, pre-req-gated smoke suite** — its config
  header documents the required boot sequence (`npm install`,
  `npx playwright install chromium`, start backend, start frontend). Not part of
  any automated gate.
- **Regeneration/build discipline is convention-enforced** — `gen_constants.py`
  before export, `export_and_build_types.py` to refresh `openapi.json`/`types.ts`;
  the router-parity check is the single loud failure in that chain.
- **Commit hygiene** substitutes for CI: one logical change per commit,
  `<type>(<scope>)` messages, `test`/`safety` commit types reserved for test and
  fail-safe changes (CLAUDE.md § Commit Message Format).

---

## 5. Gap vs. the CLAUDE.md testing tier

CLAUDE.md's hard rules describe a **static-verification tier** (read, trace,
inspect; defer live runs to the operator), not a continuously-gated tier. The
current state is consistent with that tier — but the delta to a
"mechanically-enforced" tier is:

1. **No automated gate** binds the declared 65% coverage floors (backend +
   frontend) or the Playwright smoke suite to any commit/PR. All are manual.
2. **Untyped producers are untested** — platform status strings, launch
   `target_type`, and the `media_type_from_path` vocabulary have neither type
   nor test coverage, so drift there is silent until a read-time failure.
3. **Native isolation path is untestable in-suite** — `sandbox_host.exe` /
   AppContainer relies on a manual test matrix; there is no in-repo harness for
   it.

None of these are regressions; they are the expected shape of a
household-first, static-verification project with CI deferred to a later phase
(TECH.md "CI/CD pipeline planned (P7)").

---

## Flags (security / resource)

- **Security-sensitive coverage is actually strong** at the HTTP boundary:
  CSRF, CORS, PIN/Argon2 auth, owner guard, rate limiter, confirmation tokens,
  and Job Object isolation all have dedicated backend tests.
- **The two untested security surfaces are both documented-and-accepted**, not
  oversights: the platform image-path traversal gap (intentional) and the
  native `sandbox_host.exe`/AppContainer path (manual test matrix, P9).
- **No CI means the declared coverage floors are advisory only** — a commit can
  reduce coverage or skip type regeneration with nothing blocking it. This is
  the single highest-leverage gap if/when the P7 CI work lands.
