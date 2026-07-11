# Peach 1UP — Types & Constants Ownership Map

Discovery-grounded snapshot of how typed values and constants actually flow
through the codebase today. Where the current code diverges from the intended
single-source-of-truth model, the divergence is called out explicitly rather
than papered over. Extends and reconfirms `TYPES_AUDIT.md` (no drift found
since that audit; new detail added on settings, DB column typing, and the
detector contract).

---

## 1. Ownership map — intended vs. actual

| Domain | Intended owner | Actual owner in code today | Notes |
| --- | --- | --- | --- |
| Emulator details (sandbox flags, container gating, CPU/mem skips) | TOMLs | `config/emulators/*.toml` → `emulator_catalog.py` resolvers; `EmulatorCatalogSlug` generated from TOMLs via `gen_constants.discover_catalog_slugs()` | ✅ matches. Per-launch overrides live in `settings.yaml` as `sandbox_{slug}_{field}` keys (see §5). |
| API/domain constants (era, file_type, item_type, hardware_profile, install_type, tag color, ratings, environment status, backend/system labels) | `constants.yaml` | `config/constants.yaml` → `scripts/gen_constants.py` → `backend/constants_generated.py` + `frontend/src/generated/constants.ts` | ✅ matches (Pipeline A). |
| DB schema structure | DB | SQLModel models, `create_all()` on startup, no Alembic | ⚠️ **Columns are bare `String`, not enum-constrained** — the Literal types are Pydantic-only and are *not* enforced at the DB layer (see §6). |
| FE types | OpenAPI/Pydantic generated | FastAPI → `shared/openapi.json` (startup) → `openapi-typescript` → `shared/types.ts` | ✅ matches (Pipeline B), but B is **downstream of A** — every Pydantic field typed with a generated Literal re-inlines that enum into OpenAPI. |
| Secrets | `.env` | `.env`, via `backend/service/utils/env_secrets.py` (`PIN_PEPPER`, `THEGAMESDB_API_KEY`, `AI_API_KEY`, `IGDB_API_KEY`) | ✅ matches. `settings.yaml` has been removed; secrets live in `.env` exclusively. Gitignored. |
| Operational flags | "Settings DB table" | `app_settings` DB table (SQLite), via the `Settings` ORM model (`backend/models/settings.py:8`) and `backend/service/utils/settings.py` (shared engine from `backend/core/database.py`) | ✅ matches. `settings.yaml`/`paths.yaml` have been removed; all operational flags, per-emulator sandbox overrides, and the 5 path keys are DB-backed. |

**Bottom line:** the constants pipeline (A), the OpenAPI pipeline (B), the
TOML→catalog-slug pipeline, and the settings store all match the intended
model now. The one remaining divergence is that the DB does not enforce the
generated Literals — columns are `String` (see §6).

---

## 2. The actual pipeline as it exists in code

**Pipeline A — constants → generated types**
```
config/constants.yaml
  └─ scripts/gen_constants.py  (run manually / by build scripts, no hook)
       ├─ backend/constants_generated.py   (Era, EraValue, FileType, ItemType,
       │                                     HardwareProfile, InstallType,
       │                                     TagColor, BackendSlug,
       │                                     EnvironmentStatus, label dicts)
       └─ frontend/src/generated/constants.ts
```

**Pipeline A′ — TOMLs → catalog slugs**
```
config/emulators/*.toml
  └─ gen_constants.discover_catalog_slugs()
       └─ EmulatorCatalogSlug  (dosbox-x, 86box, duckstation, …)
          — different vocabulary from BackendSlug (dosbox, 86box, …); both live
```

**Pipeline B — Pydantic → OpenAPI → FE types (downstream of A)**
```
FastAPI app  (models import generated Literals from constants_generated)
  └─ shared/openapi.json         (written at backend startup)
       └─ openapi-typescript
            └─ shared/types.ts    (consumed as @shared/types, ~40 FE files)
```

**Structural drift risk (unchanged from audit):** A and B refresh on
*different triggers*. `generated/constants.ts` refreshes when
`gen_constants.py` runs; `types.ts` refreshes only when the backend restarts
and re-emits `openapi.json`. The frontend therefore holds two copies of the
same enum sourced at different times. `file_type` (was `media_type`) is the
canonical example: the generated `FileType` union is **dead** on the FE (0 FE
imports); the FE reads `file_type` exclusively via `@shared/types` (the OpenAPI
copy). CI now regenerates both `constants_generated.*` and `shared/types.ts` on
every push/PR (`.github/workflows/test.yml`), but it uploads them as artifacts
rather than diffing against the committed copies, so it still does not fail a PR
that commits a stale generated file. See TESTING.md.

