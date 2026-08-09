# Peach 1UP: Types and Constants Ownership Map

Discovery-grounded snapshot of how typed values and constants actually flow through the
codebase today. Where the current code diverges from the intended single-source-of-truth
model, the divergence is called out explicitly rather than papered over.

Related: [TECH.md](TECH.md) for the stack, [TESTING.md](TESTING.md) for what is covered
by tests, [SECURITY.md](SECURITY.md) for the path and settings allowlists.

---

## 1. Ownership map: intended vs. actual

| Domain | Intended owner | Actual owner in code today | Notes |
| --- | --- | --- | --- |
| Emulator details (sandbox flags, container gating, CPU/mem skips) | TOMLs | `config/emulators/*.toml` → `emulator_catalog.py` resolvers; `EmulatorCatalogSlug` generated from TOMLs via `gen_constants.discover_catalog_slugs()` | ✅ matches. Per-emulator overrides live in the `settings` DB table as `sandbox_{slug}_{field}` keys (see §5). |
| API/domain constants (era, file_type, item_type, hardware_profile, install_type, tag color, ratings, environment status, backend/system labels) | `constants.yaml` | `config/constants.yaml` → `scripts/gen_constants.py` → `backend/constants_generated.py` + `frontend/src/generated/constants.ts` | ✅ matches (Pipeline A). |
| DB schema structure | DB | SQLModel models, `create_all()` on startup, no Alembic | ⚠️ **Columns are bare `String`, not enum-constrained.** The Literal types are Pydantic-only and are *not* enforced at the DB layer (see §6). |
| FE types | OpenAPI/Pydantic generated | FastAPI → `shared/openapi.json` (startup) → `openapi-typescript` → `shared/types.ts` | ✅ matches (Pipeline B), but B is **downstream of A**: every Pydantic field typed with a generated Literal re-inlines that enum into OpenAPI. |
| Secrets | `.env` | `.env`, via `backend/service/utils/env_secrets.py` (`PIN_PEPPER`, `THEGAMESDB_API_KEY`, `AI_API_KEY`, `IGDB_API_KEY`) | ✅ matches. `settings.yaml` has been removed; secrets live in `.env` exclusively. Gitignored. |
| Operational flags | "Settings DB table" | `settings` DB table (SQLite), via the `Settings` ORM model (`backend/models/settings.py:8`) and `backend/service/utils/settings.py` (shared engine from `backend/core/database.py`) | ✅ matches. `settings.yaml`/`paths.yaml` have been removed; all operational flags, per-emulator sandbox overrides, and the 5 path keys are DB-backed. |

**Bottom line:** the constants pipeline (A), the OpenAPI pipeline (B), the
TOML-to-catalog-slug pipeline, and the settings store all match the intended model. The
one remaining divergence is that the DB does not enforce the generated Literals, because
the columns are `String` (see §6).

---

## 2. The actual pipeline as it exists in code

**Pipeline A: constants to generated types**

```text
config/constants.yaml
  └─ scripts/gen_constants.py  (run manually / by build scripts, no hook)
       ├─ backend/constants_generated.py   (Era, EraValue, FileType, ItemType,
       │                                     HardwareProfile, InstallType,
       │                                     TagColor, BackendSlug,
       │                                     EnvironmentStatus, label dicts)
       └─ frontend/src/generated/constants.ts
```

**Pipeline A′: TOMLs to catalog slugs**

```text
config/emulators/*.toml
  └─ gen_constants.discover_catalog_slugs()
       └─ EmulatorCatalogSlug  (dosbox-x, 86box, duckstation, …)
          BackendSlug is a parallel vocabulary generated from constants.yaml's
          backend_slugs; the two now use the same spellings but stay separate types
```

**Pipeline B: Pydantic to OpenAPI to FE types (downstream of A)**

