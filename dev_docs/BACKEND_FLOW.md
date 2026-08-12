# Backend Flow Atlas

Every significant request path through the backend, from entry point to terminal effect.

Symbol names are the anchor, not line numbers. Line offsets drift with every edit, so this
document does not carry them.

Related: [TECH.md](TECH.md) · [TYPES.md](TYPES.md) · [AUTH.md](AUTH.md) ·
[SECURITY.md](SECURITY.md).

## App wiring

`main.py` adds middleware LIFO, giving the runtime order
RequestLogging → CORS → Security → CSRF → FirstRunGuard → router. `ROUTERS` in
[`api/routes/__init__.py`](../backend/api/routes/__init__.py) supplies 26 routers,
including the three per-domain upload routers. `main.py` also registers three catch-alls,
in this order and for this reason:

| Route | Note |
|---|---|
| `GET /media/{file_path:path}` | Localhost-or-`ALLOW_NETWORK_ACCESS` gate, then `normalise_path` under the library root. `LIBRARY_PATH` is read fresh per request, because it can change at runtime |
| `app.mount("/docs", StaticFiles(...))` | Must be registered before the SPA catch-all: Starlette dispatches to the first `Match.FULL` route in registration order. Path-based, not `Host()`-based, because a `Host()` route matches the entire request by hostname with no path discrimination and swallowed `/` as well |
| `GET /{full_path:path}` | SPA fallback: serve the asset if it exists, else `index.html` |

Every `db` parameter resolves through `get_db` in `core/database.py`, a per-request session
generator.

## Route surface

| Prefix | Router |
|---|---|
| `/api/v1/auth` | `auth.py` |
| `/api/v1/user-items` | `users.py` |
| `/api/v1/settings` | `settings.py` |
| `/api/v1/emulator-items`, `/api/v1/emulator-items/rom-packs` | `emulators.py`, `rom_packs.py` |
| `/api/v1/bios` | `bios.py` |
| `/api/v1/profile-items` | `profiles.py` |
| `/api/v1/drives` | `drives.py` |
| `/api/v1/controllers` | `controllers.py` |
| `/api/v1/game-items`, `/api/v1/game-item-bundle`, `/api/v1/game-item` | `game_item_bundles.py`, `game_items.py`, `game_metadata.py` |
| `/api/v1/app-items`, `/api/v1/app-item-bundle`, `/api/v1/app-item` | `apps.py` |
| `/api/v1/media-items`, `/api/v1/media-item`, `/api/v1/media-item-bundle(s)` | `media.py` |
| `/api/v1/environment-items` | `environments.py` |
| `/api/v1/uploads/software-games`, `/software-media`, `/software-apps` | `uploads.py` (one factory, three routers) |
| `/api/v1/launches` | `launches.py` |
| `/api/v1/jobs` | `jobs.py` |
| `/api/v1/tags`, `/api/v1/entity-links`, `/api/v1/restrictions` | `tags.py`, `entity_links.py`, `restrictions.py` |
| `/api/v1/health`, `/api/v1/filesystem` | `health.py`, `filesystem.py` |

---

## F0. Startup and teardown

Entry: ASGI startup → `lifespan` (`core/lifespan.py`).