---

## 3. Validation state at each boundary (enforced today vs. not)

| Boundary | Value | Enforced? |
| --- | --- | --- |
| `constants_generated.py` Literals | Era, FileType, ItemType, InstallType, HardwareProfile, TagColor, EnvironmentStatus | ✅ static-type only (mypy/pyright); no runtime guard |
| Pydantic request/response models | fields typed `EraValue`, `Optional[FileType]`, `EnvironmentStatus`, etc. | ✅ FastAPI validates request bodies against the inlined enum; response models validated on serialization |
| **DB column** | `SoftwareItem.file_type`, `SoftwareCollection.era` | ❌ **`Column(String)`** — any string persists; the Literal is not a DB constraint (`models/software.py`) |
| `file_type_from_path()` producer (was `media_type_from_path`) | returns `iso/cue/chd/bin/gdi/cdi/floppy/hdd/exe/rom/directory/unknown` | ✅ **now validated at emit time**. `file_type_from_path` (`service/utils/file_types.py:78`) checks its output against `_VALID_FILE_TYPES = get_args(FileType)` and **raises** on an out-of-vocabulary value. The old `bin/gdi/cdi/rom` drift is resolved: those values are now first-class members of the `FileType` Literal *and* the producer self-checks against it |
| `smart_media_detector.detect()` era output | bare era strings | ❌ validated against `EraValue` only at the DB/API boundary, never at emit time (by design — see §4) |
| `environments.py` environment status | `healthy/degraded/unconfigured/error/ok/missing/unknown` | ⚠ typed as the generated `EnvironmentStatus` Literal on `EnvironmentRead.status` (Pydantic-enforced), but the DB column is still `Column(String)`, so no DB constraint |
| `launch_history.py` target_type | `software_collection/environment` | ❌ bare strings, derived in `LaunchHistoryRead._derive_target_type`, untyped |
| `era_defaults.defaults_for_era()` | era→(emulator_slug, profile_era) | ❌ hardcoded `match/case`, bare strings (`era_defaults.py`) — one of three parallel era→emulator maps |
| Settings write endpoint | `PATCH /api/v1/settings` | ✅ allowlist-gated: `_USER_WRITABLE_KEYS`; `_SENSITIVE_KEYS` scrubbed from GET; `PIN_PEPPER`, `ALLOW_NETWORK_ACCESS`, `reset_db`, `rating_ordinals` all refused |
| Path inputs | scan/upload/library-path | ✅ `normalise_path` + allowlist against `LIBRARY_PATH`/`SOFTWARE_PATH`/`PROFILES_PATH` (per SECURITY.md); **exception:** Environment image paths intentionally unvalidated (Known Gap) |

**Net:** enforcement is strong at the HTTP request boundary (Pydantic +
settings allowlist + path allowlist) and weaker at the DB-persist boundary,
where `String` columns still carry no `CHECK` constraint. The previously-flagged
value-emit hole is closed: `file_type_from_path` now self-validates against
`FileType`, so the `bin/gdi/cdi/rom` case that used to persist silently would
now raise at emit time. What remains is structural — a producer that bypasses
that helper and writes an arbitrary string straight into a `String` column would
still not be rejected by the DB (see §6).

---

## 4. smart_media_detector call contract (current)

- **Location:** `backend/service/utils/smart_media_detector/`, zero `backend.*`
  imports (vendorable — TECH.md §Smart Scanner).
- **Entry signature:** `detect(path: Path) -> ScanResult` (`detector.py:51`).
  It takes **no allowed-value-set parameter** — the caller does not pass
  `EraValue`/`FileType` in. The detector emits bare era strings from its own
  internal vocabulary, plus era returns
  across `exe_detect.py` / `directory_detect.py` / `iso_detect.py`.
- **Result type:** `ScanResult` (`result.py`), including `requires_manual_boot`
  / `requires_install` flags.
- **Call sites (all lazy imports):**
  - `api/routes/software_collections.py`
  - `service/library/items.py`
  - `service/utils/drive_utils.py`
  - (`bios_placement.py` uses only `hashing.hash_lookup.hash_file`, not `detect`)
- **Contract consequence:** because the signature carries no vocabulary, the
  detector's output is only reconciled to `EraValue` at the DB/API boundary,
  never at emit time. This is intentional decoupling, but it means a
  detector-side era rename would not fail loudly against `constants.yaml`.

---

## 5. app_settings key inventory + call sites

