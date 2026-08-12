# Testing State

What the suites actually cover today, not an aspirational target. Verification in this
project is static by default: never run a suite in-sandbox, never install packages, verify
by reading code and tracing call sites. Live runs go to the maintainer.

## Suites

| Layer | Runner | Config | Files | Cases |
|---|---|---|---|---|
| Backend | pytest | [`pyproject.toml`](../pyproject.toml), `testpaths=["backend/tests"]` | 60 `test_*.py` | 839 `test_` functions |
| Frontend | Vitest (jsdom) | [`frontend/vitest.config.ts`](../frontend/vitest.config.ts) | 52 `*.test.{ts,tsx}` | co-located with source, plus 3 `*.acceptance.test.tsx` |

**Coverage:**

| Layer | Threshold | Enforced |
|---|---|---|
| Backend | `[tool.coverage.report] fail_under = 65` | Yes, `pytest --cov=backend` runs on `windows-latest` in CI |
| Frontend | None | No. `vitest run --coverage` runs in CI and collects a report, but the thresholds were dropped ahead of the v0.2.0 native pivot |

## What is covered

**Backend** ([`backend/tests/`](../backend/tests/)). Security-sensitive surfaces are the
best covered.

| Area | Files |
|---|---|
| Auth, session, identity | `test_auth_dependencies`, `test_identity`, `test_pin_auth`, `test_owner_guard`, `test_rate_limit` |
| HTTP security middleware | `test_security_middleware` (CSRF double-submit match/mismatch/absent/empty, CORS and localhost-origin handling) |
| Destructive-op gate | `test_confirmation_tokens` |
| Process isolation | `test_sandbox` (Job Object era-limit load, pre-create checks, lifecycle, and a real-process assignment) |
| Path handling | `test_normalise_path`, `test_disk_utils`, `test_drive_utils` |
| Upload and ingest | `test_upload`, `test_folder_ingest`, `test_folder_ingest_failure_paths` |
| Detection resolvers | `test_xbox_image`, `test_ps3`, `test_xex`, `test_media_target` |
| Launch flow | `test_launch_guards`, `test_launch_error_detection`, `test_evaluate_launch_readiness`, `test_process_registry`, `test_prepare_config`, `test_backend_router` |
| Parental controls | `test_dependencies_content_rating`, `test_restrictions_routes`, `test_game_item_bundles_filtering_gaps` |
| Route coverage | `test_apps_routes`, `test_bios_routes`, `test_controllers`, `test_drives_routes`, `test_emulators_routes`, `test_environments_routes`, `test_game_item_bundles_routes`, `test_game_item_bundles_gaps_routes`, `test_game_items_leaf_routes`, `test_game_metadata_routes`, `test_launches_routes`, `test_profiles_routes`, `test_settings_routes`, `test_users_create_delete_reset` |
| Domain and data | `test_game_items`, `test_game_scan`, `test_enrich`, `test_era_defaults`, `test_emulator_catalog`, `test_emulator_descriptor`, `test_health_storage`, `test_media`, `test_bios_placement`, `test_rom_pack`, `test_rpcs3_write_installed_state`, `test_schema_migrations`, `test_startup_cleanup`, `test_fat_writer`, `test_dosbox_autoexec`, `test_dosbox_chs_geometry`, `test_drive_hydration`, `test_asset_fetch`, `test_tags` |

Format and platform detection itself (ISO, CHD, bin/cue, magic bytes, hashing) is covered
by the vendored [`formatscout`](../services/vendor/formatscout/) package's own `tests/`,
not by `backend/tests/`. The in-tree detection tests cover only the Peach-specific
launch-target resolution that stayed behind after the extraction.

**Frontend** (`frontend/src/`).

| Area | Covered |
|---|---|
| Primitives | `Button`, `Input`, `Textarea`, `FormField`, `Modal`, `PageHeader`, `StatusBadge` |
| Hooks | `useConfirmToken`, `useLaunch`, `useLibraryScan` |
| API client | `client.test.ts` (`credentials: 'include'` singleton behaviour) |
| Pages and components | `Emulators`, `Software`, `Tags` (each with a `.test` plus `.acceptance.test`), `Emulators/Profiles`, `OwnerBroken`, `UserSwitcher`, `LaunchHistory`, `TagChips`, `EraSelector`, `ConfirmModal`, `TabbedLayout`, the `Profiles`/`Bios`/`RomPacks` tabs, `EmulatorDetail`, and the v2 route-redirect tests |

