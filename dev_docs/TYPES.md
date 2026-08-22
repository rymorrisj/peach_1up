# Types and Constants

How typed values and constants flow through the codebase today. Where the code diverges
from the single-source-of-truth model, the divergence is called out rather than papered
over.

Related: [TECH.md](TECH.md) (stack) · [TESTING.md](TESTING.md) (what is covered) ·
[SECURITY.md](SECURITY.md) (path and settings allowlists).

## 1. Ownership

| Domain | Owner in code | State |
|---|---|---|
| Emulator details (sandbox flags, container gating, resource skips) | `config/emulators/*.toml` to `emulator_catalog.py` resolvers; `EmulatorCatalogSlug` generated via `gen_constants.discover_catalog_slugs()` | Matches. Per-emulator overrides live in the `settings` table as `sandbox_{slug}_{field}`. |
| API and domain constants (era, file_type, item_type, hardware_profile, install_type, tag color, ratings, environment status, backend labels) | `config/constants.yaml` to `scripts/gen_constants.py` to `backend/constants_generated.py` + `frontend/src/generated/constants.ts` | Matches (Pipeline A). |
| Frontend types | FastAPI to `shared/openapi.json` to `openapi-typescript` to `shared/types.ts` | Matches (Pipeline B), but B is downstream of A. |
| Secrets | `.env` via `backend/service/utils/env_secrets.py` | Matches. Gitignored. |
| Operational flags and paths | `settings` DB table via `backend/models/settings.py` and `backend/service/utils/settings.py` | Matches. `settings.yaml` and `paths.yaml` are gone. |
| **DB schema constraints** | SQLModel models, `create_all()`, no Alembic | **Diverges.** Columns are bare `String`. The Literals are Pydantic-only and are not DB constraints. See §5. |

## 2. Pipelines

**A: constants to generated types**

```
config/constants.yaml
  └─ scripts/gen_constants.py          (manual or build script, no hook)
       ├─ backend/constants_generated.py     Era, EraValue, FileType, ItemType,
       │                                     HardwareProfile, InstallType, TagColor,
       │                                     BackendSlug, EnvironmentStatus, label dicts
       └─ frontend/src/generated/constants.ts
```

**A prime: TOMLs to catalog slugs**

```
config/emulators/*.toml
  └─ gen_constants.discover_catalog_slugs()
       └─ EmulatorCatalogSlug   (dosbox-x, 86box, duckstation, …)
```

`BackendSlug` is a parallel vocabulary generated from `constants.yaml`'s `backend_slugs`.
The two use the same spellings but stay separate types.

**B: Pydantic to OpenAPI to frontend types** (downstream of A)

```
FastAPI app  (models import generated Literals)
  └─ shared/openapi.json      written at backend startup
       └─ openapi-typescript
            └─ shared/types.ts     consumed as @shared/types by roughly 40 frontend files
```

**Drift risk: A and B refresh on different triggers.** `generated/constants.ts` refreshes
when `gen_constants.py` runs; `types.ts` refreshes only when the backend restarts and
re-emits `openapi.json`. The frontend therefore holds two copies of the same enum sourced
at different times. `file_type` is the canonical example: the generated `FileType` union is
dead on the frontend (zero imports), which reads `file_type` exclusively through
`@shared/types`, the OpenAPI copy.

CI regenerates both on every push and PR, and `generate-types` has a `git diff --exit-code`
step meant to fail on a stale committed copy. **That step is inert**: all four generated
paths are gitignored and untracked, so `git diff` has nothing to compare and always exits 0.

## 3. Validation at each boundary