Backed by `backend/service/utils/settings.py` (`_DEFAULTS` at `:46`, `_PATH_KEYS`
at `:59`) and persisted to the `app_settings` DB table via the `Settings` ORM
model (`backend/models/settings.py:8`). `settings.yaml` and
`%APPDATA%\Peach1UP\paths.yaml` have been removed — every key below, including
the 6 path keys, is DB-only now.

| Key | Class | Read/write sites |
| --- | --- | --- |
| `LIBRARY_PATH`, `SOFTWARE_PATH`, `MEDIA_PATH`, `OS_PATH`, `ROMS_PATH`, `PROFILES_PATH` | Path (static reference) | `main.py`, `uploads.py`, `software_collections.py`, scan allowlist; written via `set_path()` + `POST /settings/library-path` |
| `suppress_confirmations` | Operational flag | user-writable (`settings.py:64`); consumed by confirmation-token flow |
| `reset_db` | Operational flag (destructive) | **not** user-writable; startup only |
| `delete_media_on_removal` | Operational flag | user-writable; FE reads `Software/index.tsx`, `Settings/AdvancedTab.tsx` |
| `PIN_PEPPER` | **Secret** | dedicated route `PATCH /settings/pin-pepper`; scrubbed from GET; refused on generic PATCH (`settings.py:81`) |
| `THEGAMESDB_API_KEY` | **Secret** | user-writable via `AdvancedTab.tsx:32`; status-only GET `/settings/thegamesdb-api-key/status`; scrubbed from GET-all |
| `ALLOW_NETWORK_ACCESS` | Operational flag (security boundary) | read `main.py:57`, `security.py:47`, `auth.py:52`; **not** user-writable — no write site anywhere; now settable only by writing directly to the `app_settings` row (no hand-editable file exists any more) |
| `rating_ordinals` | Static reference data | `dependencies.py:39` `_load_rating_ordinals()` (falls back to `_BASE_RATING_ORDINALS`, derived by `_derive_rating_ordinals()` from `CONTENT_RATINGS`/`config/constants.yaml`'s `content_ratings` list — ordinal is index within each entry's `scheme` group, e.g. ESRB and PEGI each start their own ladder at 0); **not** user-writable — same DB-only caveat as above |
| `sandbox_{slug}_container_enabled` | Operational flag (per-emulator) | read `emulators.py:162`; written `emulators.py:457` via `set_flag`; default from TOML |
| `sandbox_{slug}_skip_memory_limit`, `sandbox_dosbox-x_skip_cpu_limit` | Operational flag (per-emulator) | same path as above; default from TOML |
| `SCAN_NAV_THRESHOLD_BYTES` | Operational flag | read `software_collections.py` (defaulted) |
| `first_run_complete` | (migrated to DB) | dropped from YAML state at load (`settings.py:102`) |

Secret handling reference: `_SENSITIVE_KEYS = {AI_API_KEY, IGDB_API_KEY,
PIN_PEPPER, THEGAMESDB_API_KEY}` (`settings.py:51`) are excluded from the
GET-all response.

---

## 6. Known SQLite / Enum limitation (concrete reference)

`backend/models/software.py` (`SoftwareItem`)
```python
file_type: Optional[FileType] = Field(default=None, sa_column=Column(String))
```
and (`SoftwareCollection`)
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
  Literal no longer accepts it — the mechanism behind the previously-reported
  read-time crash class.

This is a structural limitation of typing a `String` column with a Python
Literal, not a bug at any single line. Enforcing it would require a DB-level
`CHECK` constraint or a validator on the producer side.

---

## Flags (security / resource / structural)

- **No new security issue.** The material risks are all pre-documented:
  the Pipeline A/B regeneration split (§2) and the Environment-image-path traversal
  gap (SECURITY.md Known Gaps — intentionally unvalidated for NAS/secondary
  drives). The old unvalidated `media_type_from_path` output is now resolved —
  `file_type_from_path` validates against `FileType` at emit time (§3).
- **DB does not enforce generated Literals** (§6) — the remaining place a bad enum
  value could persist is a producer that bypasses the validating helper and writes
  straight to a `String` column.
- **`settings.yaml`/`paths.yaml` removed — resolved.** Secrets now live in
  `.env` exclusively and operational flags/paths now live in `app_settings`
  exclusively, matching the intended ownership model in §1.
- **New resource note:** `ALLOW_NETWORK_ACCESS`, `rating_ordinals`, and
  `SCAN_NAV_THRESHOLD_BYTES` were "hand-edit `settings.yaml`" only — that
  escape hatch is now gone with no replacement UI/API route, so changing
  them requires a direct write to the `app_settings` table (see §7).
