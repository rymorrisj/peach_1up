Peach 1UP — Backend Flow Atlas (discovery pass, current code)

Conventions: each step is caller (file:line) -> callee (file:line) [what happens]. Branch points list each continuation separately. "⇒ converges to Fx" marks shared subgraphs.
One-line Terminal effects per flow. Notes prefixed ⚠ are observations only (not findings).

═══════════════════════════════════════════════════════════════════════════════
V2 RENAME BANNER (applies to this ENTIRE document, supersedes both the body and
the 2026-07-04 addendum below)
═══════════════════════════════════════════════════════════════════════════════

This atlas was written before the v2 domain refactor. The flows are still
structurally accurate, but the vocabulary and file:line references below predate
v2 and are indicative, not exact. Apply this map throughout:

- `LibraryCollection` → `SoftwareCollection`; the leaf `LibraryItem` → `SoftwareItem`;
  `LibrarySet` is gone (folded into the collection/leaf model).
- `Platform` → `Environment` (model, rows, "platform" prose). `PlatformHealthCounts`
  → `EnvironmentHealthCounts`; status is the `EnvironmentStatus` Literal.
- Models: `models/library.py` → `models/software.py`; leaf field `media_type` →
  `file_type` (`FileType`); `media_path` is the leaf's `file_path`.
- Routes: `models`/routers `library.py`/`library_collections.py`/`libraryitems.py`
  → `software_collections.py` + `software_items.py`. `platforms.py` → `environments.py`.
- Route prefixes: `/api/v1/library*` → `/api/v1/software` and `/api/v1/softwarecollection`;
  `/api/v1/platforms` → `/api/v1/environments`. Collection launch is
  `POST /api/v1/softwarecollection/{collection_id}/launch` (F1).
- `launch_history.library_item_id`/`library_collection_id` → `software_collection_id`;
  derived `target_type` value `library_collection` → `software_collection`.
- Permission flags: `can_edit_library` → `can_manage_software` (which also now gates
  Profile CRUD and `POST /software/scan`); `can_edit_platforms` → `can_edit_environments`.
  `can_manage_profiles` is now an orphaned flag that gates nothing (Profile CRUD moved
  to `can_manage_software`).
- New in v2 and not in this atlas: the Media/archive domain (`/api/v1/media`), System
  domain (Health + Controllers, `can_manage_controllers`), and generalized Tags.

The remainder of the document is left in its original pre-v2 wording for historical
continuity; read it through the map above.

App wiring: main.py:39-42 middleware stack (LIFO → runtime order CORS → Security → CSRF → FirstRunGuard → router); main.py:44-57 14 routers included; main.py:65,94,96 three
catch-alls (/media/\*, docs host, SPA). All db params resolve through get_db (core/database.py:47), a per-request session generator.

---

F0 — Startup / Lifespan (process boot + teardown)

Entry: ASGI startup → lifespan (core/lifespan.py:32).

- lifespan:33 -> core.settings.init_settings [load .env + app_settings (DB); settings.yaml/paths.yaml removed]
- lifespan:35 -> logger.setup_logging
- lifespan:36 -> startup_tasks.\_ensure_default_paths (startup_tasks.py:72) [mkdir library tree]
- lifespan:38 -> service.utils.settings.validate_configured_paths; :39 stores app.state.path_warnings
- Branch (dev-only): lifespan:43 if reset_db flag → unlink db file → set_flag(reset_db,False); else skip
- lifespan:49-51 -> init_db / create_tables / \_apply_schema_migrations
- lifespan:52 -> \_ensure_owner_user (startup_tasks.py:56) [warn only if no owner]
- lifespan:57-63 one session: \_sync_first_run_from_db (sets middleware cache security.set_first_run_complete), \_seed_system_platforms, \_seed_default_profiles,
  \_cleanup_stale_sessions (closes LaunchHistory rows with null ended_at, exit_code=-1), \_flag_corrupt_platform_working_paths (marks .cfg working paths degraded)
- Branch: lifespan:66 if seeds failed → raise RuntimeError (startup aborts); else continue
- lifespan:71-72 -> \_scan_installed_emulators (writes install_registry), \_sync_detected_emulator_paths → emulator_catalog.detect_and_sync_all → configure_emulator per slug
- lifespan:74 -> app_container.validate_descriptor_grant_surface [asserts every container_broker_files[].path_key resolvable; raises if not]
- lifespan:79 -> warm eras.yaml cache
- lifespan:86-87 -> tray.start (best-effort)
- lifespan:91 -> asyncio.create_task(\_process_monitor_loop) ⇒ see F6
- yield (serving)
- Teardown :95-115: cancel monitor → process_registry.cleanup_exited + write_session_ends → mark still-running sessions ended (exit_code=-15) → process_registry.terminate each
  pid → tray.stop

Terminal effects: DB initialized/migrated/seeded; settings loaded; emulators detected into install_registry; monitor task running; on shutdown all tracked processes terminated
and their LaunchHistory rows finalized.
Mechanizability: mostly deterministic (explicit imports/calls); the seed-abort branch and the dev reset_db branch are runtime-state conditionals requiring judgment.

---

F1 — Library Item Launch

Route: POST /api/v1/library/{item_id}/launch (launches.py:27).

