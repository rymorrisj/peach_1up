Depth-First Audit — Pass 2: Library Scan/Ingest (F3), Sandbox/Job Object Launch (F5), INI-writer Fragmentation

Read-only. No files edited, no tests/installs run. Verified against code, not AUDIT.md summaries. Where a finding overlaps the prior pass it is marked (re-confirmed) and not
re-litigated.

Named item #1 — INI-writer fragmentation: third writer (RESOLVED, mostly a non-finding)

What's actually happening. ini_writer.py is a generic configparser read-edit-write utility (patch_ini/write_ini, lines 15–75) with no hardcoded keys. Its callers are box86.py
(write_ini :147, patch_ini :206, :283) and provisioner.py (patch_ini :170). So the F2-3 86Box disagreement (provisioner vs box86.\_prepare_config) is two key-sets fed into the
same writer, not a third mechanism — ini_writer does not conflict with either; they both use it.

The genuinely separate mechanism is the hand-rolled, line-based \_write_ini_key, duplicated byte-identically in console.py:33-71 and flycast.py:30-68. I diffed them: identical.
Their key-sets are scoped to entirely different emulators:

- console/DuckStation → settings.ini [GameList] RecursivePaths (console.py:111)
- console/PCSX2 → inis/PCSX2.ini [GameList] RecursivePaths (console.py:116)
- flycast → emu.cfg [config] Dreamcast.ContentPath (flycast.py:107)

None touch 86Box keys. So there is no three-way conflict — the question is closed: two mechanisms (configparser for 86Box; line-based for console/Dreamcast), one of which is
duplicated.

Why two mechanisms legitimately exist (worth recording so nobody "unifies" them wrongly): configparser strips comments and rewrites formatting; emu.cfg/PCSX2.ini are
hand-maintainable files where the line-based writer deliberately preserves all other content exactly (its docstring says so). That's a justified second style, but an unjustified
duplication between console and flycast. (Layering/DRY.)

Recommendation. Hoist the single \_write_ini_key into one shared util (e.g. add a comment-preserving set_ini_key next to patch_ini in ini_writer.py) and have both console.py and
flycast.py import it. Keep the configparser path for 86Box. Do not merge the two styles. This is the only actionable item from the "three INI approaches" note — and it's a small
DRY cleanup, not a correctness bug.

---

F3 — Library scan / ingest

F3-1 (Performance, bulk path) — full-file sha1+md5 runs before cheap extension signals, on every scanned item

detect() runs Tier-1 hash lookup first (detector.py:68-75) and only falls through to extension/magic dispatch (\_detect_file, lines 93–176) if it misses. hash_lookup.lookup reads
the entire file computing both sha1 and md5 (hash_lookup.py:20-23). The index JSON is mtime-cached (\_index_cache, good), but the per-file hashing is not.

Why it's a problem. Performance on a bulk path. A library scan of hundreds of multi-GB ISOs reads every byte of every file and hashes it twice, synchronously on the scan request
thread — even for formats whose extension already determines the era deterministically (.nes, .z64, .sfc, .xiso, lines 103–125 return confidence 0.7 from extension alone).
Those items pay a full double-hash before the cheap branch they would have hit anyway.

Recommendation. Either (a) short-circuit extension-deterministic formats ahead of the Tier-1 hash, or (b) compute sha1 first and only compute md5 on a sha1 miss
(hash_lookup.py:16-23), halving the read-bound work, or (c) gate hash lookup behind a size cap. The hash tier is needed for content-addressed titles, so keep it — just stop
running it eagerly for items that don't need it.

F3-2 (Redundancy) — detection (and its full-file hashing) is recomputed between scan-preview and import

The scan-preview endpoint calls \_smart_detect(era_path) per entry (library.py:210). Import (import_scan_results) then calls \_prepare_item per selected path (library.py:264),
which calls \_smart_detect again (items.py:161/170/220). The preview snapshot is consulted at import only for the title (title_map, library.py:250) — the detected
era/reason/requires_install are discarded and recomputed.

Why it's a problem. Performance/redundancy on the bulk path: every selected file is full-file-hashed twice across the two-phase flow.

Recommendation. Carry era, detection_reason, and requires_install in the preview snapshot and reuse them at import (skip re-detection when path+mtime+size are unchanged), or add
a short-lived detection cache keyed by (path, st_mtime, st_size).

F3-3 (Redundancy, minor) — directory items detect twice

For a directory, \_prepare_item calls \_smart_detect(media_src) (items.py:161), then resolves the inner media file and calls \_smart_detect(resolved_media) again
(items.py:168-170). The first call is on the directory (its Tier-1 hash open fails fast and is swallowed, so not a full-file hash), so cost is modest, but it's still two
detection passes.

Recommendation. Resolve the media file first, then detect once. Low priority.

F3-4 (Correctness, re-confirmed) — item.platform_id resolved but never persisted, still read downstream

