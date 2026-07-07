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
| API/domain constants (era, media_type, hardware_profile, install_type, tag color, ratings, backend/system labels) | `constants.yaml` | `config/constants.yaml` → `scripts/gen_constants.py` → `backend/constants_generated.py` + `frontend/src/generated/constants.ts` | ✅ matches (Pipeline A). |
| DB schema structure | DB | SQLModel models, `create_all()` on startup, no Alembic | ⚠️ **Columns are bare `String`, not enum-constrained** — the Literal types are Pydantic-only and are *not* enforced at the DB layer (see §6). |
| FE types | OpenAPI/Pydantic generated | FastAPI → `shared/openapi.json` (startup) → `openapi-typescript` → `shared/types.ts` | ✅ matches (Pipeline B), but B is **downstream of A** — every Pydantic field typed with a generated Literal re-inlines that enum into OpenAPI. |
| Secrets | `.env` | **`settings.yaml`** holds live secrets today (`THEGAMESDB_API_KEY`, `PIN_PEPPER`); `.env` is a legacy override only | ⚠️ Divergence: `.env` is documented as the secrets home but the actual secret values sit in `settings.yaml`. Both are gitignored. |
| Operational flags | "Settings DB table" | **`config/settings.yaml`** via `backend/service/utils/settings.py` — there is **no settings DB table** | ⚠️ Divergence: operational flags are YAML-backed, not DB-backed. Only `first_run_complete` was moved to the DB (`settings.py:102` drops it from YAML state). Path keys additionally persist to `%APPDATA%\Peach1UP\paths.yaml`. |

**Bottom line:** the constants pipeline (A), the OpenAPI pipeline (B), and the
TOML→catalog-slug pipeline match the intended model. The two real divergences
are (a) secrets/flags live in `settings.yaml`, not `.env`/a DB table, and
(b) the DB does not enforce the generated Literals — columns are `String`.

---

## 2. The actual pipeline as it exists in code