- launches.launch_item:31 -> dependencies.require_permission("can_launch_media") [403 gate]
- :33 -> dependencies.get_filtered_item (dependencies.py:127) [rating/restriction filter; 404 if hidden]
- :34 -> coordinator.launch_item (coordinator.py:314)
  - coordinator:315 -> process_registry.cleanup_exited; if any -> history.write_session_ends
  - :319 -> \_resolve_profile_for_item (coordinator.py:81) [profile_id arg → item.profile_id → else 422]
  - :320 -> db.query(Platform).filter(profile_id==profile.id) [optional platform record]
  - :322 -> drive_hydration.hydrate_drive_for_item (drive_hydration.py:41) - Branch: drive missing & era∈{dos,win31} -> drive_utils.create_drive_for_item [creates Drive row + sets item.drive_id] - Branch: loose-dir DOS item not yet installed -> format_fat16 + \_copy_loose_files_to_drive (MD5-verified) + set item.installed=True (⚠ img_path.unlink() discards prior
    image) - else: returns existing/None drive, no fs writes
  - :324-330 resolve effective_media_path: executable_path or media_path; Branch: if dir & no drive -> era_media.resolve_media_file_from_directory (else 422)
  - :332 -> \_build_spec_for_item (coordinator.py:112) - :120 -> backend_router.resolve_backend_name(Era) (backend_router.py:35) → emulator_catalog.get_backend_for_era (reads eras.yaml backend); win95/98/xp fallback → box86 - Branch: slug∉{box86,xemu} -> backend_router.get_executable_path → emulator_catalog.get_install_path; if empty -> 422 "emulator not installed". box86/xemu resolve their own
    binary later. - builds LaunchSpec (all ORM fields flattened to plain values)
  - :333 -> coordinator.launch(spec, db) ⇒ converges to F3

Terminal effects: LaunchHistory row (started/job_isolated/sandboxed/limits); process registered in process_registry; emulator process running under Job Object (+ optional
AppContainer); possible new Drive row / FAT16 image / item.installed.
Mechanizability: the dispatch into a backend is dynamic — resolve_backend_name returns a slug string used by dispatch (F3) via a dict lookup; a call-graph tool sees dispatch()
but not which backend module runs without modeling the slug. Profile/drive/media-resolution branches are runtime-state. The straight import edges
(coordinator→drive_hydration→drive_utils→fat) are deterministic.

---

F2 — Environment (Platform) Launch — with on-launch provisioning

Route: POST /api/v1/environments/{platform_id}/launch (launches.py:42).

- launches.launch_environment:46 -> require_permission("can_launch_media")
- :48 -> db.get(Platform) [404 if missing]
- :53 -> coordinator.launch_environment (coordinator.py:336)
  - :338 -> process_registry.cleanup_exited (+ write_session_ends)
  - :342 -> \_resolve_profile_for_environment (coordinator.py:94) [profile_id → platform.profile_id → bundled-by-era → else 422]
  - Branch A (provision needed): :346 working_image_path is None & era∈{win95,win98,winxp} - :348 -> vm.provision_platform (provisioner.py:172) - :186 -> emulator_catalog.get_install_path("86box") [else RuntimeError] - :193 -> get_86box_rom_path → box86.resolve_rom_path (box86.py:152) [canonical roms/ then versioned roms-*] - :195 -> provision_86box_vm (provisioner.py:64) [reads eras.yaml disk size, 86box profile; sub-branch pre-installed MBR image → copy as disk.<ext>, else build raw VHD
    footer; ISO/cue → CD-ROM section] -> ini_writer.patch_ini - returns (iso, working_img, cfg, install_path, rom_path) - :356-368 persist: base_image_path (if newly derived), working_image_path, config_path → db.commit() (⚠ resolved_install_path/rom_path carried into spec to avoid
    re-resolution) - on any exception -> 422 "automatic provisioning failed"
  - Branch B (already provisioned): skip provisioning
  - Branch (still none): :376 working_image_path still None -> 422
  - :383 -> \_build_spec_for_environment (coordinator.py:198) [slug via resolve_backend_name; spec.executable_path=resolved_install_path;
    spec.resolved_rom_path=resolved_rom_path]
  - :394 -> coordinator.launch(spec, db) ⇒ converges to F3

Terminal effects: possible new 86Box VM dir (emulators/86box/vms/{slug}/ disk image + 86box.cfg); Platform row updated with working/config/base paths; LaunchHistory; 86Box
process under Job Object.
Mechanizability: provisioning is era-gated runtime branching (judgment). provision_platform→provision_86box_vm is a deterministic import edge. The launch convergence is dynamic
dispatch as in F1.

---

F3 — Shared launch/isolation subgraph (CONVERGENCE POINT for F1, F2, and every backend)

Entry: coordinator.launch(spec, db) (coordinator.py:240). All emulator launches converge here.

- coordinator.launch:261-273 -> create+commit LaunchHistory (target_type item|environment)
- :277 -> asyncio.to_thread(backend_router.dispatch, spec) with 30s wait_for timeout
  - Branch (timeout): :281 -> set error/exit_code=-1, commit, 500
  - Branch (exception): :288 -> set error, commit, 500
- backend_router.dispatch (backend_router.py:64) -> \_BACKEND_MODULES[spec.slug] lookup (:79) -> importlib.import_module -> module.launch(spec) (dynamic dispatch by slug string)
  - Routes to one of: backends/dosbox.py:395, backends/box86.py:220, backends/xemu.py:162, backends/flycast.py:31, backends/console.py:34 (mesen/project64/duckstation/pcsx2 all
    share console)
  - Each backend (sub-convergence): validate exe/media/era → emulator_catalog.validate_bios_from_descriptor(slug) (⇒ shared with F8) → write per-launch config (dosbox temp conf
    / 86box \_prepare_config / xemu provision_xemu_defaults toml / flycast emu.cfg / duckstation+pcsx2 ini RecursivePaths) → resolve container_enabled (profile override else
    get_container_enabled) → if enabled build SandboxConfig via app_container.get_container_config (+ append BrokerFiles) → call launch_under_job_object
