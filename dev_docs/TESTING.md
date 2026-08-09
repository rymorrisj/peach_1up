# Peach 1UP: Testing State

Discovery-grounded snapshot of the test suite as it exists today. Describes what is
actually present and run, not an aspirational target. Cross-references the hard rules in
`dev_docs/CLAUDE.md` (never run suites in-sandbox, static verification only) and the
security-sensitive surface in [SECURITY.md](SECURITY.md).

---

## 1. Suites that exist

| Layer | Runner | Config | Files | Cases |
| --- | --- | --- | --- | --- |
| Backend | pytest | [`pyproject.toml`](../pyproject.toml) (`[tool.pytest.ini_options]`, `testpaths=["backend/tests"]`) | 55 `test_*.py` | 761 `test_` functions |
| Frontend | Vitest (jsdom) | [`frontend/vitest.config.ts`](../frontend/vitest.config.ts) | 52 `*.test.{ts,tsx}` | co-located with source, plus `*.acceptance.test.tsx` (3) |

**Coverage thresholds are declared and now run in CI:**
- Backend: `pyproject.toml` `[tool.coverage.report] fail_under = 65`. `pytest-cov`
  **is** a committed dev dependency (`pyproject.toml`'s `[dependency-groups] dev`,
  `pytest-cov==7.1.0`, installed by `uv sync --group dev`), and CI runs
  `pytest --cov=backend --cov-report=term-missing` on `windows-latest`
  ([`.github/workflows/test.yml`](../.github/workflows/test.yml)).
- Frontend: `vitest.config.ts` thresholds are lines/functions/statements 65, branches 60.
  CI runs `vitest run --coverage`.

---

## 2. What is tested

**Backend ([`backend/tests/`](../backend/tests/))**, security-sensitive areas are the best-covered:

- **Auth / session / identity:** `test_auth_dependencies`, `test_identity`,
  `test_pin_auth`, `test_owner_guard`, `test_rate_limit`.
- **HTTP security middleware:** `test_security_middleware`, covering CSRF double-submit
  cookie (match/mismatch/absent/empty cases) and CORS/localhost-origin handling.
- **Confirmation tokens (destructive-op gate):** `test_confirmation_tokens`.
- **Process isolation / sandbox:** `test_sandbox`, covering Job Object era-limit load,
  pre-create checks, lifecycle, and a real-process assignment
  (`test_manual_launch_under_job_object_real_process`).
- **Path handling:** `test_normalise_path`, `test_disk_utils`, `test_drive_utils`.
- **Upload/ingest:** `test_upload`, `test_folder_ingest`.
- **Detection:** `test_xbox_image`, `test_ps3`, `test_xex`, `test_media_target`
  ([`backend/service/utils/detection/`](../backend/service/utils/detection/), the
  Peach 1UP-specific PS3/Xbox 360 launch-target resolution and Xbox optical-image
  identification retained after the formatscout extraction, not format detection
  itself). Format and platform detection (ISO, CHD, bin/cue, magic-byte, hashing) is
  covered by the vendored [`formatscout`](../services/vendor/formatscout/) package's own
  `tests/`, not by `backend/tests/`.
- **Launch flow:** `test_launch_guards`, `test_launch_error_detection`,
  `test_process_registry`, `test_prepare_config`.
- **Domain/data:** `test_game_items`, `test_game_scan`, `test_enrich`,
  `test_era_defaults`, `test_emulator_catalog`, `test_health_storage`,
  `test_environments_routes`, `test_game_item_bundles_routes`,
  `test_game_item_bundles_gaps_routes`, `test_game_items_leaf_routes`,
  `test_launches_routes`, `test_media`, `test_controllers`,
  `test_dependencies_content_rating`, `test_users_create_delete_reset`,
  `test_bios_placement`, `test_bios_routes`,
  `test_backend_router`, `test_schema_migrations`, `test_startup_cleanup`,
  `test_fat_writer`, `test_dosbox_autoexec`, `test_dosbox_chs_geometry`,
  `test_drive_hydration`, `test_apps_routes`, `test_asset_fetch`,
  `test_drives_routes`, `test_emulators_routes`, `test_game_metadata_routes`,
  `test_profiles_routes`, `test_restrictions_routes`, `test_rom_pack`,
  `test_settings_routes`, `test_tags`.
  Tier-1 coverage for `core/dependencies.py`, `users.py`, `game_item_bundles.py`, and
  `launches.py` is implemented, via `test_auth_dependencies` /
  `test_dependencies_content_rating`, `test_users_create_delete_reset`,
  `test_game_item_bundles_routes`, and `test_launches_routes` respectively. (The planning
  doc this was tracked in, `dev_docs/v2/09_test_coverage.md`, no longer exists; the
  `dev_docs/v2/` directory was removed.)