```
init_settings()                       .env + settings DB table
setup_logging(), configure_uvicorn_logging()
                                      must run inside lifespan: uvicorn's own
                                      config.load() runs before startup and would
                                      otherwise overwrite the handlers
_register_upload_domains()            explicit register() per domain, not import-time
                                      decorator side effects, so a missing or duplicate
                                      registration fails loudly here
_ensure_default_paths()               mkdir the library tree
validate_configured_paths()           → app.state.path_warnings
[dev only] settings reset_db          unlink the DB file, then reset_db_completed()
                                      replays in-memory settings into the fresh file
init_db(), create_tables(), _apply_schema_migrations()
_ensure_owner_user()                  warn only, never creates

one session:
  _sync_first_run_from_db             sets the FirstRunGuard middleware cache
  _seed_system_environments
  _seed_default_profiles
  _seed_dosbox_environments           must follow profile seeding, links to the bundled
                                      dos profile
  _seed_system_tags
  _cleanup_stale_sessions             close LaunchHistory rows with a null ended_at,
                                      exit_code=-1
  _flag_corrupt_platform_working_paths
  commit

any seed failure → RuntimeError, startup aborts

_heal_interrupted_rom_pack_clones()
_sweep_upload_tmp()
_scan_installed_emulators()           writes install_registry
_sync_detected_emulator_paths()       → emulator_catalog.detect_and_sync_all
validate_descriptor_grant_surface()   asserts every container_broker_files[].path_key
                                      resolves; raises if not
warm the eras.yaml cache
tray.start()                          best effort
asyncio.create_task(_process_monitor_loop)   ⇒ F6
[packaged builds only] open http://127.0.0.1:8000

yield

cancel the monitor
process_registry.cleanup_exited() → write_session_ends
mark still-running sessions ended with exit_code=-15
terminate every tracked pid
tray.stop()
```

**Terminal effects:** DB initialised, migrated, and seeded; settings loaded; emulators
detected into `install_registry`; monitor running. On shutdown every tracked process is
terminated and its `LaunchHistory` row finalized.

---

## F1. Game bundle launch

`POST /api/v1/game-item-bundle/{collection_id}/launch` → `coordinator.launch_collection`.

```
require_permission("can_launch_media")
process_registry.cleanup_exited()  (+ write_session_ends for anything reaped)
resolve_launchable(collection_id)
  → builds a LaunchableEntity from the bundle's launch_disk_id leaf
  → disc_paths = every leaf's file_path in disc order
  → 422 if the bundle has no launch disc configured
_launch_entity:
  _resolve_profile_for_item           profile arg → entity.profile_item_id → else 422
  _resolve_environment_for_pc_entity  PC eras only. A console entity never touches
                                      Environment at all, not even to check for one
  hydrate_drive_for_entity            DOS drives: auto-create the Drive row, format FAT16,
                                      copy loose files with MD5 verification on first
                                      launch, set installed=True
  resolve effective media             executable_path or file_path; a directory with no
                                      drive goes through resolve_media_file_from_directory,
                                      with a PS3 target fallback
  _verify_media_path_containment      the resolved media path must sit inside the library
                                      tree
  _build_spec_for_entity              resolve_backend_name(era) → slug; get_install_path
                                      for everything except box86 and xemu, which resolve
                                      their own binary later; 422 "emulator not installed"
                                      on an empty path. Flattens every ORM field to a
                                      plain value
  launch(spec, db)                    ⇒ F3
```

`POST /api/v1/app-item-bundle/{collection_id}/launch` follows the same shape through
`launch_app_collection` and `resolve_launchable_app`, with `source_type="app"` on the spec.

---

## F2. Environment launch, with on-launch provisioning

`POST /api/v1/environment-items/{id}/launch` → `coordinator.launch_environment`.

```
require_permission("can_launch_media")
db.get(EnvironmentItem)               404 if missing
_resolve_profile_for_environment      profile arg → environment.profile_item_id →
                                      bundled-by-era → else 422
_ensure_environment_provisioned:
  needed when working_image_path is None and era ∈ PROVISIONABLE_ERAS
    vm.provision_platform
      get_install_path("86box")                     else RuntimeError
      box86.resolve_rom_path                        canonical roms/, then versioned roms-*
      provision_86box_vm                            reads the eras.yaml disk size and the
                                                    86box hardware profile. Pre-installed
                                                    MBR image → copy as disk.<ext>;
                                                    otherwise build a raw VHD footer.
                                                    ISO or cue → CD-ROM section
      ini_writer.patch_ini
    persist base_image_path (if newly derived), working_image_path, config_path, commit
    resolved_install_path and resolved_rom_path ride into the spec so F3 does not
    re-resolve them
    any exception → 422 "automatic provisioning failed"
  still no working image → 422
_build_spec_for_environment
launch(spec, db)                      ⇒ F3
```