- backend -> launcher.launch_under_job_object (launcher.py:178) [the hard convergence point]
  - :210 -> \_load_era_limits(era) (launcher.py:44) → eras_config.get_eras [memory_limit_mb, cpu_limit_percent; raises if missing]
  - Branch (container): :213 -> \_launch_process_in_container (launcher.py:128) -> sandbox.launch(config) ⇒ F3a
  - Branch (no container): :217 -> \_launch_process (launcher.py:75) -> kernel32.CreateProcessW
  - :219-221 -> WindowsJobObject(name+pid) (job_objects.py:82).create -> CreateJobObjectW (⚠ ERROR_ALREADY_EXISTS treated as fatal)
  - :223 if not get_skip_cpu_limit(slug) -> set_cpu_limit (MIN_MAX_RATE on build≥14393 else HARD_CAP)
  - :226 Branch: get_skip_memory_limit(slug) -> set_kill_on_close; else -> set_memory_limit
  - :259 -> job_object.add_process -> AssignProcessToJobObject
    - Branch (error 5 → retry_with_breakaway): :274 kill proc → relaunch with CREATE_BREAKAWAY_FROM_JOB → re-add; on failure teardown + RuntimeError
    - Branch (other failure): kill + teardown + RuntimeError
  - returns (SandboxProcess, WindowsJobObject)
- back in coordinator.launch:297 -> \_finalize_launch (coordinator.py:39)
  - Branch (job missing/handle None): :52 -> proc.kill(), set error "Job Object isolation required but unavailable", 500 (no unsandboxed fallback)
  - Branch (ok): :65 -> process_registry.register(pid, ProcessEntry); set history job_isolated/sandboxed/limits/network_blocked; commit
- Branch (dosbox only): coordinator.launch:304 -> monitor.register_short_lived_check ⇒ F6
- returns LaunchResult(history_id, warnings, launch_review_flagged)

F3a — AppContainer sandbox host (sub-flow)

- sandbox.launch (sandbox/sandbox.py:206): \_validate(config) → subprocess.Popen(sandbox_host.exe) → write JSON stdin payload → 15s timer → read first stdout line (JSON:
  sid/pid/event_name/stage) → Branch: stage=="error" → raise SandboxError; else build SandboxHandle + spawn daemon \_watch_event thread (waits Win32 event → fires EXITED/CLEANED_UP
  callbacks)
- launcher.\_launch_process_in_container:152 then OpenProcess(PROCESS_ALL_ACCESS, sid pid) to get a Win32 handle wrapped in SandboxProcess (so the Job Object can still manage it)

Terminal effects: native emulator process spawned (optionally inside AppContainer SID), enrolled in a named Job Object with CPU/mem caps, registered in process*registry,
LaunchHistory finalized. Config files written (per-backend, some cleaned on exit via daemon threads).
Mechanizability: This is the least mechanizable region. dispatch is string-keyed dynamic import; backend selection of container config and broker files is conditional;
get_skip*\*/get_container_enabled read settings overrides at runtime; the breakaway-retry and job-missing branches are runtime-error-driven. The launch_under_job_object fan-in
(every backend calls it) is the one edge a tool can find deterministically (direct import in all 5 backend modules).

---

F4 — Library Ingest (manual add / upload / scan / scan-import)

Four entry points share service/library/items.\_prepare_item (items.py:43).

F4a — Manual add POST /api/v1/library (library.py:59)

- -> require_permission("can_edit_library") -> lib_svc.\_ingest_media_entry (items.py:265) -> \_prepare_item → LibraryItem(\*\*row) + flush; Branch: era∈{dos,win31} ->
  create_drive_for_item; commit. \_ItemAlreadyExists -> 409.

F4b — Upload game media POST /api/v1/library/upload (library.py:76)

- -> require_permission("can_edit_library") -> upload_utils.begin_upload (slug dir under MEDIA_PATH) -> stream_upload_to_disk (1MB chunks, 413 on cap) -> \_ingest_media_entry. On
  any failure -> shutil.rmtree(dest_dir).

F4c — Scan (async preview) POST /api/v1/library/scan (library.py:144)

- Branch: \_scan_state["running"] -> 409
- \_resolve_scan_directory (MEDIA_PATH; 400 if unset/invalid) -> set state running -> background_tasks.add_task(\_run_scan)
- \_run_scan (library.py:157, background): profile_builder.scan_media_folders -> per entry: dedup vs existing folder_paths -> best_detect_path -> smart_media_detector.detect (⇒
  F4e) -> append preview dict; finally store preview in \_scan_state. No DB writes.
- GET /api/v1/library/scan/status (library.py:121) returns \_scan_state snapshot.

F4d — Import selected POST /api/v1/library/scan/import (library.py:236)

- -> require_permission("can_edit_library") -> per selected path \_prepare_item(used_slugs=...) collecting rows (skip \_ItemAlreadyExists, collect HTTPException reasons) ->
  db.bulk_insert_mappings in chunks of 500 -> commit -> for PC-era slugs query back items -> create_drive_for_item each.

F4e — \_prepare_item core (items.py:43, shared by F4a/b/d)

- get_settings MEDIA_PATH; resolve src; Branch: matches a Platform base/working image -> 409
- Branch dir: verify under media root → dedup by folder_path → \_find_cover → pick executable by \_EXECUTABLE_PRIORITY → smart_media_detector.detect → if era known
  resolve_media_file_from_directory + re-detect