## Gaps

| Gap | Detail |
|---|---|
| **Generated-file staleness is not caught** | `test.yml`'s `generate-types` job runs `git diff --exit-code` against `constants_generated.py`, `generated/constants.ts`, `openapi.json`, and `types.ts`. All four are gitignored and untracked, so `git diff` has nothing to compare and the step always passes. The check exists but is inert. |
| **No pre-commit or husky hook** | CI is the only mechanical gate. |
| **AppContainer and `sandbox_host.exe`** | `test_sandbox` covers the Job Object layer. The native path (`SECURITY_CAPABILITIES`, `CREATE_SUSPENDED`, `ResumeThread`) is a compiled binary with no Python test. Validation is a manual per-emulator smoke test and test matrix (OS × GPU × audio × controller × install path × locale). The moniker to test against is `Peach1UP.<slug>.<scope>`, for example `Peach1UP.duckstation.shared` or `Peach1UP.duckstation.42`. |
| **Environment image-path traversal** | Intentionally not validated (`base_image_path` and `working_image_path` may point anywhere; see [SECURITY.md](SECURITY.md) Known Gaps). No test asserts the behaviour either way. It is a documented accepted tradeoff, not tested enforcement. |
| **DB Literal enforcement** | No test asserts that a bad `file_type` or `era` string is rejected at persist time, because the DB does not reject it (see [TYPES.md](TYPES.md) §6). `file_type_from_path` self-validates at emit time, but a producer bypassing that helper and writing to a bare `String` column is still unguarded. |
| **Environment status vocabulary** | `test_environments_routes` exercises the routes, but the `healthy/degraded/unconfigured/error/ok/missing/unknown` vocabulary itself is not directly asserted. It is the generated `EnvironmentStatus` Literal at the Pydantic layer; the DB column is a bare `String`. |
| **Launch `target_type`** | `game_item_bundle` / `app_item_bundle` / `environment_item` is still a bare derived string with no Literal and no test. |
| **TheGamesDB proxy responses** | Untyped end to end, no OpenAPI schema, no contract test. |

### Two frontend tests are skipped (runner hang)

Not an application bug. Both test bodies pass their assertions, but the Vitest process
never advances past RUNNING: a leaked-async-handle signature whose source was not pinned
down, with an inconsistent hang point between runs. Investigated 2026-07-11.

- `frontend/src/components/layout/TabbedLayout.test.tsx`, *"derives the active tab from
  the URL, not from independent internal state"*
- `frontend/src/test/routing.sectionRedirects.test.tsx`, the `describe.skip` blocks

Both carry `TODO: re-enable once root cause is found and fixed`. Read the `KNOWN ISSUE`
comment blocks above each skip for the full notes. Tracked debt, revisit post-alpha.

## Verification practices

- **Static verification is the mandated default.** Read the code, trace call sites, check
  logic by inspection. Never run pytest or vitest in-sandbox, never install or update
  packages. The same rules apply to outside contributors; see
  [CONTRIBUTING.md](../CONTRIBUTING.md).
- **Regeneration discipline is convention-enforced:** `gen_constants.py` before export,
  then `export_and_build_types.py` to refresh `openapi.json` and `types.ts`.
  `_check_router_parity()` in `export_and_build_types.py` is the one loud failure in that
  chain: it diffs `backend.main.app`'s mounted routes against the export app's `ROUTERS`
  and raises if any are missing.
- **Commit hygiene substitutes for local CI:** one logical change per commit,
  `<type>(<scope>)` messages, `test` and `safety` types reserved for test and fail-safe
  changes.

## Where this leaves us

CI runs the suites, both linters, a formatter check, a production build, and a packaging
smoke test that launches the frozen exe and asserts it serves `/api/openapi.json`. That is
a real gate, not a formality.

The delta to a fully mechanically-enforced tier is three things: the inert generated-file
check, the absent frontend coverage floor, and the untestable native isolation path. None
of these are regressions. The first two are fixable; the third needs a manual matrix by
nature.