Re-confirmed in the F3 trace exactly as the prior pass filed it: \_prepare_item computes \_def_platform_id (items.py:247) but writes only profile_id (:251); platform_id stays None
(:114), while library.py's list filter and the frontend still read it. This is the existing FIX-SOON 3-5 contradiction — flagged as still open, not re-derived. No new
recommendation beyond the prior pass (persist it or remove the dead reads).

---

F5 — Sandbox / Job Object launch sequence

F5-1 (Concurrency, PX-4 blocker) — two single-instance assumptions: the profile_id gate and the per-slug AppContainer moniker

Two distinct places assume one-instance-at-a-time:

1. \_gate_single_active_launch(gate_profile_id) (coordinator.py:112-116) scans the registry and blocks any second launch sharing a profile_id.
2. The AppContainer moniker is per-emulator-slug, not per-instance: moniker=f"Peach1UP.{emulator_slug}" (app_container.py:190, passed to sandbox.launch → sandbox.py:299).
   reset_container deletes that shared moniker (app_container.py:246).

Why it's a problem. Concurrency — directly relevant to PX-4. Two concurrent launches of the same emulator would share one AppContainer profile/SID and the same rw broker grants
(saves_dir, memcards_dir, inis_dir, savestates_dir from \_resolve_path_key, lines 71–101) — colliding on save/config files — and a reset of one would delete the profile out from
under the other. The Job Object layer is already concurrency-safe (PID-unique names, ERROR_ALREADY_EXISTS treated as fatal, job_objects.py:103-116), so these two are the real
blockers.

Recommendation. For PX-4: make the moniker per-instance (suffix with pid or a launch id), point per-instance writable grants at instance-scoped dirs, and replace the profile_id
gate with a per-instance (or capability/seat-count) policy. Flag now; implementation is out of scope per the brief.

F5-2 (Correctness + redundancy) — a container launch reads era limits twice, via two functions with different keys and different failure modes

On a container-enabled launch, era resource limits are sourced twice from eras.yaml:

- launcher.\_load_era_limits(era) (launcher.py:43-72) — keyed by era, strict: raises RuntimeError if the era is missing or fields are absent. Feeds the WindowsJobObject.
- app_container.\_load_era(slug) → get_emulator_era(slug) (app_container.py:36-42) — keyed by the slug's era, lenient: a broad except (ValueError, Exception) returns {}, after
  which get_container_config silently substitutes defaults cpu_limit_percent=50 / memory_limit_mb=512 (app_container.py:182-187). Feeds the SandboxConfig passed to
  sandbox_host.exe.

Why it's a problem. Correctness + redundancy. The same launch derives its CPU/memory caps from two independent reads that can silently disagree, and the container path masks a
misconfigured/missing era as silent defaults while the Job Object path would have raised loudly for the same condition. The result: a container emulator can run at 50%/512 MB
defaults that don't match its actual era, with no error — violating the project's fail-loudly convention. (The broad except (ValueError, Exception) is the swallow point AUDIT
§10 already flagged for redundancy; here it's also a correctness hazard.)

Recommendation. Have both paths call one shared era-limit accessor (ties into the prior pass's cross-cutting "single eras.yaml accessor" recommendation). Narrow \_load_era's
except to the specific lookup error and let a genuinely missing era raise, matching \_load_era_limits. At minimum, log a warning when defaults are substituted instead of
substituting silently.

F5-3 (Concurrency/handle-lifecycle) — registry and teardown paths are PX-4-safe; one stale-config caveat

Affirming (not a bug): process_registry is pid-keyed and lock-guarded (process_registry.py:21-95); terminate() does full job_handle.teardown() (kill) while cleanup_exited() does
job_handle.close() (handle-only, process already exited) — correct asymmetry. The only caveat: \_CPU_MIN_RATE_PERCENT (job_objects.py:40) and \_CPU_MIN_RATE (app_container.py:33)
are read once at module import; if eras.yaml's cpu_min_rate changes they're stale until process restart. Harmless today (no live config reload), but note it for any future
reload feature.

Recommendation. No action now; revisit if config hot-reload is added.

F5-4 (Correctness, cosmetic, re-confirmed) — sandbox error strings name the wrong binary

sandbox.py user-facing error messages say peach_sandbox.exe (lines 220, 232, 249, 258, 266, 353) while the actual binary is sandbox_host.exe (EXE_NAME, :24). AUDIT §10 already
filed this. Recommend correcting the strings; the \_exe() resolution itself is correct.

Severity ranking (most actionable first)

F5-1 (PX-4 concurrency blocker: per-slug moniker + profile_id gate) > F5-2 (silent default-limit divergence on container launches — correctness) > F3-1 (eager full-file
double-hash on bulk scans — performance) > F3-2 (scan/import re-hash redundancy) > F3-4 (platform_id, re-confirmed open) > INI-writer DRY (console/flycast \_write_ini_key
duplication — the only real item from the "third writer" question) > F3-3, F5-3, F5-4 (minor/cosmetic). The "three INI writers" concern is downgraded: it's two justified
mechanisms with one duplicated helper, not a 86Box key conflict.