- Branch file + MEDIA_PATH set: compute dest folder, dedup src/dest → mkdir → move file (or reuse if identical size; 409 if size differs) → cover
- Branch file + no MEDIA_PATH: dedup only, folder_path=parent
- slug (unique_slug in-memory when batching, else generate_item_slug) → media_type_from_path → requires_install from scan → Branch: era known -> era_defaults.defaults_for_era +
  lookup_platform_and_profile → set profile_id/platform_id; override_profile_id wins → rating_detect.detect_rating → stat size → return row dict (no DB write)

F4e' — smart_media_detector.detect (detector.py:47): try Tier-1 hash lookup → file dispatch by suffix (\_detect_file) or detect_directory → compute requires_install. Returns
ScanResult(era, reason, ...). (⚠ broad except returns null-era ScanResult.)

Terminal effects: new LibraryItem rows (single or bulk); files moved/copied into MEDIA_PATH; optional Drive rows for dos/win31; \_scan_state populated (scan); no DB writes during
scan preview.
Mechanizability: \_prepare_item branching (dir vs file, dedup, dest move) is runtime-state heavy. detect's suffix dispatch and defaults_for_era's match are
deterministic-but-data-driven (a tool can read the match arms). The era→emulator mapping in era_defaults is a clean static table. Background-task scheduling (add_task) is a
deterministic edge but execution is deferred.

---

F5 — Auth / Session Lifecycle

Routes in auth.py; CSRF-exempt prefix /api/v1/auth/ (security.py:65).

- setup-owner POST /auth/setup-owner (auth.py:80): Branch owner exists -> 409; validate name/pin (4-6 digits, match) -> argon2 hash -> create owner User (all perms) ->
  identity.issue_session (identity.py:28, mints HMAC token, stores session_token_hash) -> \_set_auth_cookie + \_set_csrf_cookie.
- switch POST /auth/switch (auth.py:121): db.get(User) (404); Branch locked -> 403; Branch owner -> require pin, \_verify_pin (argon2), on fail increment failed_pin_attempts
  (lock at ≥4) -> 401; Branch non-owner & pin_required False -> passwordless; else verify pin. Success -> reset attempts -> issue_session -> set cookies.
- logout POST /auth/logout (auth.py:171): parse cookie -> validate_session (only clears if token actually validates, anti-forgery) -> clear_session -> delete cookies.
- me GET /auth/me (auth.py:189): parse cookie -> validate_session -> UserRead (401 chain).
- refresh POST /auth/refresh (auth.py:203): validate -> extend_session (pushes expiry, never rotates token) -> re-set cookies.
- Shared dependency get_active_user (dependencies.py:41): cookie -> parse_session_cookie -> validate_session (identity.py:76: user lookup → hash present → expiry check →
  hmac.compare_digest). require_self_or_admin, require_permission(flag) (owner bypass) layer on top.

Terminal effects: User row session_token_hash/expiry mutated; httponly peach_token + JS-readable peach_csrf cookies set/cleared; lockout counters updated.
Mechanizability: highly deterministic — explicit dependency wiring and direct identity.\* calls. The owner/non-owner/pin branches are readable conditionals. The
CSRF/Security/FirstRun middleware (security.py) wrap every request but are configured statically in main.py (a tool can find them; their per-request short-circuits are runtime).

---

F6 — Process Monitoring, Session Finalization & Stop

- Monitor loop \_process_monitor_loop (process_monitor.py:10, started F0): every 5s -> process_registry.cleanup_exited (process_registry.py:67, polls each handle, closes job
  handles of reaped procs) -> if exited history.write_session_ends (history.py:6, sets ended_at/exit_code) -> monitor.poll_short_lived (monitor.py:36).
- Short-lived detection (dosbox only): register_short_lived_check (F3) stores (proc, t); poll_short_lived flags item if exited within 3s -> \_flag_short_lived_item sets
  LibraryItem.launch_review_flagged=True.
- Stop POST /api/v1/launches/{history_id}/stop (launches.py:98) -> coordinator.stop_launch (coordinator.py:397): 404 if no record; Branch non-admin & profile belongs to other
  user -> 403; find pid by history_id or library_item_id -> process_registry.terminate (terminates proc + job_handle.teardown) -> set ended_at/exit_code=-15.
- Read GET /launches, /library/{id}/launches, /launches/{id} — thin DB queries (launches.py:66,80,87).

Terminal effects: registry entries reaped; LaunchHistory rows finalized; short-lived dosbox items flagged; processes/jobs torn down on stop.
Mechanizability: deterministic call edges; the "find pid by history or item" and short-lived timeout are runtime-state loops.

---

F7 — Emulator Install / Catalog / Sandbox config

Routes in emulators.py.

- list GET /api/v1/emulators (:125): load_catalog + per slug get_install_path, installer_present, check_git, settings sandbox overrides → assembled dicts. (unauthenticated)
- install POST /{slug}/install (:284) [admin]: get_emulator (404); Branch by install_type: zip -> detect_binary (404 if absent) + install_registry.set_status(complete);
  installer -> guard if already launched (409) -> launch_installer (ShellExecuteW runas) + status installer_launched; rom_pack -> guard cloning (409) -> status cloning +
  background_tasks.add_task(\_run_clone) -> \_run_clone -> asyncio.to_thread(clone_rom_pack) (git clone) + status complete/error; else 400.
- status GET /{slug}/status (:351) [admin]: catalog + get_install_path + install_registry.get_status.
- delete DELETE /{slug} (:401) [admin]: consume_confirm_token (403) -> remove_emulator (rmtree under emulators/) -> status idle. Token via GET /{slug}/confirm-token.
- sandbox patch PATCH /{slug}/sandbox (:381) [admin]: Branch trying to enable a permanently-disabled container -> 400; else settings.set*flag(sandbox*{slug}\_{field}).
- sandbox-state reset DELETE /sandbox-state (:179) [admin]: consume_confirm_token("sandbox-state") -> for each container_enabled catalog entry, sweep all Profile.user_id scopes