| Boundary | Value | Enforced |
|---|---|---|
| `constants_generated.py` Literals | Era, FileType, ItemType, InstallType, HardwareProfile, TagColor, EnvironmentStatus | Static typing only (mypy/pyright). No runtime guard. |
| Pydantic request and response models | fields typed `EraValue`, `Optional[FileType]`, `EnvironmentStatus` | Yes. FastAPI validates request bodies against the inlined enum; response models validate on serialization. |
| **DB column** | `GameItem.file_type`, `GameItemBundle.era` | **No.** `Column(String)`, any string persists. |
| `file_type_from_path()` | returns `iso/cue/chd/bin/gdi/cdi/floppy/hdd/exe/rom/directory/unknown` | Yes, at emit time. It checks its own output against `frozenset(get_args(FileType))` and raises on an out-of-vocabulary value. |
| `formatscout.detect()` era output | bare era strings | No. Reconciled to `EraValue` only at the DB/API boundary, never at emit time. Intentional; see §4. |
| `environments.py` status | `healthy/degraded/unconfigured/error/ok/missing/unknown` | Partially. Typed as the generated `EnvironmentStatus` Literal on `EnvironmentRead.status`, so Pydantic enforces it, but the DB column is still `Column(String)`. |
| `launch_history` `target_type` | `game_item_bundle` / `app_item_bundle` / `environment_item` | No. Bare strings derived in `LaunchHistoryRead._derive_target_type`. |
| `era_defaults.defaults_for_era()` | era to (emulator_slug, profile_era) | No. Hardcoded `match/case` with bare strings, one of three parallel era-to-emulator maps. |
| `PATCH /api/v1/settings` | settings writes | Yes. Allowlist-gated by `_USER_WRITABLE_KEYS`; `_SENSITIVE_KEYS` scrubbed from GET; `PIN_PEPPER`, `ALLOW_NETWORK_ACCESS`, `reset_db`, and `rating_ordinals` all refused. |
| Path inputs | scan, upload, library-path | Yes. `normalise_path` plus an allowlist against `LIBRARY_PATH`/`SOFTWARE_PATH`/`PROFILES_PATH`. **Exception:** Environment image paths are intentionally unvalidated (see [SECURITY.md](SECURITY.md) Known Gaps). |

Enforcement is strong at the HTTP request boundary and weak at the DB-persist boundary,
where `String` columns carry no `CHECK` constraint. The value-emit hole is closed;
what remains is structural.

## 4. formatscout contract

Extracted from `backend/service/utils/smart_media_detector/` into the standalone
[`formatscout`](https://pypi.org/project/formatscout/) package, installed as a regular
dependency in `pyproject.toml`. The Peach-specific launch-target resolvers that stayed
behind live in
[`backend/service/utils/detection/`](../backend/service/utils/detection/).

| Entry point | Signature | Returns |
|---|---|---|
| `detect` | `detect(path: Path) -> ScanResult` | Era, reason, `requires_manual_boot`, `requires_install` |
| `verify` | `verify(path, expected_sha1) -> VerifyResult` | `matched` / `mismatched` / `not_in_index` |
| `classify` | `classify(path, title, era, threshold=0.80) -> ClassifyResult` | `verified` / `caution` / `mismatch` / `not_in_index` / `unchecked` |

`detect` takes **no allowed-value-set parameter**. The caller never passes `EraValue` or
`FileType` in, so the detector emits bare era strings from its own internal vocabulary. The
consequence is deliberate decoupling: a detector-side era rename would not fail loudly
against `constants.yaml`. The package boundary makes this looser than it was in-tree, since
the two now version independently.

Call sites (lazy imports unless noted): `game_item_bundles.py`, `games/items.py`,
`drive_utils.py`, and `bios_placement.py` (module-level, uses only
`formatscout.hashing.hash_lookup.hash_file`, not `detect`).

### Verification surface

- `verify()` is hash-only and needs a prior known hash. It is used internally by
  `classify()`'s `verified` tier and is not called directly by any backend code.
- `classify()` is what `games/items.py` actually calls, once per disc, at ingest
  (`_finalize_row_fields`, reached from both the single and multi-disc paths) and on a
  manual re-check (`_reverify_leaf_in_session`). `mismatch` (renamed from `suspect`) means
  the title fuzzy-matched an indexed title but no hash did. That is expected to happen
  often against an inherently incomplete public catalog and is not itself a sign the file
  is bad.
- `GameItem.verification_status` persists `ClassifyResult.status` verbatim.
  `GameItem.sha1` persists `computed_sha1`. `GameItem.verification_similarity` persists
  `similarity`, populated only when status is `mismatch`.
- `GameItemBundleRead.verification_status` is a read-time rollup across a bundle's items,
  worst severity wins (`_rollup_verification_item` / `_VERIFICATION_SEVERITY` in
  `models/game.py`). For a multi-disc bundle this rollup, not any single disc, is the true
  state.
- **The raw hash is never returned via the API.** `GameItem.sha1` has no field on
  `GameItemRead`. A caller needing it uses `formatscout` directly.
- Fuzzy title matching (`hashing/title_match.py`) is stdlib-only
  (`difflib.SequenceMatcher`) and scoped to `era`. It is skipped entirely when `era` is
  `None` or `unknown`, failing closed to `not_in_index` rather than searching every
  platform's titles.

> **Known gap: `sha1 = NULL` on directory-shaped leaves.** Ingest runs `classify()` against
> the leaf's `file_path`. When that path is a directory (PS3 folder layouts, DOS loose-file
> folders) no hash is computed and `sha1` stays `NULL`. A later manual re-verify takes the
> no-baseline branch, resolves the directory to its inner media file, and stores *that*
> file's hash, so ingest and re-verify disagree about what the leaf's hash represents.