**Frontend (`frontend/src/`)**, UI primitives plus page acceptance:
- Primitives: `Button`, `Input`, `Textarea`, `FormField`, `Modal`,
  `PageHeader`, `StatusBadge`.
- Hooks: `useConfirmToken`, `useLaunch`, `useLibraryScan`.
- API client: `client.test.ts` (`credentials: 'include'` singleton behaviour).
- Pages/components: `Emulators`, `Software`, `Tags` (each with `.test` +
  `.acceptance.test`), `Emulators/Profiles`, `OwnerBroken`, `UserSwitcher`,
  `LaunchHistory`, `TagChips`, `EraSelector`, `ConfirmModal`, `TabbedLayout`,
  `Profiles`/`Bios`/`RomPacks` tabs, `EmulatorDetail`, plus the v2 route-redirect
  tests (`test/routing.sectionRedirects.test.tsx`).

---

## 3. What is NOT tested (gaps)

- **CI: present but partial.** `.github/workflows/test.yml` now runs pytest
  (`--cov`) on `windows-latest`, vitest (`--coverage`), and type generation on
  every push/PR to `main`. There is still **no pre-commit or husky** hook, and
  the type-generation job uploads regenerated files as artifacts rather than
  diffing them against the committed copies, so a stale committed generated file
  is not yet mechanically failed.
- **`environments.py` environment status strings.** The
  `healthy/degraded/unconfigured/error/ok/missing/unknown` producer has
  `test_environments_routes` exercising the routes, but the status-string
  vocabulary itself is not directly asserted. The values are now the generated
  `EnvironmentStatus` Literal at the Pydantic layer (TYPES.md §3), though the DB
  column remains a bare `String`.
- **AppContainer / `sandbox_host.exe` delegation.** `test_sandbox` covers the
  Job Object layer, but the native `sandbox_host.exe` path
  (`SECURITY_CAPABILITIES`, `CREATE_SUSPENDED`, `ResumeThread`) is a compiled
  binary and is not covered by any Python test. AppContainer smoke/test-matrix
  validation is manual per emulator (SECURITY.md § AppContainer not yet
  validated; SCOPE.md P9-6).
  - The moniker to test against is `Peach1UP.<slug>.<scope>`. Confirmed real
    examples: `Peach1UP.duckstation.shared`, `Peach1UP.mesen.shared`. `<slug>`
    matches the emulator catalog's `slug` field (check the emulator's TOML
    descriptor under `config/emulators/` if unsure). `<scope>` is `shared` for
    the non-per-item container; a per-item-id scope variant also exists,
    using the decimal `user_item_id` in place of `shared` (e.g.
    `Peach1UP.duckstation.42`).
- **Environment image-path traversal gap.** Intentionally *not* validated
  (`base_image_path`/`working_image_path` may point anywhere; SECURITY.md Known
  Gaps). No test asserts this behaviour either way; it is a documented,
  accepted tradeoff rather than tested enforcement.
- **DB Literal enforcement.** There is no test that a bad `file_type`/`era`
  string is rejected at persist time, because the DB does not reject it
  (TYPES.md §6). The old `media_type_from_path` → `bin/gdi/cdi/rom` drift is now
  resolved in code (`file_type_from_path` self-validates against `FileType`), but the
  structural gap, a producer bypassing that helper and writing to a bare `String` column,
  is still not guarded by a test.