* "shared" -> app_container.reset_container(slug, user_id) -> sandbox.reset_container (sandbox_host.exe --reset moniker). Token via GET /sandbox-state/confirm-token.

- xemu asset paths GET/PATCH /xemu/asset-paths (:218,239) [admin]: read/normalise/write emulators/xemu/xemu.toml [sys.files].

Terminal effects: install_registry state; emulator binaries detected/removed; ROM pack cloned; settings flags; AppContainer profiles reset; xemu.toml rewritten.
Mechanizability: install is a clean install_type string switch (readable). reset_sandbox_state dispatches into the sandbox subsystem with per-user moniker construction — the
moniker string (Peach1UP.{slug}.{user|shared}) is computed at runtime (judgment to connect reset↔launch moniker parity).

---

F8 — BIOS Validation & Placement

- list GET /api/v1/bios (bios.py:27): load_bios_requirements + per entry check_bios_presence (emulator_catalog.py:389).
- place POST /api/v1/bios/{slug}/place (bios.py:50) [admin]: find requirement (404) → resolve dest_dir under base (500 if escapes) → Branch source_path xor uploads (400 if
  both/neither) → bios_placement.place_bios_asset (bios_placement.py:219) which dispatches by slug (ps1-bios/ps2-bios/86box-roms/dreamcast-bios/mesen-fds-bios/xbox-bios→reject)
  into pattern/tree/pair/fds placement helpers (copy or stream_upload_to_disk, hash-check for FDS) → re-check check_bios_presence.
- Validation (launch-time, shared with F3): every backend calls validate_bios_from_descriptor(slug) (emulator_catalog.py:423): iterate descriptor [[dependencies]] with bios_path
  → resolve under root (ValueError if escapes) → \_missing_required_files (required_files/required_glob/excludes, else non-empty-dir) → FileNotFoundError if required & missing.

Terminal effects: BIOS/ROM files copied into descriptor-declared dirs; placement result (copied/skipped/warnings); launch-time gate raises before any process spawn.
Mechanizability: place_bios_asset is a string-keyed dispatch (slug→helper) — readable arms but per-slug semantics need judgment. validate_bios_from_descriptor is data-driven
from TOML descriptors (a static tool would need to read the TOMLs, not just Python).

---

F9 — Platform / Environment CRUD, Snapshots, Health

Routes in platforms.py → service/platforms/environments.py.

- create POST /api/v1/platforms (:41) [can_edit_platforms] -> environments.create_platform: validate era (422) + image paths -> create Platform -> Branch no working img &
  era∈{win95,win98,winxp} -> vm.provision_platform (⇒ shares provisioner with F2) -> persist paths -> \_compute_status.
- update/delete :69,:81 -> update_platform / delete_platform (token-gated via confirmation_tokens.consume).
- health POST /{id}/health (:91) -> check_platform_health (Branch is_system → check emulator install; else compute from image files). health-all -> batch_health_check. GET
  /health -> get_health_summary (aggregates platforms/library/drives/emulators/bios/rom_packs). GET /storage-stats -> get_storage_stats.
- snapshots (:100-147) -> create*snapshot (copy working image to \_snapshot* file), restore_snapshot (token → copy snap over working), delete_snapshot (token → unlink). Each
  confirm-token endpoint issues via confirmation_tokens.issue.
- list/get :21,:61 thin queries (list augments with image sizes via stat).

Terminal effects: Platform rows; provisioned VM files; snapshot image files; status/last_health_check updates.
Mechanizability: straightforward service-method edges; provisioning + is_system branches are runtime. Token issue/consume is a deterministic pair across confirmation_tokens.

---

F10 — Settings & First-Run

Routes in settings.py.

- GET "" (:60) returns settings minus \_-prefixed and sensitive keys. PATCH "" (:70) [can_edit_settings]: path keys → svc.set_path; others → mutate state + \_persist (app_settings DB row).
- POST /validate (:83) — thin stub, returns empty results (no further trace).
- GET /first-run-status (:88): DB first_run row + owner count + compute_setup_status + path snapshot + app.state.path_warnings. GET /owner-status (:111) unauthenticated
  owner-health check.
- POST /emulator-path (:119) / POST /library-path (:146): normalise + existence/type check → svc.set_path.
- POST /complete-first-run (:165) [can_edit_settings]: write DB first_run_complete=true → security.set_first_run_complete() (flips middleware cache, see F0/middleware).

Terminal effects: app_settings DB row(s) mutated; first-run DB flag + middleware cache flipped.
Mechanizability: deterministic. The \_ALL_PATH_KEYS membership branch in PATCH is a static set lookup.

---

F11 — Users CRUD (users.py)

- GET "" (:71) intentionally unauthenticated (switch-user screen; UserRead excludes secrets). GET /{id} auth'd.
- POST "" (:93) [is_admin]: validate/hash pin (argon2 low-level), create User. PATCH /{id} (:126) [is_admin]: 403 if owner; apply non-none fields. DELETE /{id} (:146)
  require_self_or_admin: 403 owner; reassign that user's Profiles to owner, delete MediaRestrictions, delete user. reset-pin/unlock/force-logout [is_admin] mutate
  pin/lock/session.

Terminal effects: User rows + pin hashes; profile reassignment; session clears.
Mechanizability: fully deterministic dependency + DB edges.