## 5. Known SQLite Literal limitation

```python
# backend/models/game.py
file_type: Optional[FileType] = Field(default=None, sa_column=Column(String))
era: EraValue = Field(sa_column=Column(String, nullable=False))
```

The generated Literals are the **Pydantic** field type; the underlying SQLite column is a
bare `String`. SQLModel and SQLite do not translate a Literal into a `CHECK` constraint or
native enum. Therefore:

- A producer that bypasses `file_type_from_path` and writes an out-of-vocabulary value
  straight to the column **persists successfully**.
- The mismatch only surfaces later, on the read side, when the value serializes back
  through a Pydantic model whose Literal no longer accepts it. That is the mechanism behind
  the read-time crash class.

This is structural, not a bug at any single line. Enforcing it needs a DB-level `CHECK` or
a producer-side validator.

## 6. Settings inventory

Backed by [`backend/service/utils/settings.py`](../backend/service/utils/settings.py)
(`_DEFAULTS`, `_PATH_KEYS`) and persisted to the `settings` table via the `Settings` ORM
model. Every key below is DB-only; there is no YAML store.

| Key | Class | Notes |
|---|---|---|
| `LIBRARY_PATH`, `SOFTWARE_PATH`, `MEDIA_PATH`, `OS_PATH`, `ROMS_PATH`, `PROFILES_PATH` | Path | Resolved absolute at `init()`. Written via `set_path()` and `POST /api/v1/settings/library-path`. User-writable through the generic PATCH. |
| `suppress_confirmations` | Operational flag (list) | Consumed by the confirmation-token flow. User-writable. |
| `delete_media_on_removal` | Operational flag | User-writable. |
| `delete_original_on_upload` | Operational flag | User-writable. |
| `metadata_provider` | Operational flag | `thegamesdb` (default) or `igdb`. User-writable. |
| `launch_history_retention` | Operational flag | `never` (default) preserves unbounded history. User-writable. |
| `UPLOAD_TMP_TTL_SECONDS` | Operational flag | Not user-writable. |
| `reset_db` | Operational flag (destructive) | Not user-writable. Startup only, cleared immediately after use. |
| `ALLOW_NETWORK_ACCESS` | Security boundary | Read in `main.py`, `middleware/security.py`, `routes/auth.py` (`_cookies_secure`). **Not** user-writable and has no write site anywhere, so it is settable only by writing the `settings` row directly. |
| `rating_ordinals` | Static reference data | `_load_rating_ordinals()` in `core/dependencies.py`, falling back to `_BASE_RATING_ORDINALS` derived from `constants.yaml`'s `content_ratings`. The ordinal is the index within each entry's `scheme` group, so ESRB and PEGI each start their own ladder at 0. **Not** user-writable, same DB-only caveat. |
| `sandbox_{slug}_container_enabled` | Per-emulator flag | Read and written in `routes/emulators.py` via `set_flag` (`PATCH /{slug}/sandbox`); resolved through `get_container_enabled()`. Default from the TOML. |
| `sandbox_{slug}_skip_memory_limit`, `sandbox_{slug}_skip_cpu_limit` | Per-emulator flag | Same path, resolved through `get_skip_memory_limit()` / `get_skip_cpu_limit()`. |
| `SCAN_NAV_THRESHOLD_BYTES` | Operational flag | Read in `routes/game_item_bundles.py` with a default. |
| `first_run_complete` | Operational flag | `GET /settings/first-run-status`, `POST /settings/complete-first-run`, `_sync_first_run_from_db` in `core/startup_tasks.py`. |

`ALLOW_NETWORK_ACCESS`, `rating_ordinals`, and `SCAN_NAV_THRESHOLD_BYTES` have no
programmatic write path at all. They used to be hand-editable in `config/settings.yaml`;
that escape hatch is gone with no replacement, so changing any of them today means writing
the `settings` table directly.

### Module surface

Symbol names rather than line numbers, since offsets drift with every edit.

- `_DEFAULTS`: the 6 path keys plus `suppress_confirmations`, `reset_db`,
  `delete_media_on_removal`, `delete_original_on_upload`, `UPLOAD_TMP_TTL_SECONDS`,
  `metadata_provider`, `launch_history_retention`.
- `_PATH_KEYS`: the 6 path keys, normalised and resolved absolute at `init()` time.
- Read/write primitives: `get()`, `set_flag()`, `add_suppression()` / `is_suppressed()`,
  `set_path()`, `get_env_var()`.
- `_persist()` upserts a single key through the shared SQLAlchemy engine and the `Settings`
  ORM model. `_load_all_rows()` reads the whole table the same way. No raw SQL, no YAML.
