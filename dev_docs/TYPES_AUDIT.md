  Type / Constant Source Inventory — Full Stack

  Summary of the two pipelines (and how they actually relate)

  - Pipeline A — config/constants.yaml → scripts/gen_constants.py →
  backend/constants_generated.py and frontend/src/generated/constants.ts (two
  outputs, one generator, run manually / by build scripts).
  - Pipeline B — FastAPI app → shared/openapi.json (written at startup) →
  openapi-typescript → shared/types.ts (consumed as @shared/types).
  - They are not independent for shared concepts — B is downstream of A. Every
  Pydantic field typed with a generated Literal (media_type:
  Optional[MediaType], era: EraValue, hardware_profile, install_type, tag
  color, emulator_slug) causes openapi.json to inline the exact same enum
  (confirmed: openapi media_type =
  [directory,iso,cue,chd,floppy,hdd,exe,unknown], identical to constants.yaml).
  So A and B agree by construction — but only after both are regenerated. They
  drift whenever constants.yaml is regenerated but the backend isn't restarted
  to re-emit openapi/types (or vice versa), because the frontend then holds
  two copies (generated/constants.ts and types.ts) sourced at different times.
  This is the structural drift risk, and it is why the prior chd/rom bugs
  surfaced on the read side.

  ---
  Point 1 — Every Literal / Enum / TypedDict / string-union, classified

  Backend Literals/Enums (non-generated):
  - backend/core/jobs.py:17-18 JobKind,JobStatus Literal — (c) hand-written,
  independent.
  - backend/core/install_registry.py:6 InstallStatus Literal — (c)
  hand-written; surfaces in openapi as EmulatorStatusData.status enum (feeds B,
  not A).
  - backend/api/routes/uploads.py:45 kind Literal — (c) hand-written (openapi
  InitBody.kind).
  - backend/api/routes/settings.py:42 key Literal — (c) hand-written (openapi
  LibraryPathBody.key).
  - backend/api/routes/library_metadata.py:34 &
  backend/service/library/enrich.py:89 entity_type Literal — (c) hand-written,
  declared twice (d, duplicate of each other).
  - backend/service/utils/platform/windows/sandbox/sandbox_config.py:10-11
  access,mode Literal — (c) internal sandbox, independent.
  - sandbox_event.py:7,14 SandboxEvent,SandboxStage;
  sandbox_checker/results.py:7 CheckStatus — (c) internal Enums, independent.
  - Backend TypedDict: none.

  Backend generated (Pipeline A): Era, EraValue, BackendSlug, MediaType,
  EmulatorCatalogSlug, HardwareProfile, TagColor, InstallType + label dicts —
  (a).

  Backend implicit (untyped) string enums — no Literal, no constant:
  - backend/service/platforms/environments.py:84-112 platform status =
  healthy|degraded|unconfigured|error|ok|missing — (c) hardcoded, not typed
  anywhere; PlatformRead.status/PlatformHealthCounts are plain str.
  - backend/models/launch_history.py:57-61 target_type =
  library_collection|environment — (c) hardcoded.
  - backend/service/utils/xbox_image.py xiso|dvd_rip|iso9660|unknown — (c)
  internal format tag.

  Frontend string-unions (non-generated):
  - frontend/src/components/common/EraSelector.tsx:1 EraValue union — (d)
  duplicate of generated Era, already drifted (missing 'unknown').
  - frontend/src/types/era.ts
  ERA_LABEL/ERA_COLOR/ERA_PLACEHOLDER/EMULATOR_ERA_MAP — (d) parallel
  hand-maintained era label/color/emulator maps, drifted (labels "WIN31" vs
  generated "Windows 3.1", no unknown).
  - frontend/src/pages/Environments/EnvironmentModal.tsx:9 PCEra — (d)
  hand-written era subset.
  - frontend/src/ui/StatusBadge.tsx:3 Status='ok'|'missing'|'error'|'unknown' —
  (c/d) drifted vs platform status (no healthy|degraded|unconfigured);
  component itself only referenced by its test.
  - frontend/src/pages/Emulators/components/EmulatorDetailPrimitives.tsx:1,
  Settings/index.tsx:7, ProfileDetail.tsx:21,
  Environments/EnvironmentDetail.tsx:14 Tab unions; ui/Button.tsx Variant/Size;
  lib/logger.ts Level; context/_AppContext.ts Theme — (c) local UI unions,
  independent, not API concepts.

  ---
  Point 2 — Dead generated exports

  Backend constants_generated.py — generated but 0 backend imports: ERA_LABELS,
  BACKEND_LABELS, BACKEND_SYSTEM_LABELS, CONTENT_RATINGS,
  DGVOODOO2_SUPPORTED_ERAS, HARDWARE_PROFILE_LABELS, TAG_COLOR_HEX (all
  label/display maps — only the frontend consumes labels; backend never does).
  7 dead exports.

  Frontend generated/constants.ts — generated but 0 app imports:
  BACKEND_LABELS, BACKEND_SYSTEM_LABELS, BACKEND_SLUGS, BackendSlug,
  HARDWARE_PROFILE_LABELS, and MediaType (the frontend types media_type
  exclusively via @shared/types, never the generated union). 6 dead exports.

  Net: the generator emits ~13 names that nothing consumes. Every
  used-elsewhere name is still live (Era/EraValue, ERA_LABELS,
  EmulatorCatalogSlug, TagColor, TAG_COLOR_HEX (FE), HardwareProfile,
  InstallType, RATING_OPTIONS, DGVOODOO2_SUPPORTED_ERAS,
  EMULATOR_CATALOG_SLUGS).

  ---
  Point 3 — types.ts consumption vs hand-written duplicates

  @shared/types (openapi) is heavily consumed — ~40 files use
  components['schemas'][X] (UserRead, ProfileRead, PlatformRead,
  CatalogEntryResponse, LaunchHistoryRead, TagRead, LibraryCollectionRead,
  etc.). It is the real API-type source.

  Hand-written frontend types that duplicate an existing types.ts schema:
  - frontend/src/components/common/FileBrowser.tsx:7-24
  DriveEntry,DirEntry,FileEntry,BrowseResult — duplicate openapi
  DriveEntry/DirEntry/FileEntry/BrowseResult.
  - frontend/src/pages/PlatformHealth/index.tsx:10-31
  HealthSummary,StorageFootprint,StorageCategory,EraBreakdown — duplicate
  openapi HealthSummary/StorageStats.
  - frontend/src/pages/Library/components/CollectionCard.tsx:10-26
  LibraryCollectionData,LibraryCollectionItemData — duplicate
  LibraryCollectionRead/LibraryItemRead.
  - frontend/src/pages/Library/index.tsx:20 &
  frontend/src/pages/Profiles/ProfileDetail.tsx:14 Page<T> — duplicate openapi
  Page_LibraryCollectionRead_.
  - frontend/src/pages/FirstRun/types.ts:30 EmulatorStatusData — duplicate of
  openapi EmulatorStatusData (schema exists and is used elsewhere); its inline
  status union also re-hardcodes InstallStatus.
  - frontend/src/hooks/useLibraryScan.ts:19,36 ScanStatus,ImportResult —
  duplicate openapi ScanStatus/ImportResult/ImportErrorItem.

  Hand-written by necessity (backend never exposes a typed schema — a real gap,
  not laziness):
  - useLibraryScan.ts:7 ScanPreviewItem — backend models/library.py has
  ScanPreviewItem but no endpoint uses it as response_model (preview rides the
  untyped jobs result). Backend model is effectively dead, frontend re-invents
  it.
  - FirstRun/types.ts EmulatorStatus,LibraryPaths,FirstRunStatus,OwnerStatus —
  first-run endpoints return untyped dicts; no openapi schema.
  - FetchMetadataModal.tsx:6,12 SearchResult,GameDetails — TheGamesDB proxy
  responses are untyped; no openapi schema.

  ---
  Point 4 — Do constants.yaml and openapi/types.ts overlap? Which is
  authoritative?

  Yes, they overlap for 6 concepts (media_type, era, hardware_profile,
  install_type, tag color, emulator_slug), and constants.yaml is authoritative
  — openapi inlines those enums because the Pydantic models import the
  generated Literals. There is no place where openapi defines a value set that
  contradicts constants.yaml today.

  They can still drift independently because the frontend carries the same
  concept twice via two separately-triggered regenerations:
  generated/constants.ts (from gen_constants.py) and types.ts (from a
  backend-startup openapi dump). media_type illustrates the split perfectly —
  the generated MediaType union is dead (0 uses); the frontend actually reads
  media_type from types.ts. So the value set that matters at runtime for
  media_type is the openapi copy, refreshed only when the backend restarts.
  Enums that come only from hand-written backend Literals
  (InstallStatus→EmulatorStatusData.status, kind, key, entity_type) exist only
  in Pipeline B — they never reach generated/constants.ts.

  ---
  Point 5 — Hardcoded literals in detection/ingest with no constant reference
  (drift-prone sites)

  - backend/service/utils/era_media.py:42-67 media_type_from_path returns bare
  "iso"/"cue"/"chd"/"bin"/"gdi"/"cdi"/"floppy"/"hdd"/"exe"/"rom"/"directory"/"u
  nknown" — the origin of the prior drift; bin/gdi/cdi/rom still not in
  MediaType. No reference to the MediaType constant.
  - backend/service/library/items.py:126,132,205-210,301,348,351-353,505,509 —
  "era":"unknown", media_type write, "Selected by user during import", !=
  "unknown" — all bare strings.
  - backend/service/utils/era_defaults.py:4,8-22 DOS_WIN_ERAS={"dos","win31"}
  and the defaults_for_era match/case — hardcoded era→emulator map, duplicating
  BACKEND_SYSTEM_LABELS (constants.yaml) and EMULATOR_ERA_MAP (types/era.ts):
  three independent era→emulator mappings.
  - backend/service/utils/smart_media_detector/detector.py:23 {"dos","win31"}
  and all era returns across detector.py/exe_detect.py/directory_detect.py —
  bare era strings (the smart_media_detector is intentionally decoupled from
  backend.*, so this is by design, but it means detector era output is
  validated against EraValue only at the DB/API boundary, never at emit time).
  - backend/service/platforms/environments.py:84-112 platform status strings —
  bare, no constant, and the only frontend consumer (StatusBadge) doesn't cover
  half of them.
  - backend/models/launch_history.py:59-61 target_type strings — bare.

  ---
  Point 6 — Concept map (declared / generated / duplicated)

  Media type
  - config/constants.yaml media_types: — SSOT (declared)
  - backend/constants_generated.py:93 MediaType Literal — generated (A), used
  by models only
  - frontend/src/generated/constants.ts:64 MediaType — generated (A), DEAD (0
  uses)
  - backend/models/library.py:42,71 LibraryItem/LibraryItemRead.media_type —
  consumer → emits openapi inline enum
  - shared/openapi.json→shared/types.ts LibraryItemRead.media_type — generated
  (B), the copy actually used by FE
  - backend/service/utils/era_media.py:42 media_type_from_path — producer,
  hardcoded, unaligned (bin/gdi/cdi/rom missing)

  Era
  - config/constants.yaml eras: — SSOT
  - backend/constants_generated.py:6,22 Era/EraValue — generated (A), used
  backend-wide
  - frontend/src/generated/constants.ts:3 Era + ERA_LABELS — generated (A),
  used by FE
  - shared/types.ts LibraryCollectionCreate.era inline enum — generated (B)
  - frontend/src/components/common/EraSelector.tsx:1 EraValue — hand duplicate,
  drifted (no unknown)
  - frontend/src/types/era.ts ERA_LABEL/ERA_COLOR/ERA_PLACEHOLDER — hand
  duplicate label/color maps, drifted
  - frontend/src/pages/Environments/EnvironmentModal.tsx:9 PCEra — hand subset

  Era → emulator/backend mapping
  - config/constants.yaml backend_system_labels →
  constants_generated/constants.ts — generated
  - backend/service/utils/era_defaults.py:8 defaults_for_era — hand duplicate
  (dispatch)
  - frontend/src/types/era.ts:39 EMULATOR_ERA_MAP — hand duplicate (display)

  Backend slug (dispatch) vs Emulator catalog slug (launch)
  - config/constants.yaml backend_slugs: → BackendSlug (dosbox,86box,…) —
  generated; BackendSlug DEAD on FE (0 uses)
  - config/emulators/*.toml → gen_constants.discover_catalog_slugs() →
  EmulatorCatalogSlug (dosbox-x,86box,…) — generated, different vocabulary
  (dosbox vs dosbox-x); both live

  Install / job / sandbox status
  - backend/core/install_registry.py:6 InstallStatus — hand SSOT → openapi
  EmulatorStatusData.status
  - frontend/src/pages/FirstRun/types.ts:37 inline status union — hand
  duplicate of InstallStatus
  - backend/core/jobs.py:17-18 JobKind/JobStatus — hand SSOT (not exported to
  FE; FE _AppContext.ts BackgroundJob re-types loosely)

  Platform / environment status
  - backend/service/platforms/environments.py:84-112
  healthy|degraded|unconfigured|error|ok|missing — hand SSOT, untyped
  (PlatformRead.status: str)
  - frontend/src/ui/StatusBadge.tsx:3 Status — hand duplicate, drifted +
  component unused

  Launch target type
  - backend/models/launch_history.py:59 library_collection|environment — hand,
  untyped (derived in read model)

  Tag color
  - config/constants.yaml tag_colors: → TagColor/TAG_COLOR_HEX (A) → openapi
  TagCreate.color (B); FE uses generated TAG_COLOR_HEX. No duplication.

  Content rating
  - config/constants.yaml content_ratings: → backend CONTENT_RATINGS (DEAD in
  backend) + FE RATING_OPTIONS (used). Rating ordinal comparison map lives
  separately in settings.yaml (_load_rating_ordinals) — a second, unlinked
  rating source.

  API response shapes (filesystem, health, scan preview, pagination, collection
  card)
  - openapi schemas exist → but hand-duplicated in FileBrowser.tsx,
  PlatformHealth/index.tsx, CollectionCard.tsx,
  Library/index.tsx+ProfileDetail.tsx (Page<T>), useLibraryScan.ts,
  FirstRun/types.ts (see Point 3).

  ---
  Flags (security / resource / structural)

  - No new security issue. The one material risk is the regeneration split
  (Point 4): generated/constants.ts and openapi.json/types.ts are refreshed by
  different triggers, so the frontend can hold two out-of-sync copies of the
  same enum — the mechanism behind the read-time media_type crash class already
  reported. Nothing mechanically enforces co-regeneration (TECH.md/SECURITY.md
  already note "no CI/pre-commit exists").
  - media_type_from_path (era_media.py:42) remains unaligned with MediaType
  (bin,gdi,cdi,rom) — still live drift, per prior discovery.
  - Dead backend model ScanPreviewItem (never a response_model) forces a
  hand-written FE copy and keeps the scan-preview contract untyped end-to-end.
  - ~13 dead generated exports and 3 parallel era→emulator maps / 3 era label
  sources are maintenance-drift surface, not runtime bugs.

  No fixes proposed. No files edited. No test suites or package managers run.
  No background processes were started.