```text
FastAPI app  (models import generated Literals from constants_generated)
  └─ shared/openapi.json         (written at backend startup)
       └─ openapi-typescript
            └─ shared/types.ts    (consumed as @shared/types, ~40 FE files)
```

**Structural drift risk:** A and B refresh on *different triggers*. `generated/constants.ts` refreshes when
`gen_constants.py` runs; `types.ts` refreshes only when the backend restarts
and re-emits `openapi.json`. The frontend therefore holds two copies of the
same enum sourced at different times. `file_type` (was `media_type`) is the
canonical example: the generated `FileType` union is **dead** on the FE (0 FE
imports); the FE reads `file_type` exclusively via `@shared/types` (the OpenAPI
copy). CI regenerates both `constants_generated.*` and `shared/types.ts` on every
push/PR ([`.github/workflows/test.yml`](../.github/workflows/test.yml)), but it uploads
them as artifacts rather than diffing against the committed copies, so it still does not
fail a PR that commits a stale generated file. See [TESTING.md](TESTING.md).

---

## 3. Validation state at each boundary (enforced today vs not)

| Boundary | Value | Enforced? |
| --- | --- | --- |
| `constants_generated.py` Literals | Era, FileType, ItemType, InstallType, HardwareProfile, TagColor, EnvironmentStatus | ✅ static-type only (mypy/pyright); no runtime guard |
| Pydantic request/response models | fields typed `EraValue`, `Optional[FileType]`, `EnvironmentStatus`, etc. | ✅ FastAPI validates request bodies against the inlined enum; response models validated on serialization |
| **DB column** | `GameItem.file_type`, `GameItemBundle.era` | ❌ **`Column(String)`**: any string persists, and the Literal is not a DB constraint (`models/game.py`) |
| `file_type_from_path()` producer (was `media_type_from_path`) | returns `iso/cue/chd/bin/gdi/cdi/floppy/hdd/exe/rom/directory/unknown` | ✅ **validated at emit time**. `file_type_from_path` (`backend/service/utils/file_types.py`) checks its output against `_VALID_FILE_TYPES = frozenset(get_args(FileType))` and **raises** on an out-of-vocabulary value. The old `bin/gdi/cdi/rom` drift is resolved: those values are now first-class members of the `FileType` Literal *and* the producer self-checks against it |
| `formatscout.detect()` era output | bare era strings | ❌ validated against `EraValue` only at the DB/API boundary, never at emit time (by design, see §4) |
| `environments.py` environment status | `healthy/degraded/unconfigured/error/ok/missing/unknown` | ⚠ typed as the generated `EnvironmentStatus` Literal on `EnvironmentRead.status` (Pydantic-enforced), but the DB column is still `Column(String)`, so no DB constraint |
| `launch_history.py` target_type | `game_item_bundle`/`app_item_bundle`/`environment_item` | ❌ bare strings, derived in `LaunchHistoryRead._derive_target_type`, untyped |
| `era_defaults.defaults_for_era()` | era to (emulator_slug, profile_era) | ❌ hardcoded `match/case`, bare strings (`era_defaults.py`), one of three parallel era-to-emulator maps |
| Settings write endpoint | `PATCH /api/v1/settings` | ✅ allowlist-gated: `_USER_WRITABLE_KEYS`; `_SENSITIVE_KEYS` scrubbed from GET; `PIN_PEPPER`, `ALLOW_NETWORK_ACCESS`, `reset_db`, `rating_ordinals` all refused |
| Path inputs | scan/upload/library-path | ✅ `normalise_path` plus allowlist against `LIBRARY_PATH`/`SOFTWARE_PATH`/`PROFILES_PATH` (per [SECURITY.md](SECURITY.md)); **exception:** Environment image paths intentionally unvalidated (Known Gap) |