- ~13 dead generated exports and 3 parallel era→emulator maps remain
  maintenance-drift surface (per TYPES_AUDIT.md §2/§6), not runtime bugs.

---

## 7. Settings Store — Resolved State (settings.yaml/paths.yaml → app_settings collapse, complete)

This section originally scoped a discovery-only audit for collapsing
`settings.yaml`/`paths.yaml` into `app_settings`. That collapse is now done —
`config/settings.yaml` and `%APPDATA%\Peach1UP\paths.yaml` have been deleted
from disk, and their load/write functions removed from
`backend/service/utils/settings.py`. This section reflects the resulting
architecture rather than the original discovery notes.

### 7.1 `backend/service/utils/settings.py` — module surface (file:line)

- `_DEFAULTS` (`:46`): `LIBRARY_PATH`, `SOFTWARE_PATH`, `MEDIA_PATH`, `OS_PATH`,
  `ROMS_PATH`, `PROFILES_PATH`, `suppress_confirmations`, `reset_db`,
  `delete_media_on_removal`, `UPLOAD_TMP_TTL_SECONDS`.
- `_PATH_KEYS` (`:62`): the 6 path keys above — normalised, resolved absolute
  at `init()` time, and stored in `app_settings` like every other key. No
  separate paths file exists any more.
- No `_USER_WRITABLE_KEYS`/`_SENSITIVE_KEYS` in this module — those two
  allowlists still live one layer up, in `backend/api/routes/settings.py`
  (`_SENSITIVE_KEYS:55`, `_USER_WRITABLE_KEYS:70`).
- Read/write primitives: `get()` (`:193`), `set_flag()` (`:202`),
  `add_suppression()`/`is_suppressed()` (`:217`/`:237`), `set_path()`
  (`:246`), `get_env_var()` (`:153`).
- Persistence: `_persist()` (`:93`) upserts a single key into the
  `app_settings` table through the shared SQLAlchemy engine
  (`backend.core.database.get_engine()`) and the `Settings` ORM model
  (`backend/models/settings.py:8`) — no raw SQL, no YAML I/O of any kind.
  `_load_all_rows()` (`:79`) reads the whole table the same way.

### 7.2 Key classification — now uniform

Every key listed in §5 is DB-only, in the single `app_settings` table. There
is no YAML-backed key any more, no `paths.yaml` overlay, and no key that must
be reconciled between two stores — the YAML-vs-DB divergence TYPES.md §1
used to flag is gone. The one remaining split is deliberate, not a
divergence: the 4 secret-class keys (`PIN_PEPPER`, `THEGAMESDB_API_KEY`,
`AI_API_KEY`, `IGDB_API_KEY`) are kept out of `app_settings` and live in
`.env` instead (§7.3) — a secret must not round-trip through the same SQLite
file the `reset_db` dev flag can delete.

One operational consequence of the removal: `ALLOW_NETWORK_ACCESS`,
`rating_ordinals`, and `SCAN_NAV_THRESHOLD_BYTES` previously had no
programmatic write path and were "hand-edit `config/settings.yaml`" only.
That escape hatch is now gone with no replacement UI/API route — changing
any of these three today requires a direct write to the `app_settings`
table (e.g. via a script), not a config-file edit.

### 7.3 Secrets — `.env`, mechanism unchanged by the collapse

- `PIN_PEPPER` — single dedicated route (`PATCH /settings/pin-pepper`),
  refused on the generic PATCH, scrubbed from `GET /settings`
  (`_SENSITIVE_KEYS`).
- `THEGAMESDB_API_KEY` — user-writable via generic PATCH (`AdvancedTab.tsx:32`
  → `_USER_WRITABLE_KEYS`); scrubbed from GET; status-only endpoint
  (`/thegamesdb-api-key/status`).
- `AI_API_KEY` / `IGDB_API_KEY` — still dead secret surface: both are in
  `_SENSITIVE_KEYS` and `_USER_WRITABLE_KEYS` (writable + scrubbed) but **no
  code anywhere reads either key**, in `backend/` or `frontend/src`. Not a
  leak, but a user can be led to believe setting these does something when
  nothing consumes them. Unresolved carryover from the pre-collapse audit,
  independent of the YAML removal — worth resolving (wire up a consumer or
  remove the allowlist entries) on its own.
- `get_env_secret()`/`set_env_secret()` (`backend/service/utils/env_secrets.py`)
  are the only read/write path for all four keys. No secret ever touches
  `app_settings`.