Direct environment launches use `call_site="environment"`, which structurally never checks
`environment_not_installed`: booting in to run the OS installer is exactly how an
environment gets installed in the first place. Only `environment_not_provisioned` applies.
Do not widen this gate set.

**Terminal effects:** possible new 86Box VM directory (`emulators/86box/vms/{slug}/` with a
disk image and `86box.cfg`); the `EnvironmentItem` row updated with working, config, and
base paths; a `LaunchHistory` row; the 86Box process under a Job Object.

---

## F3. Shared launch and isolation subgraph

Entry: `coordinator.launch(spec, db)`. **Every emulator launch converges here.**

```
try_reserve(profile_item_id, emulator_slug, user_item_id)
  → 409 if a launch for that profile or (emulator, user) pair is already active.
    The check and the reservation happen atomically under process_registry's lock, so a
    concurrent second request cannot slip through the gap. Released in a finally on
    every path
create + commit LaunchHistory   (game_item_bundle_id | app_item_bundle_id |
                                 environment_item_id, whichever applies)

asyncio.to_thread(backend_router.dispatch, spec), wrapped in a 30s wait_for
  timeout             → exit_code=-1, commit, 500
  XboxDvdRipDetected  → exit_code=-1, commit, 422 with a structured error_type payload
  any exception       → exit_code=-1, commit, 500

backend_router.dispatch
  _BACKEND_MODULES[spec.slug] → importlib.import_module → module.launch(spec)
  Routes to one of backends/{dosbox,box86,xemu,rpcs3,flycast,xenia,console}.py
  (duckstation, pcsx2, mesen, and project64 all share console)

each backend, in the same order:
  validate exe, media, and era
  validate_bios_from_descriptor(slug)              ⇒ shared with F8
  write the per-launch config
    dosbox   temp conf directory
    86box    _prepare_config
    xemu     provision_xemu_defaults toml
    flycast  emu.cfg
    duckstation, pcsx2   ini RecursivePaths
  resolve_container_enabled                        profile or spec override, else catalog
                                                   and settings; a permanently-excluded
                                                   slug ignores the override and warns
  if enabled: build SandboxConfig + broker files
  launch_under_job_object(...)

launcher.launch_under_job_object                   the hard convergence point
  _load_era_limits(era)                            from eras_config.get_eras(), already
                                                   clamped to the hardcoded ceilings.
                                                   Raises if the era or either field is
                                                   missing
  get_skip_cpu_limit(slug), get_skip_memory_limit(slug), get_cpu_min_rate(era)
  container path: copy the resolved numbers onto sandbox_config, then launch_suspended
                  through sandbox.launch(config) ⇒ F3a
  native path:    launch_suspended → CreateProcessW
  run_under_job:
    WindowsJobObject(prefix + launched pid).create → CreateJobObjectW
    apply limits   (skipped entirely for container launches: sandbox_host.exe already
                    applied them before the process was resumed, so the Python-side job
                    is only a teardown handle and a launch-history record)
    AssignProcessToJobObject
      error 5 → kill, relaunch with CREATE_BREAKAWAY_FROM_JOB, re-add
      any other failure or a failed retry → kill, teardown, RuntimeError
    ResumeThread
  returns (SandboxProcess, WindowsJobObject)

_finalize_launch
  job missing or handle None → proc.kill(), error "Job Object isolation required but
                               unavailable", 500. No unsandboxed fallback
  otherwise → process_registry.register(pid, ProcessEntry); set job_isolated, sandboxed,
              limits, network_blocked on the history row; commit

bundles only (not environments):
  _poll_for_immediate_exit(proc), ~0.75s inline
    non-zero exit inside the window → terminate, record the error, surface it in this
    response. Slower crashes are still caught asynchronously by the 3s
    register_short_lived_check ⇒ F6, which flags the item for the *next* launch's response
```