**Net:** enforcement is strong at the HTTP request boundary (Pydantic, settings
allowlist, path allowlist) and weaker at the DB-persist boundary, where `String` columns
still carry no `CHECK` constraint. The previously flagged value-emit hole is closed:
`file_type_from_path` self-validates against `FileType`, so the `bin/gdi/cdi/rom` case
that used to persist silently now raises at emit time. What remains is structural. A
producer that bypasses that helper and writes an arbitrary string straight into a
`String` column would still not be rejected by the DB (see §6).

---

## 4. formatscout call contract (current)

The detector was extracted from `backend/service/utils/smart_media_detector/` into the
standalone `formatscout` package, vendored at
[`services/vendor/formatscout/`](../services/vendor/formatscout/) and declared as a
dependency in `pyproject.toml`. Backend code imports it as `formatscout`. The
Peach-specific launch-target resolvers that stayed behind live in
[`backend/service/utils/detection/`](../backend/service/utils/detection/).

- **Entry signature:** `detect(path: Path) -> ScanResult` (`formatscout/detector.py`).
  It takes **no allowed-value-set parameter**: the caller does not pass
  `EraValue`/`FileType` in. The detector emits bare era strings from its own internal
  vocabulary, with era returns across `exe_detect.py`, `directory_detect.py`, and
  `iso_detect.py`.
- **Result type:** `ScanResult` (`formatscout/result.py`), including the
  `requires_manual_boot` and `requires_install` flags.
- **Call sites (all lazy imports unless noted):**
  - `backend/api/routes/game_item_bundles.py`
  - `backend/service/games/items.py`
  - `backend/service/utils/drive_utils.py`
  - `backend/service/utils/bios_placement.py` uses only
    `formatscout.hashing.hash_lookup.hash_file` (a module-level import), not `detect`
- **Contract consequence:** because the signature carries no vocabulary, the detector's
  output is reconciled to `EraValue` only at the DB/API boundary, never at emit time.
  This is intentional decoupling, but it means a detector-side era rename would not fail
  loudly against `constants.yaml`. The package boundary makes this looser than it was
  in-tree, since the two now version independently.

### 4a. verify() and classify(), the verification surface

This subsection covers the verification-specific entry points.

- **`verify(path, expected_sha1) -> VerifyResult`** (`verify.py`), hash-only,
  three-state (`matched` / `mismatched` / `not_in_index`). Needs a prior
  known hash to compare against, used internally by `classify()`'s
  `"verified"` tier only, not called directly by any backend code today.
- **`classify(path, title, era, threshold=0.80) -> ClassifyResult`**
  (`classify.py`), five-state (`verified` / `caution` / `mismatch` /
  `not_in_index` / `unchecked`), no prior expected hash needed. This is the
  function `backend/service/games/items.py` actually calls, once per disc,
  both at ingest (`_prepare_item`, `_create_multi_disc_collection`) and on a
  manual re-check (`_reverify_leaf_in_session`). `"mismatch"` (renamed from
  `"suspect"`) means the title fuzzy-matched an indexed title but no hash
  did, expected to happen often against an inherently incomplete public hash
  catalog, and not itself a sign the file is bad.
- **`GameItem.verification_status`** (`backend/models/game.py`) persists
  `ClassifyResult.status` verbatim, same five string values. `GameItem.sha1`
  persists `ClassifyResult.computed_sha1`. `GameItem.verification_similarity`
  persists `ClassifyResult.similarity`, populated only when status is
  `"mismatch"`, None otherwise.
- **`GameItemBundleRead.verification_status`** is a read-time rollup (not
  stored) across a bundle's items, worst-severity-wins, see
  `_rollup_verification_item` / `_VERIFICATION_SEVERITY` in
  `backend/models/game.py`. Per-disc verification means this rollup, not any
  single disc's own status, is a multi-disc bundle's true state.
  `GameItemBundleRead.verification_similarity` carries over from whichever
  leaf's status won that rollup, same None-unless-`"mismatch"` rule.