### 7.4 `app_settings` table (DB) — full consumer list

Definition: `backend/models/settings.py:8` (`Settings`, table `app_settings`,
columns `key`/`value`/`updated_at`) and `:19` (`SettingsPatch`, a generic
`{updates: dict}` Pydantic body used by the generic PATCH endpoint — the name
overlap with the `Settings` DB model is coincidental, not a coupling).

Every key now round-trips through this table via `_load_all_rows()`/
`_persist()` (`settings.py:79`/`:93`) — not just `first_run_complete` as
before the collapse. `first_run_complete` itself is still handled the same
way it always was: `backend/api/routes/settings.py` (`GET /first-run-status`,
`POST /complete-first-run`) and `backend/core/startup_tasks.py`
(`_sync_first_run_from_db`).

### 7.5 Table-creation / seed flow (updated for the T1/T6 engine-sharing fix)

- `ensure_settings_table()` (`backend/core/database.py`) creates just the
  `app_settings` table at T1 (import time, inside `settings.init()`, called
  from `main.py` before the FastAPI app is built) — scoped narrowly enough to
  run before the rest of `backend.models.*` has registered with
  `SQLModel.metadata`.
- `create_tables()` (`backend/core/database.py`, invoked from `lifespan.py`)
  still runs the full `SQLModel.metadata.create_all()` at T6 (ASGI startup) —
  a no-op for `app_settings` since it already exists by then. Plain
  `create_all`, no Alembic (matches CLAUDE.md stack notes).
- The legacy-migration seed step (`_migrate_legacy_config_into_db()`) has
  been deleted along with `settings.yaml`/`paths.yaml`. `init()` no longer
  does an empty-table check to trigger a one-time migration — there is
  nothing left to migrate from.

---

## 8. Era → emulator coverage (8 wired emulators, current state)

Cross-referenced `config/constants.yaml` (`eras`, `backend_slugs`,
`backend_system_labels`) against `era_defaults.defaults_for_era()`,
`startup_seed.py`, and the smart detector's era
branches. All 11 non-`unknown` eras in `constants.yaml`'s `eras` map route
to one of the 8 wired emulators — there is currently **no** era or
ROM-shaped format that is detectable but has no backend:

| Era | Emulator | ROM/BIOS required |
| --- | --- | --- |
| dos | dosbox-x | No |
| win95, win98, winxp | 86box | Yes (86Box ROM pack) |
| ps1 | duckstation | Yes (PS1 BIOS) |
| ps2 | pcsx2 | Yes (PS2 BIOS) |
| xbox | xemu | Yes (Xbox BIOS) |
| nes | mesen | No |
| snes | mesen | No |
| n64 | project64 | No |
| dreamcast | flycast | Yes (DC BIOS) |

> **`win31` (Windows 3.1) has been removed** from `constants.yaml`'s `eras`
> map — `EraValue` no longer lists it, so DOSBox-X now backs `dos` only. Docs
> that still mention a Windows 3.1 era are stale. Flagged in the reconciliation
> summary in case the removal was not intended.

**SNES is not unresolved** — `era_defaults.py` (`case "snes": return
("mesen", "snes")`), `startup_seed.py` (`supported_eras: ["nes", "snes"]`),
and the smart detector (era=`"snes"` on `.sfc`/`.smc`/etc.) all route it to
Mesen identically to NES. The earlier label inconsistency is resolved:
`constants.yaml`'s `backend_system_labels.mesen` now reads `"NES, SNES"`.

**No GBA, GB/GBC, or Genesis/32X detection exists anywhere in the
codebase today** — not in `constants.yaml`'s `eras` map, not in
`ERA_MEDIA_TYPES` (`backend/constants.py:24`), not as an era branch in
`smart_media_detector` (`detector.py`, `iso_detect.py`, `exe_detect.py`,
`directory_detect.py`). These formats are neither detected nor backed;
they are simply absent from scope, not a detected-without-a-backend gap.
(This section was originally scoped to document such a gap for GBA/GB-GBC/
Genesis-32X as detectable-but-backend-less and SNES as unresolved — neither
premise held up against the current code, so this documents actual state
instead.)

---

**Summary:** the settings.yaml → DB collapse is complete. `app_settings` now
holds every operational flag, per-emulator sandbox override, and path key;
secrets remain in `.env` by design (§7.3). The two items worth resolving
independently of the collapse, carried forward unchanged from the original
discovery: the dead `AI_API_KEY`/`IGDB_API_KEY` secret surface (§7.3), and
the DB's lack of Literal enforcement (§6).