### F3a. AppContainer sandbox host

```
sandbox.launch(config)   (wincage/sandbox.py)
  _validate(config)
  subprocess.Popen(sandbox_host.exe) → write the JSON stdin payload → 15s timer
  read the first stdout line (JSON: sid, pid, event_name, stage)
    stage == "error" → raise SandboxError
    otherwise → build a SandboxHandle and spawn a daemon _watch_event thread that waits on
                the Win32 event and fires EXITED / CLEANED_UP callbacks
launcher then OpenProcess(PROCESS_ALL_ACCESS, sid pid) to get a Win32 handle wrapped in a
SandboxProcess, so the Job Object can still manage it
```

**Terminal effects:** a native emulator process spawned (optionally inside an AppContainer
SID), enrolled in a per-launch-named Job Object with CPU and memory caps applied, registered
in `process_registry`, `LaunchHistory` finalized, per-backend config files written and some
cleaned up on exit via daemon threads.

---

## F4. Library ingest

Everything funnels through `backend/service/games/items.py`, which runs a fixed four-stage
pipeline. Stages are ordered so that detection completes with **zero filesystem writes**
before staging starts.

| Stage | Does |
|---|---|
| 1. `_validate_source` | Normalise and resolve the path; reject a path that matches an Environment base or working image (409) |
| 2. detect | `_detect_directory_source` or `_detect_file_source`. Zero writes. Admission checks first (`_guard_directory_source`: already tracked, out of bounds), because they are cheap DB and path work and there is nothing to gain from detecting against a folder that is already rejected |
| 3. `stage_files` | Move or copy into the domain root, dedup, cover art discovery, owned-folder reconciliation. Every mutation registers its undo on the undo stack |
| 3.5. `_finalize_row_fields` | Era resolution and detection reason, `defaults_for_era` → `lookup_environment_and_profile`, `detect_rating`, then one `classify()` call **per target** (Redump gives every disc of a set its own DAT entry and therefore its own sha1). Returns collection fields plus one leaf-fields dict per target |

A loose file runs stage 3 before stage 2, deliberately: staging resolves the final path that
detection then runs against.

`_ingest_transaction` wraps the persist step; `_replay_undo` unwinds the staging mutations
on failure.

| Entry point | Path |
|---|---|
| Manual add | `POST /api/v1/game-items` → `_ingest_media_entry` → `_prepare_item` → `_persist_collection_of_one` |
| Import from path | `POST /api/v1/game-items/import-from-path` → `path_import.stage_from_source` or `_import_in_place`, then the same funnel. Large imports run as a background job |
| Scan | `POST /api/v1/game-items/scan` → background job, re-walks disk every call, no DB writes. `GET /scan/status`, `POST /scan/{job_id}/cancel` |
| Scan import | `POST /api/v1/game-items/scan/import` → re-validates every submitted path against the DB at request time. The client-echoed era is **not** trusted: fresh on-disk detection wins, and the echoed value only ever selects which file inside a multi-format folder is authoritative |
| Chunked upload | `/api/v1/uploads/software-games` ⇒ F5 |

All mutating entry points require `can_manage_game`.

Scan and import are stateless. `GameItem.original_name`, a one-time snapshot at import,
matches disk paths to existing rows on later scans. **A DB-known path missing on disk fails
loud** ("Cannot find `<name>`, did you move or rename it?") rather than silently dropping
the row.

> **Known gap: `sha1 = NULL` on directory-shaped leaves.** `classify()` runs against the
> leaf's `file_path`. When that is a directory (PS3 folder layouts, DOS loose-file folders)
> no hash is computed and `sha1` stays `NULL`. `_reverify_leaf_in_session` then takes the
> no-baseline branch, resolves the directory to its inner media file, and stores that file's
> hash instead, so ingest and re-verify disagree about what the leaf's hash represents.