**Pipeline A — constants → generated types**
```
config/constants.yaml
  └─ scripts/gen_constants.py  (run manually / by build scripts, no hook)
       ├─ backend/constants_generated.py   (Era, EraValue, MediaType,
       │                                     HardwareProfile, InstallType,
       │                                     TagColor, BackendSlug, label dicts)
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
same enum sourced at different times. `media_type` is the canonical example —
the generated `MediaType` union is **dead** (0 FE imports); the FE reads
`media_type` exclusively via `@shared/types` (the OpenAPI copy). Nothing
mechanically enforces co-regeneration (no CI/pre-commit — see TESTING.md).

---

## 3. Validation state at each boundary (enforced today vs. not)

| Boundary | Value | Enforced? |
| --- | --- | --- |
| `constants_generated.py` Literals | Era, MediaType, InstallType, HardwareProfile, TagColor | ✅ static-type only (mypy/pyright); no runtime guard |
| Pydantic request/response models | fields typed `EraValue`, `Optional[MediaType]`, etc. | ✅ FastAPI validates request bodies against the inlined enum; response models validated on serialization |
| **DB column** | `LibraryItem.media_type`, `LibraryItem.era` | ❌ **`Column(String)`** — any string persists; the Literal is not a DB constraint (`models/library.py:42`, `:108`) |
| `media_type_from_path()` producer | returns `iso/cue/chd/floppy/hdd/exe/directory/unknown` **plus `bin/gdi/cdi/rom`** | ❌ bare strings; `bin`, `gdi`, `cdi`, `rom` are **not in the `MediaType` Literal** (`era_media.py:42`) — live drift |
| `smart_media_detector.detect()` era output | bare era strings | ❌ validated against `EraValue` only at the DB/API boundary, never at emit time (by design — see §4) |
| `environments.py` platform status | `healthy/degraded/unconfigured/error/ok/missing` | ❌ bare strings, no Literal/constant; `PlatformRead.status` is plain `str` (`environments.py:88–112`) |
| `launch_history.py` target_type | `library_collection/environment` | ❌ bare strings, derived in read model, untyped (`launch_history.py:54–61`) |
| `era_defaults.defaults_for_era()` | era→(emulator_slug, profile_era) | ❌ hardcoded `match/case`, bare strings (`era_defaults.py:8`) — one of three parallel era→emulator maps |
| Settings write endpoint | `PATCH /api/v1/settings` | ✅ allowlist-gated: `_USER_WRITABLE_KEYS` (`settings.py:60`); `_SENSITIVE_KEYS` scrubbed from GET; `PIN_PEPPER`, `ALLOW_NETWORK_ACCESS`, `reset_db`, `rating_ordinals` all refused |
| Path inputs | scan/upload/library-path | ✅ `normalise_path` + allowlist against `LIBRARY_PATH`/`PROFILES_PATH` (per SECURITY.md); **exception:** platform image paths intentionally unvalidated (Known Gap) |

**Net:** enforcement is strong at the HTTP request boundary (Pydantic +
settings allowlist + path allowlist) and weak-to-absent at the value-emit and
DB-persist boundaries. The one place a Literal violation can silently persist
is a producer (`media_type_from_path`) writing `bin/gdi/cdi/rom` into a
`String` column typed as `MediaType`.

---

## 4. smart_media_detector call contract (current)

- **Location:** `backend/service/utils/smart_media_detector/`, zero `backend.*`
  imports (vendorable — TECH.md §Smart Scanner).
- **Entry signature:** `detect(path: Path) -> ScanResult` (`detector.py:51`).
  It takes **no allowed-value-set parameter** — the caller does not pass
  `EraValue`/`MediaType` in. The detector emits bare era strings from its own
  internal vocabulary (`detector.py:23` `{"dos","win31"}`, plus era returns
  across `exe_detect.py` / `directory_detect.py` / `iso_detect.py`).
- **Result type:** `ScanResult` (`result.py`), including `requires_manual_boot`
  / `requires_install` flags.
- **Call sites (5, all lazy imports):**
  - `api/routes/library_collections.py:234`
  - `service/library/items.py:99`, `:496`
  - `service/utils/drive_utils.py:71`
  - (`bios_placement.py:23` uses only `hashing.hash_lookup.hash_file`, not `detect`)
- **Contract consequence:** because the signature carries no vocabulary, the
  detector's output is only reconciled to `EraValue` at the DB/API boundary,
  never at emit time. This is intentional decoupling, but it means a
  detector-side era rename would not fail loudly against `constants.yaml`.

---

## 5. settings.yaml key inventory + call sites

Backed by `backend/service/utils/settings.py` (`_DEFAULTS` at `:35`, `_PATH_KEYS`
at `:51`). There is **no settings DB table**; path keys additionally mirror to
`%APPDATA%\Peach1UP\paths.yaml`.

| Key | Class | Read/write sites |
| --- | --- | --- |
| `LIBRARY_PATH`, `MEDIA_PATH`, `OS_PATH`, `ROMS_PATH`, `PROFILES_PATH` | Path (static reference) | `main.py:50`, `uploads.py:52`, `library_collections.py:145`, scan allowlist; written via `set_path()` (`settings.py:267`) + `POST /settings/library-path` |
| `suppress_confirmations` | Operational flag | user-writable (`settings.py:64`); consumed by confirmation-token flow |
| `reset_db` | Operational flag (destructive) | **not** user-writable; startup only |
| `delete_media_on_removal` | Operational flag | user-writable; FE reads `Library/index.tsx:99`, `Settings/AdvancedTab.tsx:219/227` |
| `PIN_PEPPER` | **Secret** | dedicated route `PATCH /settings/pin-pepper`; scrubbed from GET; refused on generic PATCH (`settings.py:81`) |
| `THEGAMESDB_API_KEY` | **Secret** | user-writable via `AdvancedTab.tsx:32`; status-only GET `/settings/thegamesdb-api-key/status`; scrubbed from GET-all |
| `ALLOW_NETWORK_ACCESS` | Operational flag (security boundary) | read `main.py:57`, `security.py:47`, `auth.py:52`; **not** user-writable |
| `rating_ordinals` | Static reference data | `dependencies.py:40` `_load_rating_ordinals()` (falls back to `_DEFAULT_RATING_ORDINALS`); **not** user-writable |
| `sandbox_{slug}_container_enabled` | Operational flag (per-emulator) | read `emulators.py:162`; written `emulators.py:457` via `set_flag`; default from TOML |
| `sandbox_{slug}_skip_memory_limit`, `sandbox_dosbox-x_skip_cpu_limit` | Operational flag (per-emulator) | same path as above; default from TOML |
| `SCAN_NAV_THRESHOLD_BYTES` | Operational flag | read `library_collections.py:175` (defaulted) |
| `first_run_complete` | (migrated to DB) | dropped from YAML state at load (`settings.py:102`) |

Secret handling reference: `_SENSITIVE_KEYS = {AI_API_KEY, IGDB_API_KEY,
PIN_PEPPER, THEGAMESDB_API_KEY}` (`settings.py:51`) are excluded from the
GET-all response.

---

## 6. Known SQLite / Enum limitation (concrete reference)

`backend/models/library.py:42`
```python
media_type: Optional[MediaType] = Field(default=None, sa_column=Column(String))
```
and `:108`
```python
era: EraValue = Field(sa_column=Column(String, nullable=False))
```

The generated `MediaType` / `EraValue` Literals are applied as the **Pydantic**
field type, but the underlying SQLite column is a bare `String`. SQLModel/SQLite
do not enforce the Literal as a `CHECK` constraint or native enum. Therefore:

- A producer that emits an out-of-vocabulary value (e.g.
  `media_type_from_path()` returning `bin`/`gdi`/`cdi`/`rom`, `era_media.py:42`)
  will **persist successfully** to the DB.
- The mismatch only surfaces later on the *read* side when the value is
  serialized back through a Pydantic model whose Literal no longer accepts it —
  the mechanism behind the previously-reported `chd`/`rom` read-time crash class.

This is a structural limitation of typing a `String` column with a Python
Literal, not a bug at any single line. Enforcing it would require a DB-level
`CHECK` constraint or a validator on the producer side.

---

## Flags (security / resource / structural)

- **No new security issue.** The material risks are all pre-documented:
  the Pipeline A/B regeneration split (§2), the unvalidated
  `media_type_from_path` output (§3), and the platform-image-path traversal
  gap (SECURITY.md Known Gaps — intentionally unvalidated for NAS/secondary
  drives).
- **DB does not enforce generated Literals** (§6) — the one place a bad enum
  value can silently persist.
- **Secrets live in `settings.yaml`, not `.env`** — divergence from the stated
  ownership model; both files are gitignored, so not an exposure, but worth
  noting for the SSOT map.
- ~13 dead generated exports and 3 parallel era→emulator maps remain
  maintenance-drift surface (per TYPES_AUDIT.md §2/§6), not runtime bugs.

---

## 7. Settings Consumer Inventory (discovery for settings.yaml → DB collapse)

Full re-walk of every `settings.yaml` and `app_settings` (DB) consumer, done to
scope a future collapse of the two mechanisms into one. Discovery only — no
code changed.

### 7.1 `backend/service/utils/settings.py` — module surface (file:line)

- `_DEFAULTS` (`:35`): `LIBRARY_PATH`, `MEDIA_PATH`, `OS_PATH`, `ROMS_PATH`,
  `PROFILES_PATH`, `suppress_confirmations`, `reset_db`,
  `delete_media_on_removal`, `PIN_PEPPER`.
- `_PATH_KEYS` (`:51`): the 5 path keys above — normalised to forward slashes,
  resolved absolute, and diverted to `paths.yaml` (see §7.4) instead of
  `settings.yaml`.
- No `_USER_WRITABLE_KEYS` or `_SENSITIVE_KEYS` in this module — those two
  allowlists live one layer up, in `backend/api/routes/settings.py:51,60`
  (`_SENSITIVE_KEYS`, `_USER_WRITABLE_KEYS`), not in `settings.py` itself.
  TYPES.md §5 previously implied all four allowlists are co-located; they are
  not — worth correcting if this doc is cited elsewhere.
- Read/write primitives: `get()` (`:214`), `set_flag()` (`:223`),
  `add_suppression()`/`is_suppressed()` (`:238`,`:258`), `set_path()` (`:267`),
  `get_env_var()` (`:173`).
- Persistence: `_save()` (`:359`) writes everything except `_`-prefixed keys
  and `_PATH_KEYS` to `config/settings.yaml`, atomically (tmp file + rename).
  `_save_paths()` (`:387`) writes `_PATH_KEYS` to
  `%APPDATA%\Peach1UP\paths.yaml` (or `~/.config/Peach1UP` off Windows),
  atomically, separately.

### 7.2 Every settings.yaml-backed key, with all call sites

| Key | Class | Default | Read sites | Write sites |
| --- | --- | --- | --- | --- |
| `LIBRARY_PATH`, `MEDIA_PATH`, `OS_PATH`, `ROMS_PATH`, `PROFILES_PATH` | Path | computed under project root (`_PATH_DEFAULTS:61`) | `main.py:50`, `media.py:55` (`get_env_var`), `uploads.py:52` (`get_env_var`), `library_collections.py:145`, `filesystem.py:19,88-92`, `models/library.py:85`, `service/library/enrich.py:42`, `service/library/items.py:104,593`, `startup_tasks.py:154`, `api/routes/settings.py:205-209` | `set_path()` via `PATCH /api/v1/settings` (routed keys) and `POST /settings/library-path` (`settings.py:236`) |
| `suppress_confirmations` | Operational flag | `[]` | `is_suppressed()` (`settings.py:258`) — grep found **no call site** for `is_suppressed()` outside its own definition; only `add_suppression()`/`set_flag` write paths are exercised. Confirmation-token flow (`test_confirmation_tokens`) appears to gate elsewhere. | `add_suppression()` (`settings.py:238`); user-writable via generic PATCH (`api/routes/settings.py:64`) |
| `reset_db` | Operational flag (destructive) | `False` | `lifespan.py:48` | `lifespan.py:53` (cleared immediately after use); **not** user-writable (absent from `_USER_WRITABLE_KEYS`) |
| `delete_media_on_removal` | Operational flag | `False` | `service/library/items.py:639` (gates media deletion on library-item removal) | user-writable (`api/routes/settings.py:65`) |
| `PIN_PEPPER` | **Secret** | `""` | `pin_hashing.py` (via `patch_pin_pepper`), `api/routes/settings.py:151` | dedicated route only: `PATCH /settings/pin-pepper` (`:124`); refused on generic PATCH (`:81`) |
| `THEGAMESDB_API_KEY` | **Secret** | not in `_DEFAULTS` (falls through to `get()`'s `default=None`) | `service/thegamesdb_client.py:22` | user-writable via generic PATCH (`AdvancedTab.tsx:32` → `_USER_WRITABLE_KEYS`) |
| `AI_API_KEY`, `IGDB_API_KEY` | **Secret** (declared) | not in `_DEFAULTS` | **none found** — no backend consumer reads either key anywhere in `backend/` or `frontend/src` beyond the allowlists themselves (`api/routes/settings.py:51,62-63`). These are write-and-scrub-only: a user can PATCH them in and they'll never be read. Flagged below. | user-writable (`api/routes/settings.py:62-63`) |
| `ALLOW_NETWORK_ACCESS` | Operational flag (security boundary) | not in `_DEFAULTS`, defaults `False` at call site | `security.py:47`, `main.py:57`, `auth.py:52` | **not** user-writable — no write site found anywhere (must be hand-edited into `settings.yaml`) |
| `rating_ordinals` | Static reference data | not in `_DEFAULTS`; falls back to `_DEFAULT_RATING_ORDINALS` (`dependencies.py:16`) | `dependencies.py:40,60,80,186` | **not** user-writable; no write site found — hand-edit only |
| `sandbox_{slug}_container_enabled`, `sandbox_{slug}_skip_memory_limit`, `sandbox_{slug}_skip_cpu_limit` | Operational flag (per-emulator) | from TOML (`emulator_catalog.py:306,316,332`) | `emulator_catalog.py:306,316,332` | `emulators.py:457` via `set_flag()`, looped over `("container_enabled","skip_cpu_limit","skip_memory_limit")` (`emulators.py:160`) |
| `SCAN_NAV_THRESHOLD_BYTES` | Operational flag | `DEFAULT_SCAN_NAV_THRESHOLD_BYTES = 1 GiB` (`upload_utils.py:25`) | `library_collections.py:175-178` | **no write site found** — hand-edit only |
| `UPLOAD_TMP_TTL_SECONDS` | Operational flag | `DEFAULT_UPLOAD_TMP_TTL_SECONDS = 24h` (`upload_utils.py:26`) | `startup_tasks.py:157` | **no write site found** — hand-edit only; **not previously listed in TYPES.md §5** |
| `first_run_complete` | migrated to DB | — | dropped from YAML state at load (`settings.py:102`) | never written to YAML (DB-only, see §7.3) |

**New keys found beyond the TYPES.md §5 inventory:** `AI_API_KEY`,
`IGDB_API_KEY` (declared/writable but dead), `UPLOAD_TMP_TTL_SECONDS`
(consumed, undeclared, no default in `_DEFAULTS`), and confirmation that
`ALLOW_NETWORK_ACCESS`, `rating_ordinals`, `SCAN_NAV_THRESHOLD_BYTES` have
**no write path at all** — they are read-only from the app's perspective and
can currently only be set by hand-editing `config/settings.yaml` directly.

### 7.3 `app_settings` table (DB) — full consumer list

Definition: `backend/models/settings.py:8` (`Settings`, table `app_settings`,
columns `key`/`value`/`updated_at`) and `:19` (`SettingsPatch`, a generic
`{updates: dict}` Pydantic body — currently used only by the YAML-backed
generic PATCH endpoint, **not** by the `Settings` DB model at all; the name
overlap between `SettingsPatch` and the DB `Settings` table is coincidental,
not a coupling).

Every reference to the `Settings` DB model, repo-wide:

- `backend/models/__init__.py:15` — re-export.
- `backend/api/routes/settings.py:194,196` — `GET /first-run-status` reads
  the row.
- `backend/api/routes/settings.py:245-251` — `POST /complete-first-run`
  upserts the row (`value="true"`).
- `backend/core/startup_tasks.py:13-16` (`_sync_first_run_from_db`) — reads
  the row at startup and calls `set_first_run_complete()` (an in-memory flag
  in `security.py`, not a settings.yaml write) if true.

**Confirmed: `first_run_complete` is the only key ever written to or read
from `app_settings`.** No other route, service, or startup task touches the
`Settings` model. Grepped for `SettingsModel`, `db.get(SettingsModel`,
`db.query(SettingsModel` — zero hits outside the four sites above.

### 7.4 Key classification — YAML-only / DB-only / both

- **DB-only:** `first_run_complete`. Sole occupant of `app_settings`.
- **YAML-only:** every other key in §7.2 (all path keys, flags, secrets,
  per-emulator sandbox flags, thresholds). None of them have any DB-table
  presence — there is no overlap/collision case today. "Which one wins" is
  moot because no key is routed through both; the divergence TYPES.md §1
  already flagged (operational flags in YAML, not DB) is total, not partial.
- **Neither (hand-edit only):** `ALLOW_NETWORK_ACCESS`, `rating_ordinals`,
  `SCAN_NAV_THRESHOLD_BYTES`, `UPLOAD_TMP_TTL_SECONDS` — these are read from
  YAML state but have no programmatic write path; they only take a
  non-default value if someone edits `config/settings.yaml` by hand.

### 7.5 `%APPDATA%\Peach1UP\paths.yaml` — separate mechanism, confirmed

- **Write sites:** `settings.py:139-157` (first-run generation, from
  `_PATH_DEFAULTS`, only if the file doesn't exist yet) and `_save_paths()`
  (`settings.py:387`, invoked by every `set_path()` call).
  `settings.py:267` (`set_path`) is the only public entry point that reaches
  `_save_paths()`.
- **Read site:** `settings.py:123-137`, during `init()`, layered **on top of**
  whatever `settings.yaml`/`_PATH_DEFAULTS` already resolved for each of the 5
  `_PATH_KEYS` — `paths.yaml` values win if present and non-empty.
- **Relationship to settings.yaml:** it is a genuinely separate file (separate
  directory, separate atomic-write routine, separate schema — only the 5 path
  keys), but it **shares the same key vocabulary and the same in-memory
  `_state` dict** as `settings.yaml` once `init()` completes — from every
  caller's perspective (`get()`, `get_env_var()`) there is one merged state,
  and only `_save()` vs `_save_paths()` (both private) know which file a given
  key round-trips through. A collapse to a single settings store would need
  to either fold `paths.yaml` in or explicitly preserve it as the
  machine-local override layer it currently is (its stated purpose — per-
  install paths that shouldn't live in a shared/committed `settings.yaml`).

### 7.6 Table-creation / seed flow

- `backend/core/database.py:38` — `SQLModel.metadata.create_all(bind=_ENGINE)`,
  called from `create_tables()`, invoked once at `lifespan.py:55`. Plain
  `create_all`, no Alembic (matches CLAUDE.md stack notes).
- **No seed step populates `app_settings`.** Grepped `startup_migrations.py`
  and `startup_seed.py` for `Settings`/`app_settings` — zero hits. The table
  is created empty on every fresh DB and only gains a row the first time
  `POST /complete-first-run` is called (or, on an existing DB, whatever was
  already committed there previously).

### 7.7 Where secrets touch either mechanism (security-relevant — read first)

- **`PIN_PEPPER`** — YAML-only, single dedicated route
  (`PATCH /settings/pin-pepper`), refused on the generic PATCH, scrubbed from
  `GET /settings` (`_SENSITIVE_KEYS`). No DB involvement. Consistent with
  TYPES.md §1/§5.
- **`THEGAMESDB_API_KEY`** — YAML-only, live value currently present in
  `config/settings.yaml` on this checkout (gitignored, confirmed via repo
  read — not reproduced here). Read by `thegamesdb_client.py:22`. Scrubbed
  from `GET /settings`; status-only endpoint exists
  (`/thegamesdb-api-key/status`). Matches TYPES.md §5.
- **`AI_API_KEY` / `IGDB_API_KEY` — flag: dead secret surface.** Both are in
  `_SENSITIVE_KEYS` (scrubbed from GET, so the intent to treat them as
  secrets is real) and in `_USER_WRITABLE_KEYS` (a `can_edit_settings` user
  can PATCH a value in), but **no code anywhere reads either key** — not in
  `backend/`, not in `frontend/src`. This is not a leak (they're write-only
  and still scrubbed on read), but it means: (a) a user can be led to believe
  setting these keys does something, when nothing consumes them, and (b) if
  a future feature adds a reader for one of these without re-auditing the
  write/scrub path, that's the point a latent secret-handling assumption
  gets exercised for the first time untested. Worth resolving one way
  (wire up a consumer) or the other (remove the dead allowlist entries)
  before any settings.yaml→DB collapse, so the collapse doesn't have to
  carry forward dead secret plumbing.
- **`.env` vs `settings.yaml` for secrets** — reconfirms TYPES.md §1: `.env`
  is documented as the secrets home (`.env.template`) but holds no secrets
  in practice; `PEACH_ENV`/`CORS_ORIGIN`/`DOCS_BASE_URL` are its only
  documented keys, none sensitive. All four secret-class keys
  (`PIN_PEPPER`, `THEGAMESDB_API_KEY`, `AI_API_KEY`, `IGDB_API_KEY`) route
  through `settings.yaml`/`_SENSITIVE_KEYS` exclusively, not `.env`.
- **No secret ever touches `app_settings` (DB).** The only DB-resident
  settings value is `first_run_complete: "true"`, a non-sensitive boolean
  string.

---

**Summary for the settings.yaml → DB collapse:** the collapse has one clean
side and one non-trivial side. Clean: `app_settings` today holds exactly one
key (`first_run_complete`) with 4 call sites total, so absorbing it into a
unified store costs nothing to reason about. Non-trivial: `settings.yaml`
carries ~20 keys across 5 classes (paths, flags, secrets, per-emulator
sandbox flags, thresholds), a parallel `paths.yaml` machine-local override
file that shares the same in-memory state but writes to a different
location, and 4 keys (`AI_API_KEY`, `IGDB_API_KEY`, `ALLOW_NETWORK_ACCESS`,
`rating_ordinals`, `SCAN_NAV_THRESHOLD_BYTES`, `UPLOAD_TMP_TTL_SECONDS`) with
no programmatic write path today (hand-edit only) that a DB-backed model
would need an explicit decision on (expose a write route, or keep them
config-file/env-only by design). The two dead secret keys (`AI_API_KEY`,
`IGDB_API_KEY`) are the one item worth resolving *before* the collapse
rather than carrying forward. No fixes applied; no files edited outside this
document.