F12 — Profiles CRUD (profiles.py)

- GET "" (:79) -> \_with_stats_bulk (counts items+launches). POST "" (:87) [can_manage_profiles] 409 on slug dup. GET /{slug}, /{slug}/items. PATCH /{slug} re-slugs on name
  change. DELETE /{slug} 403 if bundled.
  Terminal effects: Profile rows. Mechanizability: deterministic; stats are aggregate queries.

F13 — Tags CRUD (tags.py)

- GET "" (:25) -> \_tag_read (item counts). POST "" 422 blank/409 dup. DELETE /{id}. POST|DELETE /{tag_id}/items/{item_id} manage LibraryItemTag link (404s if tag/item missing).
  All mutations [can_edit_library].
  Terminal effects: Tag + LibraryItemTag rows. Mechanizability: deterministic.

F14 — Drives CRUD (drives.py)

- GET ""/{id} auth'd. GET /{id}/confirm-token issues token. DELETE /{id} [can_edit_library]: consume token (400) → unlink image file → delete row.
  Terminal effects: Drive rows + image files. Mechanizability: deterministic.

F15 — Filesystem Browse (filesystem.py)

- GET /drives (:55) Windows-only (404 else). GET /browse (:71): home listing when path None; else normalise_path → \_within_allowed(\_allowed_roots()) (400 if outside) → iterate
  dir (skip symlinks/hidden, ext filter). Auth'd via get_active_user.
  Terminal effects: read-only listing. Mechanizability: deterministic; allowed-root computation reads settings at runtime.

F16 — OS Media Upload (media.py)

- POST /api/v1/media/upload (:15) [can_edit_library]: Branch media_type≠"os" → 400 (game media moved to F4b); era must be PC era (422) → begin_upload(OS_PATH/era) →
  stream_upload_to_disk → returns path/slug/size. No DB write, no ingest (OS images are Platform fields).
  Terminal effects: file under OS_PATH/{era}. Mechanizability: deterministic; shares upload_utils with F4b.

F17 — Static / Media / Docs serving (main.py)

- GET /media/{file_path} (:66): localhost-or-ALLOW_NETWORK gate (403) → normalise_path under library root (404 if escapes/missing) → FileResponse.
- app.host(\_DOCS_HOST) (:94): Docusaurus StaticFiles sub-app (registration-order matters vs SPA catch-all).
- GET /{full_path} (:97): serve asset if file exists else index.html (SPA fallback).
  Terminal effects: file bytes served. Mechanizability: deterministic; the host-vs-catchall ordering is a Starlette runtime-matching subtlety (the code comments it).

---

Macro subsystem map (top-level diagram input)

┌───────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Subsystem │ Flows / modules │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ API/Middleware │ all routes; security.py (CORS→Security→CSRF→FirstRunGuard); dependencies.py (auth + library filtering) │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Launch Coordination │ F1, F2, F3 — launch/coordinator.py, launch_spec.py, backend_router.py │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Backends │ F3 — backends/{dosbox,box86,xemu,flycast,console}.py │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Sandbox/Isolation │ F3, F3a — process/launcher.py, process/job_objects.py, app_container.py, sandbox/sandbox.py, sandbox_process.py │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ BIOS/Dependency Validation │ F8 — emulator_catalog.validate_bios_from_descriptor, check_bios_presence, bios_placement.py │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Provisioning │ F2, F9 — vm/provisioner.py, vm/vhd.py, ini_writer.py │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Emulator Catalog/Install │ F7 — emulator_catalog.py, emulator_installer.py, install_registry.py │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Library Ingest │ F4 — library/items.py, smart_media_detector/_, era_media.py, era_defaults.py, drive_utils.py, upload_utils.py, rating_detect.py │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Drive/FAT │ F1, F4 — drive_hydration.py, drive_utils.py, fat/_ │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Auth/Session │ F5 — identity.py, auth.py, dependencies.py │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Process Lifecycle │ F0, F6 — process_registry.py, process_monitor.py, launch/monitor.py, launch/history.py │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Platforms/Snapshots/Health │ F9 — platforms/environments.py │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Settings/First-run │ F0, F10 — core/settings.py, service/utils/settings.py, eras_config.py │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ CRUD (users/profiles/tags/drives) │ F11–F14 │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Filesystem/Static │ F15, F16, F17 │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Confirmation Tokens │ cross-cutting — confirmation_tokens.py (library, platform, drive, snapshot, emulator) │
└───────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

Cross-subsystem edges (who calls whom)

- API/Middleware → every subsystem (route entry)
- Launch Coordination → Backends (via backend_router.dispatch, dynamic) → Sandbox/Isolation (every backend → launch_under_job_object, fan-in)
- Launch Coordination → Provisioning (F2 on-launch) → Emulator Catalog (binary/ROM resolution)
- Backends → BIOS Validation (validate_bios_from_descriptor) and → Emulator Catalog (get_container_config, get_install_path, era limits)
- Sandbox/Isolation → Emulator Catalog (get*skip*\*, get_container_enabled) → Settings (eras.yaml, sandbox overrides)
- Launch Coordination → Drive/FAT (F1 hydration) and → Process Lifecycle (process_registry, monitor, history)
- Library Ingest → Drive/FAT (drive creation), → Emulator Catalog (era detection deps), → Provisioning-adjacent (Platform dedup)
- Platforms → Provisioning + Emulator Catalog + Confirmation Tokens
- Emulator Install → Sandbox (reset_container) + Install Registry + Confirmation Tokens
- Process Lifecycle ↔ Launch Coordination (registry shared; monitor finalizes histories)