### Verification

`_reverify_leaf_in_session` (behind `POST /game-item/{leaf_id}/verify` and
`POST /game-item-bundle/{id}/verify`) reads `leaf.sha1` directly. It never parses
`detection_reason` and never fabricates a comparison value, which was the previous
implementation's bug: it parsed a hash out of the reason string and, when that failed,
silently compared a freshly computed hash against itself, which always "matched" whether the
file was good or not.

| `leaf.sha1` | Behaviour |
|---|---|
| Present | Run `classify()` fresh. Naturally re-derives `verified` if nothing changed, `caution` or `mismatch` on recognisable drift, `not_in_index` on unrecognisable drift |
| Absent | Hash the file now and resolve to `not_in_index` (hashing worked) or `unchecked` (it still cannot be hashed). Never jump straight to verified, caution, or mismatch on a leaf that was never classified at ingest |

---

## F5. Chunked upload

```
POST   /init                                    create the session, stage a directory,
                                                create the jobs entry before any bytes move
PUT    /{upload_id}/chunks/{file_idx}/{chunk}   store_chunk
POST   /{upload_id}/complete                    always 202 + job_id, finalizes as a
                                                BackgroundTask. There is no inline path
DELETE /{upload_id}                             abort
```

`core.reassemble()` writes every file of the upload into **one** slug directory, so a `.cue`
and its `.bin` land as siblings (409 on same-named files). Then the domain's own
`finalize_reassembled` dispatches on kind:

| Kind | Path |
|---|---|
| `file` | Reassemble → `find_existing_duplicate` (content dedup via `media_dup_index`, file-kind only) → `_ingest_media_entry` |
| `set` | `select_disc_pointer_files` (order preserving, companion aware: `.gdi`/`.cue`/`.chd` pointers kept in client order, companions ride along in the shared destination) → `_prepare_multi_disc` → `_persist_multi_disc_collection` |
| `folder` | `folder_ingest.ingest_folder` → `detect_disc_files` (sorted; 2 or more of **one** pointer format, 422 if formats are mixed) → multi-disc if found, else `pick_folder_launch_file` → `_ingest_media_entry` |

Set and folder share `_DISC_POINTER_EXTS` and the same `_prepare_multi_disc` builder.

Cleanup ownership is split deliberately: `core` owns the tmp staging directory (success,
abort, and the orphan sweep at startup), and the domain finalizer removes the reassembled
destination directory if ingest fails.

`media_dup_index` is an in-memory `(size, lazy sha256)` index under the media root. It
re-validates each cached hash against a live `stat()` before trusting it, so it never
produces a false positive; the worst case is a missed match.

---

## F6. Process monitoring and stop

```
_process_monitor_loop, started in F0, every 5s:
  process_registry.cleanup_exited()   poll each handle, close the job handles of reaped
                                      processes
  write_session_ends(exited)          set ended_at and exit_code
  monitor.poll_short_lived()          register_short_lived_check (F3) stored (proc, t);
                                      an exit within 3s flags the bundle
                                      launch_review_flagged=True. A clean exit code 0 is
                                      success, not a crash

POST /api/v1/launches/{history_id}/stop → coordinator.stop_launch
  404 if no record
  403 if the caller is not admin and the profile belongs to another user
  find the pid by history_id or bundle id
  process_registry.terminate  (terminate the process, tear down the job handle)
  set ended_at, exit_code=-15
```

Read paths are thin DB queries: `GET /launches`, `GET /launches/{id}`,
`GET /game-item-bundle/{id}/launches`. `DELETE /launches` (owner or admin) prunes history.

---

## F7. Emulator catalog, install, and sandbox config

Routes in `emulators.py`, all under `/api/v1/emulator-items`.