- **TheGamesDB proxy responses.** Untyped end-to-end (no OpenAPI schema); no contract
  test.
- **Type-generation freshness.** No test or CI job asserts that `constants_generated.*`
  and `shared/types.ts` are regenerated together. The only mechanical guard is
  `_check_router_parity()` in
  [`export_and_build_types.py`](../scripts/export_and_build_types.py), which catches
  missing routers at export time, not stale enums.

### Known issue: two v2 navigation tests skipped (test-runner hang)

Two frontend tests are currently `it.skip`ped because they hang the Vitest
runner, not because of a real application bug (investigated on 2026-07-11; the
test bodies themselves pass, but the process never advances past RUNNING, a
leaked-async-handle signature whose source was not pinned down, and the hang
point is not even consistent between runs). Read the `KNOWN ISSUE` comment
blocks directly above each skip for the full investigation notes:

- `frontend/src/components/layout/TabbedLayout.test.tsx`,
  *"derives the active tab from the URL, not from independent internal state"*.
- `frontend/src/test/routing.sectionRedirects.test.tsx`,
  *"/emulators/:slug still resolves to EmulatorDetail for a real (non-reserved)
  slug"* (part of the `describe.skip` blocks in that file).

Both carry a `TODO: re-enable once root cause is found and fixed`. This is
tracked technical debt to revisit post-alpha; do not treat these skips as an
application defect.

---

## 4. Current verification practices (as they show up in code/docs)

- **Static verification is the mandated default** (CLAUDE.md hard rules): never run
  pytest/vitest or any suite in-sandbox, never install or update packages, and verify by
  reading code and tracing call sites. Live runs are handed to the maintainer to execute
  manually. The same rules are stated for outside contributors in
  [CONTRIBUTING.md](../CONTRIBUTING.md) § Static verification.
- **Regeneration/build discipline is convention-enforced:** `gen_constants.py` before
  export, `export_and_build_types.py` to refresh `openapi.json` and `types.ts`. The
  router-parity check is the single loud failure in that chain.
- **Commit hygiene** substitutes for local CI: one logical change per commit,
  `<type>(<scope>)` messages, and the `test`/`safety` commit types reserved for test and
  fail-safe changes (CLAUDE.md § Commit Message Format).

---

## 5. Gap vs. the CLAUDE.md testing tier

CLAUDE.md's hard rules describe a **static-verification tier** (read, trace, inspect,
and defer live runs to the operator), not a continuously-gated tier. The current state is
consistent with that tier. The delta to a mechanically-enforced tier is:

1. **CI now runs the suites** (`.github/workflows/test.yml`: pytest and vitest, both
   with coverage, on push/PR to `main`), but the type-generation job does not fail on a
   stale committed generated file, since it uploads artifacts instead of diffing.
2. **Some producers stay untyped and untested.** Launch `target_type`
   (`game_item_bundle`/`environment_item`) is still a bare derived string. The
   environment status vocabulary is now the `EnvironmentStatus` Literal and the
   `file_type` vocabulary is now self-validated by `file_type_from_path`, so those two
   are no longer silent-drift surfaces.
3. **The native isolation path is untestable in-suite.** `sandbox_host.exe` and
   AppContainer rely on a manual test matrix; there is no in-repo harness for it.

None of these are regressions; they are the expected shape of a household-first
project. The GitHub Actions test workflow is the first piece of a CI/CD pipeline that
was previously deferred to a later phase.

---

## Flags (security / resource)

- **Security-sensitive coverage is strong** at the HTTP boundary: CSRF, CORS,
  PIN/Argon2 auth, owner guard, rate limiter, confirmation tokens, and Job Object
  isolation all have dedicated backend tests.
- **The two untested security surfaces are both documented and accepted**, not
  oversights: the Environment image-path traversal gap (intentional) and the native
  `sandbox_host.exe`/AppContainer path (manual test matrix, P9).
- **CI runs pytest and vitest with coverage on every push/PR**, so the coverage floors
  are enforced there. The remaining gap is the type-generation freshness check, where
  artifacts are uploaded rather than diffed.