---

Mechanizability summary (for future call-graph tooling)

Deterministically extractable (direct imports + static calls; a tool reading the import graph would reconstruct these):

- The middleware stack and dependency injection wiring (F5, all routes).
- launch_under_job_object as the fan-in of all 5 backends (each backend imports it directly).
- coordinator→drive_hydration→drive_utils→fat; coordinator→provisioner→vhd/ini_writer.
- CRUD routes → service methods (F9–F14); upload routes → upload_utils.
- confirmation_tokens.issue/consume pairs; install_registry state transitions.
- The era→emulator table (era_defaults.defaults_for_era) and \_BACKEND_MODULES dict — both are static data tables a tool could read literally.

Require judgment / dynamic (a naïve call-graph tool would miss or mis-resolve these):

- backend_router.dispatch — \_BACKEND_MODULES[spec.slug] + importlib.import_module + module.launch. The actual backend is selected by a runtime slug string derived from era; the
  tool sees dispatch, not the 5 possible targets, without modeling the dict + resolve_backend_name.
- bios_placement.place_bios_asset and emulators install — string-keyed (slug/install_type) branch dispatch into helpers.
- Config-driven validation (validate_bios_from_descriptor, app_container.\_resolve_path_key, era limits) — behavior lives in TOML/YAML descriptors, not Python; a static analyzer
  must parse config/emulators/\*.toml and config/eras.yaml to know what runs.
- Runtime-state branches: provision-needed vs already-provisioned (F2), container-enabled resolution (profile override vs catalog vs settings flag), drive hydration paths,
  \_prepare_item dir/file/dedup logic, breakaway-retry and job-missing abort in launch_under_job_object.
- Deferred execution: BackgroundTasks.add_task (scan import, rom_pack clone) and asyncio.to_thread/daemon threads (sandbox watcher, dosbox/xemu config cleanup, dgvoodoo2
  cleanup) — edges exist statically but execution is decoupled from the call site.
- Moniker parity: AppContainer reset (F7) and launch (F3) must agree on Peach1UP.{slug}.{user_id|shared} — a string constructed in two places
  (app_container.\_moniker_user_scope), only correlatable by understanding semantics.

No files were edited; no tests or installs were run. The call chains above reflect the current code (profile_id gate gone, per-user moniker, ROM path via
emulator_catalog/resolve_rom_path, single xemu BIOS validator, F2-4 path reuse via resolved_install_path/resolved_rom_path).

═══════════════════════════════════════════════════════════════════════════════
CURRENT-STATE ADDENDUM (2026-07-04 audit pass)
═══════════════════════════════════════════════════════════════════════════════

The flow atlas above was written before the P-META / library-consolidation / detection /
multi-disc / platform-health changes. Where it and this addendum disagree, this addendum is
current. It (a) records the entity/route renames, (b) restates the three flows changed this
session in their current shape, and (c) expands services/utils coverage that was thin above.

--- Entity & route renames (global) ---

- LibraryItem/LibrarySet → LibraryCollection (parent "game") + LibraryItem (leaf "disc").
  A single-disc game is a collection-of-one. Models: backend/models/library.py.
  Collection owns metadata (title/era/rating/cover/profile/platform/drive) and an ordered
  leaf list; leaf owns per-disc media_path/executable_path/cover/media_type/folder_path.
- launch_history.library_item_id → library_collection_id (FK CASCADE). LaunchHistoryRead
  derives target_type in a model_validator (library_collection vs environment); it is NOT a
  stored column, so the old "target_type rebuild migration" hazard is gone.
- Routes: the old library.py is split — library_collections.py (list/scan/import/CRUD on the
  parent) and libraryitems.py (leaf get/patch). Chunked upload lives in uploads.py. There is
  NO /library/multi route and NO synchronous upload-folder route — both removed.

--- F1 (revised) — Library Collection Launch ---

Route: POST /api/v1/library/{collection_id}/launch (launches.py) → coordinator.launch_collection
(coordinator.py:468).
- cleanup_exited (+ write_session_ends if any reaped)
- resolve_launchable(collection_id) (launchable_resolver.py:54) → builds a LaunchableEntity from
  the collection's launch_disk_id leaf; disc_paths = every leaf's media_path in disc_number order.
  422 if the collection has no launch disc configured.
- _launch_entity (coordinator.py:445): _resolve_profile_for_item → platform lookup by profile →
  hydrate_drive_for_entity (drive_hydration.py:41; auto-creates DOS/win31 drive, copies loose
  files with MD5 verify on first launch, sets collection.installed=True) → resolve effective media
  (dir + no drive → resolve_media_file_from_directory) → _build_spec_for_entity → launch() ⇒ F3.
- launch() (coordinator.py:332) now guards concurrency up front: process_registry.try_reserve
  (profile_id, emulator_slug, user_id) → 409 if a launch for that profile/emulator is already
  active; reservation released in a finally on every path. After dispatch it runs an inline
  ~0.75s _poll_for_immediate_exit (collections only, not environments) to catch near-instant
  crashes synchronously; slower crashes still caught by the async 3s register_short_lived_check.

--- F4/multi-disc (revised) — Ingest & the consolidated upload pipeline ---

Every add path funnels through service/library/items.py:
- _prepare_item (items.py:66): dir/file/dedup + era detection + defaults; sets content_rating via
  detect_rating, cover via _find_cover, requires_install from the scan. Returns a plain row dict.
- _ingest_media_entry → _persist_collection_of_one (items.py:346): one LibraryCollection + one
  LibraryItem leaf (collection-of-one). Used by manual add and scan-import.