| Endpoint | Behaviour |
|---|---|
| `GET ""` | `load_catalog` plus, per slug, `get_install_path`, installer presence, git check, running status, and the settings sandbox overrides. Unauthenticated |
| `GET /attribution` | License and copyright set |
| `POST /{slug}/install` (admin) | Dispatch on `install_type`. `github_release` and `zip` → download or detect the binary, then `install_registry.set_status`. `rom_pack` → 409 if already cloning, else status `cloning` plus a background `clone_rom_pack` (git clone), ending in `complete` or `error` |
| `GET /{slug}/status` (admin) | Catalog entry, `get_install_path`, and `install_registry.get_status` |
| `DELETE /{slug}` (admin) | `consume_confirm_token` → `remove_emulator` (rmtree under `emulators/`) → status `idle`. Token from `GET /{slug}/confirm-token` |
| `PATCH /{slug}/sandbox` (admin) | Writes `sandbox_{slug}_{field}` via `settings.set_flag`. Enabling a container that the catalog marks disabled is rejected with 400 |
| `DELETE /sandbox-state` (admin) | `consume_confirm_token("sandbox-state")` → for every container-enabled entry, sweep all profile user scopes plus `shared` and call `reset_container(slug, user_id)` → `sandbox_host.exe --reset <moniker>` |
| `GET|PATCH /xemu/asset-paths` (admin) | Read, normalise, and write `emulators/xemu/xemu.toml` `[sys.files]` |

**Moniker parity matters.** Reset here and launch in F3 must agree on
`Peach1UP.{slug}.{user_item_id|shared}`, a string built in two places
(`app_container._moniker_user_scope`). Changing one without the other silently orphans
container state.

---

## F8. BIOS validation and placement

```
GET /api/v1/bios
  load_bios_requirements + check_bios_presence per entry

POST /api/v1/bios/{slug}/place  (admin)
  find the requirement                        404
  resolve dest_dir under the base             500 if it escapes
  source_path XOR uploads                     400 if both or neither
  bios_placement.place_bios_asset             dispatch by slug into the pattern, tree,
                                              pair, or fds placement helper (copy or
                                              stream_upload_to_disk, hash check for FDS)
  re-run check_bios_presence

launch time (shared with F3):
  validate_bios_from_descriptor(slug)
    iterate the descriptor's [[dependencies]] entries that carry a bios_path
    resolve under the root                    ValueError if it escapes
    _missing_required_files                   required_files, required_glob,
                                              required_glob_excludes, else non-empty-dir
    FileNotFoundError if required and missing  → the launch aborts before any spawn
```

This is data-driven from the TOML descriptors, not from Python. A static analyzer has to
read `config/emulators/*.toml` to know what actually runs.

---

## F9. Environment CRUD and health

Routes in `environments.py` → `service/environments/environments.py`.

| Endpoint | Behaviour |
|---|---|
| `POST ""` (`can_manage_environment`) | `create_environment_item`: validate era (422) and image paths → create the row → if no working image and the era is provisionable, `vm.provision_platform` (shares the provisioner with F2) → persist paths → compute status |
| `PATCH /{id}`, `DELETE /{id}` | Update, and token-gated delete via `confirmation_tokens.consume` |
| `POST /{id}/health` | `check_environment_item_health` |
| `POST /{slug}/install-media` | Upload installation media for the environment |

Health is one computation, `compute_environment_presence` plus `_compute_status(era,
working, base)`, reached from every producer: list, create, per-environment health,
`batch_health_check`, and `get_health_summary`. DOS environments are never provisioned, so
the absence of a working image is `healthy`/`unconfigured` there, not `degraded`.

`_probe_image_integrity` is a shallow check: non-empty file, first and last 512 bytes
readable. It does not parse the image format. See [SECURITY.md](SECURITY.md) Known
Limitations.