- The allowlists live one layer up, in
  [`backend/api/routes/settings.py`](../backend/api/routes/settings.py), not here.

### Table creation

- `ensure_settings_table()` (`core/database.py`) creates just the `settings` table at
  import time, inside `settings.init()`, called from `main.py` before the FastAPI app is
  built. Scoped narrowly enough to run before the rest of `backend.models.*` has registered
  with `SQLModel.metadata`.
- `create_tables()` runs the full `SQLModel.metadata.create_all()` at ASGI startup, a no-op
  for `settings` by then. Plain `create_all`, no Alembic.

## 7. Secrets in `.env`

`get_env_secret()` / `set_env_secret()` in
[`env_secrets.py`](../backend/service/utils/env_secrets.py) are the only read/write path.
No secret ever touches the `settings` table, because a secret must not round-trip through
the same SQLite file the `reset_db` dev flag can delete.

`_ENV_KEYS` (writable in `.env`): `PIN_PEPPER`, `THEGAMESDB_API_KEY`, `AI_API_KEY`,
`IGDB_CLIENT_ID`, `IGDB_CLIENT_SECRET`.

| Key | Write path | Read by |
|---|---|---|
| `PIN_PEPPER` | Dedicated `PATCH /settings/pin-pepper` (owner-only). Refused on the generic PATCH, because changing it requires re-hashing the owner PIN. | `pin_hashing.py` |
| `THEGAMESDB_API_KEY` | Generic PATCH via `_ENV_SECRET_KEYS` | `thegamesdb_provider.py` |
| `IGDB_CLIENT_ID`, `IGDB_CLIENT_SECRET` | Generic PATCH via `_ENV_SECRET_KEYS` | `metadata_providers/igdb_provider.py` |
| `AI_API_KEY` | Generic PATCH via `_ENV_SECRET_KEYS` | **Nothing.** Dead surface: writable and scrubbed, but no consumer anywhere in `backend/` or `frontend/src`. Not a leak, but a user can be led to believe setting it does something. |

All six of `_SENSITIVE_KEYS` (the five above plus `IGDB_ACCESS_TOKEN`) are scrubbed from
`GET /api/v1/settings`. `IGDB_ACCESS_TOKEN` is deliberately absent from `_ENV_KEYS`: it is
a Twitch OAuth token the provider mints and refreshes itself, never something a user sets.

Status-only endpoints expose configured-or-not without values:
`/settings/pin-pepper/status`, `/settings/thegamesdb-api-key/status`, and
`/settings/igdb-status` (true only when both IGDB credentials are present). All three are
owner-gated.

## 8. Era to emulator coverage

All 13 non-`unknown` eras in `constants.yaml` route to one of the 10 wired emulators, so
there is no era or ROM-shaped format that is detectable but has no backend.

| Era | Emulator | ROM or BIOS |
|---|---|---|
| `dos` | dosbox-x | No |
| `win95`, `win98`, `winxp` | 86box | Yes, 86Box ROM pack |
| `ps1` | duckstation | Yes, PS1 BIOS |
| `ps2` | pcsx2 | Yes, PS2 BIOS |
| `ps3` | rpcs3 | Yes, PS3 firmware |
| `xbox` | xemu | Yes, Xbox BIOS |
| `xbox360` | xenia | No |
| `nes` | mesen | No |
| `snes` | mesen | No |
| `n64` | project64 | No |
| `dreamcast` | flycast | Yes, DC BIOS |

`_BACKEND_MODULES` in
[`backend_router.py`](../backend/service/utils/backend_router.py) maps those 10 slugs onto
7 backend modules: `dosbox`, `box86`, `xemu`, `rpcs3`, `flycast`, `xenia`, and a shared
`console` serving duckstation, pcsx2, mesen, and project64.

**`win31` has been removed** from `constants.yaml`'s `eras` map, so `EraValue` no longer
lists it and DOSBox-X backs `dos` only. Anything still referencing a Windows 3.1 era is
stale.

**No GBA, GB/GBC, or Genesis/32X detection exists anywhere**, in `constants.yaml`,
`eras.yaml`, or the detector. These are absent from scope, not a detected-without-a-backend
gap.

## Flags

- **No new security issue.** The material risks are pre-documented: the Pipeline A/B
  regeneration split (§2) and the Environment image-path gap ([SECURITY.md](SECURITY.md)
  Known Gaps).
- **The DB does not enforce generated Literals** (§5).
- **The CI staleness check for generated files cannot fail** (§2).
- **`AI_API_KEY` is a dead secret surface** (§7).
- Roughly a dozen dead generated exports and three parallel era-to-emulator maps remain a
  maintenance-drift surface, not runtime bugs.