- _create_multi_disc_collection (items.py:402): one leaf per disc file, era from disc_files[0].
  ⚠ AUDIT H1: this builder does NOT call detect_rating / _find_cover — multi-disc sets get
  content_rating=None (parental-controls gap) and no cover. Divergent from the single-disc path.

Chunked upload (uploads.py → chunked_uploads.py → upload_finalize.py → folder_ingest.py):
- init (declare manifest, stage dir) → PUT chunks → complete. ≤ threshold finalizes inline (201);
  over threshold returns 202 + job_id and finalizes in a BackgroundTask (core.jobs / nav bell).
- upload_finalize._finalize is the single funnel. kind dispatch:
  - "file": reassemble → find_existing_duplicate (media_dup_index, hash/content dedup) →
    _ingest_media_entry. (Content dedup is file-kind ONLY — AUDIT M3.)
  - "set": select_disc_pointer_files (order-preserving, companion-aware: .gdi/.cue/.chd pointers
    kept in client order, companions ride along in the shared dest dir) → _create_multi_disc_collection.
  - "folder": folder_ingest.ingest_folder → detect_disc_files (sorted; 2+ of ONE pointer format,
    422 if formats mixed) → multi-disc if found, else pick_folder_launch_file + _ingest_media_entry.
  set/folder symmetry: both now share _DISC_POINTER_EXTS (.gdi/.cue/.chd) and the shared
  _create_multi_disc_collection builder, and both reassemble every file into ONE slug dir (so a
  .cue and its .bin are siblings — the "folder-write collision" fix, 409 on same-named files).
  Residual asymmetry (AUDIT L7): disc_count is reported as len(disc_files) for "set" but
  len(all reassembled paths) for "folder".
- Cleanup ownership: chunked_uploads owns the tmp staging dir (success/abort/orphan sweep);
  upload_finalize removes the reassembled dest dir if ingest fails.

--- F9/health (revised) — Live platform status recompute ---

Single computation: environments.compute_live_status(platform) (environments.py:102) → is_system →
emulator install check (ok/missing); else _compute_status(era, working, base) →
unconfigured/healthy/degraded/error (DOS/win31 never provisioned → absence of a working image is
"healthy/unconfigured", not degraded). All five producers call it: list_platforms (recompute on
read, platforms.py:29), create_platform, check_platform_health, batch_health_check,
get_health_summary. The persisted Platform.status column is written by the health endpoints but is
authoritative for display ONLY via those recompute paths.
- ⚠ AUDIT M1: GET /platforms/{id} (get_platform) returns the ORM object directly, so it still
  serializes the persisted (possibly stale) status column — the one read path not recomputing.
- ⚠ AUDIT M2: get_health_summary buckets unconfigured→degraded and keeps an always-zero "unknown"
  bucket (compute_live_status never yields "unknown" for non-system platforms).

--- Detection tiers (expanded) — service/utils/smart_media_detector ---

detect(path) (detector.py:47) wraps _detect and fail-softs to a null-era ScanResult on any
exception (documented contract, not a swallow):
1. Tier-1 hash lookup (hash_lookup.lookup, sha1→md5→crc32, confidences 1.0/0.85/0.75). For .chd,
   raw file bytes never match Redump; it reads the CHD v5 header's embedded rawsha1
   (chd_validator.extract_embedded_sha1) and matches that. Missing/empty index is caught and
   falls through.
2. File suffix dispatch (_detect_file) or detect_directory. Console ROM extensions → era by
   extension; .iso → magic → PVD (volume label / DOS publisher / PlayStation prefix + DVD-size
   split / .xbe scan) → xiso magic → size fallback; .bin/.cue → magic → PVD → bin_validator;
   .chd → chd_validator.detect (CHGD→Dreamcast; CHTR/CHT2→ size-based PS1/PS2 tiebreaker via
   header logicalbytes — see AUDIT L3 stale docstring / L4 threshold comment); .img → size heuristic.
3. _compute_requires_install(path, era) (dos/win31 only: installer ISO/CUE, small floppy .img, or
   a directory whose only executables are blocklisted DOS tools).
PS1-vs-PS2 is resolved consistently by SYSTEM.CNF BOOT/BOOT2 across magic_detect
(_resolve_ps_generation on raw 2352-byte sectors; resolve_ps_generation_from_file for extracted
files) and directory_detect (SYSTEM.CNF at root).

--- services/utils quick-reference (expansion) ---

- backend_router.py: _BACKEND_MODULES slug→module dict; dispatch imports and calls module.launch.
  resolve_backend_name (win95/98/xp → 86box; else eras.yaml backend). ⚠ get_backend_name is dead
  (AUDIT L1).
- media_dup_index.py: in-memory (size, sha256-lazy) index under the media root; backs content
  dedup; re-validates each cached hash against a live stat() before trusting (never a false
  positive, worst case a missed match).
- eras_config.py / era_media.py: cached eras.yaml accessor; media_type_from_path;
  resolve_media_file_from_directory (extension-priority pick, excludes .img).
- rating_detect.py: NFO sidecar → ISO PVD (.iso only) → bracket-guarded filename stem.
- confirmation_tokens.py: issue/consume pairs gating every destructive op (platform/snapshot/
  drive/library/emulator/sandbox-state).
- vm/provisioner.py + vhd.py + ini_writer.py: 86Box VM provisioning (pre-installed MBR copy vs
  raw VHD build; ISO/cue → CD-ROM), atomic ini patching.
- platform/windows/*: launcher.launch_under_job_object is the fan-in of all 5 backends; job_objects,
  app_container, sandbox (sandbox_host.exe) provide isolation; sandbox_checker validates the tier.