Aggregate reads live under `/api/v1/health`: `summary`, `recompute-all`, `storage-stats`,
`storage`, and `storage/rescan`.

---

## F10 to F16. Smaller flows

| Flow | Shape |
|---|---|
| **Settings** (`settings.py`) | `GET ""` returns settings minus `_`-prefixed and `_SENSITIVE_KEYS`. `PATCH ""` gates on `_USER_WRITABLE_KEYS`: path keys go to `set_path`, env-secret keys to `set_env_secret`, the rest to `_persist`. `PATCH /pin-pepper` is owner-only and separate, because it re-hashes the owner PIN. Status-only endpoints for pin-pepper, TheGamesDB, and IGDB never return values. `POST /complete-first-run` writes the DB flag and flips the middleware cache |
| **Users** (`users.py`) | `GET ""` intentionally unauthenticated, see [AUTH.md](AUTH.md). Everything else gated; owner-only create and delete; delete reassigns that user's profiles to the owner and removes their `MediaRestriction` rows before deleting |
| **Profiles** (`profiles.py`) | `GET ""` returns rows with bulk-computed item and launch counts. `POST` 409s on a slug duplicate. `PATCH /{slug}` re-slugs on a name change. `DELETE /{slug}` 403s if the profile is bundled. All mutations gate on `can_manage_game` |
| **Tags** (`tags.py`) | List with per-tag counts; create (422 blank, 409 duplicate); delete; `POST|DELETE /{tag_id}/assignments` resolves the target entity and re-checks that entity's own permission flag before linking |
| **Entity links** (`entity_links.py`) | `POST|DELETE /entity-links/{entity_type}/{entity_id}`. Polymorphic across Game, App, and Media, with two-sided authorization and explicit cleanup on delete |
| **Restrictions** (`restrictions.py`) | `GET|PUT /restrictions/{domain}/{entity_id}` for `game`, `media`, `app`. `is_admin` gated, and each domain resolves through its own `get_filtered_*` getter rather than a raw `db.get()`, so a restricted admin cannot read or edit the restriction list either |
| **Drives** (`drives.py`) | List and get authed. `GET /{id}/confirm-token` issues; `DELETE /{id}` consumes it, unlinks the image file, deletes the row |
| **Filesystem** (`filesystem.py`) | `GET /drives` (Windows only), `GET /launch-file-extensions`, `GET /browse`. Browse normalises the path and rejects anything outside the allowed roots with 400, then lists the directory skipping symlinks and hidden entries |
| **Jobs** (`jobs.py`) | `GET /jobs`, `GET /jobs/{job_id}`. Backs the nav bell for uploads, scans, and imports |
| **Metadata** (`game_metadata.py`) | `GET /metadata-search`, `GET /metadata-details`, `POST /enrich`, `POST /{id}/accept-metadata-assets`. Provider selected by the `metadata_provider` setting (`thegamesdb` or `igdb`). Search and apply are separate calls behind an explicit user action, so no API credit is spent on selection |

---

## Subsystem map