- **Raw hash never returned via the API.** `GameItem.sha1` has no field on
  `GameItemRead`, confirmed by reading `GameItemRead`'s field list directly
  (`backend/models/game.py`), not inferred. A caller needing the raw hash
  uses the `formatscout` package directly; `ClassifyResult` and `VerifyResult` both
  carry it.
- **Fuzzy title matching** (`hashing/title_match.py`) is stdlib-only
  (`difflib.SequenceMatcher`), no new dependency, scoped to `era`
  (skipped entirely when `era` is `None`/`"unknown"`, fails closed to
  `not_in_index` rather than searching every platform's titles).

---

## 5. settings key inventory + call sites

Backed by [`backend/service/utils/settings.py`](../backend/service/utils/settings.py)
(`_DEFAULTS`, `_PATH_KEYS`) and persisted to the `settings` DB table via the `Settings`
ORM model ([`backend/models/settings.py`](../backend/models/settings.py)).
`settings.yaml` and `%APPDATA%\Peach1UP\paths.yaml` have been removed, so every key
below, including the 6 path keys, is DB-only.

| Key | Class | Read/write sites |
| --- | --- | --- |
| `LIBRARY_PATH`, `SOFTWARE_PATH`, `MEDIA_PATH`, `OS_PATH`, `ROMS_PATH`, `PROFILES_PATH` | Path (static reference) | `main.py`, `uploads.py`, `game_item_bundles.py`, scan allowlist; written via `set_path()` + `POST /settings/library-path` |
| `suppress_confirmations` | Operational flag | user-writable (`settings.py:64`); consumed by confirmation-token flow |
| `reset_db` | Operational flag (destructive) | **not** user-writable; startup only |
| `delete_media_on_removal` | Operational flag | user-writable; FE reads `Software/index.tsx`, `Settings/AdvancedTab.tsx` |
| `PIN_PEPPER` | **Secret** | dedicated route `PATCH /settings/pin-pepper`; scrubbed from GET; refused on generic PATCH (`settings.py:81`) |
| `THEGAMESDB_API_KEY` | **Secret** | user-writable via `AdvancedTab.tsx:32`; status-only GET `/settings/thegamesdb-api-key/status`; scrubbed from GET-all |
| `ALLOW_NETWORK_ACCESS` | Operational flag (security boundary) | read in `main.py`, `api/middleware/security.py`, `api/routes/auth.py` (`_cookies_secure`); **not** user-writable, with no write site anywhere, so it is settable only by writing directly to the `settings` row |
| `rating_ordinals` | Static reference data | `_load_rating_ordinals()` in `core/dependencies.py`, falling back to `_BASE_RATING_ORDINALS` derived by `_derive_rating_ordinals()` from `CONTENT_RATINGS` (`config/constants.yaml`'s `content_ratings` list). The ordinal is the index within each entry's `scheme` group, so ESRB and PEGI each start their own ladder at 0. **Not** user-writable, same DB-only caveat as above |
| `sandbox_{slug}_container_enabled` | Operational flag (per-emulator) | read and written in `api/routes/emulators.py` via `set_flag` (`PATCH /{slug}/sandbox`); resolved through `get_container_enabled()`; default from TOML |
| `sandbox_{slug}_skip_memory_limit`, `sandbox_{slug}_skip_cpu_limit` | Operational flag (per-emulator) | same path as above, resolved through `get_skip_memory_limit()` / `get_skip_cpu_limit()`; default from TOML |
| `SCAN_NAV_THRESHOLD_BYTES` | Operational flag | read in `api/routes/game_item_bundles.py` (defaulted) |
| `first_run_complete` | Operational flag | `GET /settings/first-run-status`, `POST /settings/complete-first-run`, and `_sync_first_run_from_db` in `core/startup_tasks.py` |

Secret handling reference: `_SENSITIVE_KEYS = {AI_API_KEY, IGDB_API_KEY, PIN_PEPPER,
THEGAMESDB_API_KEY}` in [`backend/api/routes/settings.py`](../backend/api/routes/settings.py)
is excluded from the GET-all response.

---

## 6. Known SQLite / Enum limitation (concrete reference)

`backend/models/game.py` (`GameItem`)
```python
file_type: Optional[FileType] = Field(default=None, sa_column=Column(String))
```
and (`GameItemBundle`)
```python
era: EraValue = Field(sa_column=Column(String, nullable=False))
```

The generated `FileType` / `EraValue` Literals are applied as the **Pydantic**
field type, but the underlying SQLite column is a bare `String`. SQLModel/SQLite
do not enforce the Literal as a `CHECK` constraint or native enum. Therefore:

- A producer that bypasses `file_type_from_path` and writes an out-of-vocabulary
  value straight to the column will still **persist successfully** to the DB (the
  column has no `CHECK`). The specific `bin/gdi/cdi/rom` case that previously did
  this is resolved: those are now valid `FileType` members, and
  `file_type_from_path` self-validates against the Literal (§3), so the common
  producer path can no longer emit an unknown value silently.
- Where a bad value does reach the column, the mismatch only surfaces later on
  the *read* side when the value is serialized back through a Pydantic model whose
  Literal no longer accepts it. That is the mechanism behind the previously reported
  read-time crash class.

This is a structural limitation of typing a `String` column with a Python
Literal, not a bug at any single line. Enforcing it would require a DB-level
`CHECK` constraint or a validator on the producer side.

---

## Flags (security / resource / structural)

- **No new security issue.** The material risks are all pre-documented: the Pipeline
  A/B regeneration split (§2) and the Environment-image-path traversal gap
  ([SECURITY.md](SECURITY.md) Known Gaps, intentionally unvalidated for NAS and
  secondary drives). The old unvalidated `media_type_from_path` output is resolved, since
  `file_type_from_path` validates against `FileType` at emit time (§3).
- **DB does not enforce generated Literals** (§6). The remaining place a bad enum value
  could persist is a producer that bypasses the validating helper and writes straight to
  a `String` column.
- **`settings.yaml`/`paths.yaml` removed, resolved.** Secrets now live in `.env`
  exclusively and operational flags and paths now live in `settings` exclusively,
  matching the intended ownership model in §1.
- **Resource note:** `ALLOW_NETWORK_ACCESS`, `rating_ordinals`, and
  `SCAN_NAV_THRESHOLD_BYTES` were hand-edit-`settings.yaml` only. That escape hatch is
  gone with no replacement UI or API route, so changing them requires a direct write to
  the `settings` table (see §7).
- Roughly a dozen dead generated exports and 3 parallel era-to-emulator maps remain a
  maintenance-drift surface, not runtime bugs.

---

## 7. Settings store: resolved state (settings.yaml/paths.yaml collapse, complete)

This section originally scoped a discovery-only audit for collapsing
`settings.yaml`/`paths.yaml` into `settings`. That collapse is done:
`config/settings.yaml` and `%APPDATA%\Peach1UP\paths.yaml` have been deleted
from disk, and their load/write functions removed from
`backend/service/utils/settings.py`. This section reflects the resulting
architecture rather than the original discovery notes.

### 7.1 `backend/service/utils/settings.py`: module surface

Symbol names rather than line numbers, since the line offsets in this file drift with
every edit.

- `_DEFAULTS`: the 6 path keys (`LIBRARY_PATH`, `SOFTWARE_PATH`, `MEDIA_PATH`, `OS_PATH`,
  `ROMS_PATH`, `PROFILES_PATH`) plus `suppress_confirmations`, `reset_db`,
  `delete_media_on_removal`, `delete_original_on_upload`, `UPLOAD_TMP_TTL_SECONDS`,
  `metadata_provider`, and `launch_history_retention`.
- `_PATH_KEYS`: the 6 path keys above, normalised and resolved absolute at `init()` time
  and stored in `settings` like every other key. No separate paths file exists.
- No `_USER_WRITABLE_KEYS` or `_SENSITIVE_KEYS` in this module. Those two allowlists live
  one layer up, in
  [`backend/api/routes/settings.py`](../backend/api/routes/settings.py).
- Read/write primitives: `get()`, `set_flag()`, `add_suppression()` / `is_suppressed()`,
  `set_path()`, `get_env_var()`.
- Persistence: `_persist()` upserts a single key into the `settings` table through the
  shared SQLAlchemy engine (`backend.core.database.get_engine()`) and the `Settings` ORM
  model ([`backend/models/settings.py`](../backend/models/settings.py)). No raw SQL and no
  YAML I/O of any kind. `_load_all_rows()` reads the whole table the same way.

### 7.2 Key classification, now uniform

Every key listed in §5 is DB-only, in the single `settings` table. There
is no YAML-backed key any more, no `paths.yaml` overlay, and no key that must
be reconciled between two stores, so the YAML-versus-DB divergence §1 used to flag is
gone. The one remaining split is deliberate rather than a divergence: the 4 secret-class
keys (`PIN_PEPPER`, `THEGAMESDB_API_KEY`, `AI_API_KEY`, `IGDB_API_KEY`) are kept out of
`settings` and live in `.env` instead (§7.3), because a secret must not round-trip
through the same SQLite file the `reset_db` dev flag can delete.

One operational consequence of the removal: `ALLOW_NETWORK_ACCESS`,
`rating_ordinals`, and `SCAN_NAV_THRESHOLD_BYTES` previously had no
programmatic write path and were "hand-edit `config/settings.yaml`" only.
That escape hatch is gone with no replacement UI or API route, so changing any of these
three today requires a direct write to the `settings` table (e.g. via a script), not a
config-file edit.

### 7.3 Secrets in `.env`, mechanism unchanged by the collapse

- `PIN_PEPPER`: single dedicated route (`PATCH /settings/pin-pepper`),
  refused on the generic PATCH, scrubbed from `GET /settings`
  (`_SENSITIVE_KEYS`).
- `THEGAMESDB_API_KEY`: user-writable via the generic PATCH (`AdvancedTab.tsx` →
  `_USER_WRITABLE_KEYS`); scrubbed from GET; status-only endpoint
  (`/thegamesdb-api-key/status`).
- `AI_API_KEY` and `IGDB_API_KEY`: still a dead secret surface. Both are in
  `_SENSITIVE_KEYS` and `_USER_WRITABLE_KEYS` (writable + scrubbed) but **no
  code anywhere reads either key**, in `backend/` or `frontend/src`. Not a
  leak, but a user can be led to believe setting these does something when
  nothing consumes them. Unresolved carryover from the pre-collapse audit,
  independent of the YAML removal, worth resolving on its own by wiring up a consumer or
  removing the allowlist entries.
- `get_env_secret()`/`set_env_secret()` (`backend/service/utils/env_secrets.py`)
  are the only read/write path for all four keys. No secret ever touches
  `settings`.

### 7.4 `settings` table (DB): full consumer list

Definition: [`backend/models/settings.py`](../backend/models/settings.py) defines
`Settings` (table `settings`, columns `key`/`value`/`updated_at`) and `SettingsPatch`, a
generic `{updates: dict}` Pydantic body used by the generic PATCH endpoint. The name
overlap with the `Settings` DB model is coincidental, not a coupling.

Every key now round-trips through this table via `_load_all_rows()` and `_persist()`,
not just `first_run_complete` as before the collapse. `first_run_complete` itself is still handled the same
way it always was: `backend/api/routes/settings.py` (`GET /first-run-status`,
`POST /complete-first-run`) and `backend/core/startup_tasks.py`
(`_sync_first_run_from_db`).

### 7.5 Table-creation / seed flow (updated for the T1/T6 engine-sharing fix)

- `ensure_settings_table()` (`backend/core/database.py`) creates just the
  `settings` table at T1 (import time, inside `settings.init()`, called
  from `main.py` before the FastAPI app is built), scoped narrowly enough to run before
  the rest of `backend.models.*` has registered with `SQLModel.metadata`.
- `create_tables()` (`backend/core/database.py`, invoked from `lifespan.py`)
  still runs the full `SQLModel.metadata.create_all()` at T6 (ASGI startup), a no-op for
  `settings` since it already exists by then. Plain `create_all`, no Alembic.
- The legacy-migration seed step (`_migrate_legacy_config_into_db()`) has
  been deleted along with `settings.yaml`/`paths.yaml`. `init()` no longer
  does an empty-table check to trigger a one-time migration, because there is nothing
  left to migrate from.

---

## 8. Era to emulator coverage (10 wired emulators, current state)

Cross-referenced [`config/constants.yaml`](../config/constants.yaml) (`eras`,
`backend_slugs`, `backend_system_labels`) against `era_defaults.defaults_for_era()`,
`startup_seed.py`, `backend_router._BACKEND_MODULES`, and the detector's era branches.
All 13 non-`unknown` eras in `constants.yaml`'s `eras` map route to one of the 10 wired
emulators, so there is currently **no** era or ROM-shaped format that is detectable but
has no backend:

| Era | Emulator | ROM/BIOS required |
| --- | --- | --- |
| dos | dosbox-x | No |
| win95, win98, winxp | 86box | Yes (86Box ROM pack) |
| ps1 | duckstation | Yes (PS1 BIOS) |
| ps2 | pcsx2 | Yes (PS2 BIOS) |
| ps3 | rpcs3 | Yes (PS3 firmware) |
| xbox | xemu | Yes (Xbox BIOS) |
| xbox360 | xenia | No |
| nes | mesen | No |
| snes | mesen | No |
| n64 | project64 | No |
| dreamcast | flycast | Yes (DC BIOS) |

`_BACKEND_MODULES` in
[`backend/service/utils/backend_router.py`](../backend/service/utils/backend_router.py)
maps 10 slugs onto 7 backend modules: `dosbox`, `box86`, `xemu`, `rpcs3`, `flycast`,
`xenia`, and a shared `console` module serving duckstation, pcsx2, mesen, and project64.

> **`win31` (Windows 3.1) has been removed** from `constants.yaml`'s `eras` map, so
> `EraValue` no longer lists it and DOSBox-X now backs `dos` only. Docs that still
> mention a Windows 3.1 era are stale. Flagged in case the removal was not intended.

**SNES is not unresolved.** `era_defaults.py` (`case "snes": return ("mesen", "snes")`),
`startup_seed.py` (`supported_eras: ["nes", "snes"]`), `eras.yaml` (`snes.backend:
mesen`), and the detector (era `"snes"` on `.sfc`/`.smc` and similar) all route it to
Mesen identically to NES. The earlier label inconsistency is resolved:
`constants.yaml`'s `backend_system_labels.mesen` now reads `"NES, SNES"`.

**No GBA, GB/GBC, or Genesis/32X detection exists anywhere in the codebase today.** Not
in `constants.yaml`'s `eras` map, not in `config/eras.yaml`, and not as an era branch in
the `formatscout` detector. These formats are neither detected nor backed; they are
absent from scope rather than a detected-without-a-backend gap.

---

**Summary:** the settings.yaml → DB collapse is complete. `settings` now
holds every operational flag, per-emulator sandbox override, and path key;
secrets remain in `.env` by design (§7.3). The two items worth resolving
independently of the collapse, carried forward unchanged from the original
discovery: the dead `AI_API_KEY`/`IGDB_API_KEY` secret surface (§7.3), and
the DB's lack of Literal enforcement (§6).