| Subsystem | Modules |
|---|---|
| API and middleware | all routes; `request_logging.py`, `security.py`, `dependencies.py` |
| Launch coordination | `launch/coordinator.py`, `launch_spec.py`, `launchable_resolver.py`, `utils/backend_router.py` |
| Backends | `backends/{dosbox,box86,xemu,rpcs3,flycast,xenia,console}.py` |
| Sandbox and isolation | in-tree `platform/windows/process/launcher.py` and `app_container.py`; vendored `wincage/{job,process,sandbox}.py` and `wincage/checker/` |
| BIOS validation | `emulator_catalog.validate_bios_from_descriptor`, `check_bios_presence`, `bios_placement.py` |
| Provisioning | `vm/provisioner.py`, `vm/vhd.py`, `ini_writer.py` |
| Emulator catalog and install | `emulator_catalog.py`, `emulator_descriptor.py`, `emulator_installer.py`, `github_release_installer.py`, `install_registry.py` |
| Ingest | `games/items.py`, `games/folder_ingest.py`, `games/path_import.py`, vendored `formatscout`, `era_media.py`, `era_defaults.py`, `drive_utils.py`, `upload_utils.py`, `rating_detect.py`, `media_dup_index.py` |
| Uploads | `uploads/core.py`, `uploads/registry.py`, `uploads/software_{games,media,apps}.py` |
| Drive and FAT | `launch/drive_hydration.py`, `drive_utils.py`, `fat/*` |
| Auth and session | `identity.py`, `auth.py`, `dependencies.py`, `rate_limit.py` |
| Process lifecycle | `process_registry.py`, `process_monitor.py`, `launch/monitor.py`, `launch/history.py` |
| Environments and health | `environments/environments.py` |
| Settings and first-run | `core/settings.py`, `utils/settings.py`, `eras_config.py` |
| Metadata | `metadata_providers/{thegamesdb,igdb}_provider.py`, `thegamesdb_client.py`, `games/enrich.py`, `games/media_link.py` |
| Confirmation tokens | cross-cutting: `confirmation_tokens.py` |

### Cross-subsystem edges

- API and middleware reach every subsystem (route entry).
- Launch coordination → Backends (dynamic dispatch) → Sandbox (every backend calls
  `launch_under_job_object`, the one true fan-in).
- Launch coordination → Provisioning (F2) → Emulator catalog (binary and ROM resolution).
- Backends → BIOS validation and Emulator catalog (container config, install path, era
  limits).
- Sandbox → Emulator catalog (`get_skip_*`, `get_container_enabled`) → Settings
  (`eras.yaml`, sandbox overrides).
- Ingest → Drive/FAT, Emulator catalog (era detection defaults), Environment dedup.
- Emulator install → Sandbox (`reset_container`), Install registry, Confirmation tokens.
- Process lifecycle ↔ Launch coordination (shared registry; the monitor finalizes
  histories).

---

## What a call-graph tool would miss

Deterministically extractable from imports alone:

- The middleware stack and dependency-injection wiring.
- `launch_under_job_object` as the fan-in of all seven backend modules; each imports it
  directly.
- `coordinator` → `drive_hydration` → `drive_utils` → `fat`, and
  `coordinator` → `provisioner` → `vhd`/`ini_writer`.
- CRUD routes → service methods; upload routes → `uploads/core`.
- `confirmation_tokens.issue`/`consume` pairs and `install_registry` state transitions.
- The era-to-emulator table in `era_defaults.defaults_for_era` and the `_BACKEND_MODULES`
  dict, both static data a tool can read literally.

Requires judgment:

- **`backend_router.dispatch`** is `_BACKEND_MODULES[spec.slug]` plus
  `importlib.import_module` plus `module.launch`. The backend is chosen by a runtime slug
  derived from era; a naive tool sees `dispatch`, not the seven possible targets.
- **String-keyed branch dispatch** in `bios_placement.place_bios_asset` and the emulator
  install route.
- **Config-driven behaviour** lives in TOML and YAML, not Python:
  `validate_bios_from_descriptor`, `app_container._resolve_path_key`, era limits. A static
  analyzer must parse `config/emulators/*.toml` and `config/eras.yaml`.
- **Runtime-state branches:** provision-needed versus already-provisioned, container-enable
  resolution, drive hydration, the ingest stage ordering, and the breakaway-retry and
  job-missing aborts.
- **Deferred execution:** `BackgroundTasks.add_task` (upload finalize, scan import, ROM
  pack clone) and `asyncio.to_thread` plus daemon threads (sandbox watcher, dosbox and xemu
  config cleanup). The edges exist statically but execution is decoupled from the call site.
- **Moniker parity** between AppContainer reset (F7) and launch (F3): one string built in
  two places, correlatable only by understanding the semantics.
