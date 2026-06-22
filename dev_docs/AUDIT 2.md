● I have traced all four flows end-to-end against the actual code. Here are the findings. No files were edited.

---

Depth-First Audit — Launch / Provisioning / BIOS Validation

F1 — Library item launch

F1-1 (Correctness, crash) — get_base_path() is undefined in box86.py

backend/service/backends/box86.py:298 and :304 call get_base_path() inside the dgVoodoo2 injection block, but box86.py never imports it. The top-of-file imports (lines 16–29)
pull specific names from emulator_catalog, ini_writer, launcher, sandbox — none of them get_base_path, and there is no function-local import.

Why it's a problem: Any Win95/98/XP launch (item or environment — box86 is shared) with profile.enable_dgvoodoo2 = True raises NameError: name 'get_base_path' is not defined at
box86.py:298, before the library-root safety check it's meant to perform. The launch crashes on the user-facing path. It is latent only because dgVoodoo2 is an opt-in profile
flag; the feature is effectively dead-on-arrival.

Recommendation: Add from backend.core.settings import get_base_path to the module imports. This is a real bug, not a style issue — worth a fast-follow fix regardless of the rest
of this audit.

F1-2 (Correctness, dead guard) — unreachable "already installed" protection in drive hydration

backend/service/launch/drive_hydration.py:60-65 enters the copy block only when not item.installed. Inside it, line 70 re-tests if item.installed: raise RuntimeError("...already
contains installed data..."). Since item.installed is provably False in this branch, that guard can never fire; control always reaches img_path.unlink() at line 75.

Why it's a problem: The intended safety rail — refusing to silently destroy an image that already holds installed data — is unreachable. The documented unlink() "silently
discards prior image content" behavior is therefore unconditional on every pre-install launch, contradicting CLAUDE.md's "err toward doing nothing over doing something wrong."
Correctness/safety, not performance.

Recommendation: The guard should key off image content (e.g. img_path.exists() + a populated FAT), not item.installed, or the whole inner if item.installed block should be
removed and the destructive-overwrite decision surfaced to the user. Flag for a decision rather than silent fix — it touches the safety model.

F1-3 (Redundancy, low) — backend name + executable re-resolved

In coordinator.\_build_spec_for_item (coordinator.py:131) resolve_backend_name(era_enum) is called, then get_executable_path(era_enum) (backend_router.py:127) calls
resolve_backend_name again internally. Each call re-enters \_get_eras_config() (cached, so cheap) but the double resolution is gratuitous.

Recommendation: Have get_executable_path accept an already-resolved backend slug, or have \_build_spec_for_item pass the slug it already computed. Cosmetic; low priority.

---

F2 — Environment (Win9x/XP) launch + provisioning

F2-1 (Layering, the headline item) — vm/provisioner reaches into backends/box86.\_resolve_rom_path

backend/service/utils/vm/provisioner.py:188 does from backend.service.backends.box86 import \_resolve_rom_path and calls it at line 189. A service/utils module imports a private
function from a backend-layer adapter. AUDIT.md flags this as the only service→backend back-edge in the tree, and it is.

Why it's a problem: Layering inversion. \_resolve_rom_path is ROM-location policy (find the single roms\* subdir next to the binary). It currently lives in the box86 backend but
is needed by both the backend (launch, box86.py:271) and the provisioner. Importing a leading-underscore symbol across an architectural boundary couples the service layer to a
backend's internals and its private API.

Recommendation: Move \_resolve_rom_path to a shared neutral home — emulator_catalog (which already owns get_install_path/get_86box_profile and is the catalog SoT) or a small
rom_resolution util — and have both box86 and the provisioner import it from there as a public function. This removes the back-edge without changing behavior and gives the
"where is the 86Box ROM pack" question a single owner. (A move is cleaner than re-exposing it through a launch gate, since provisioning is not a launch.)

F2-2 (Redundancy / divergence risk) — base_image_path update duplicated across two layers

provisioner.provision_platform (provisioner.py:192-198) updates Platform.base_image_path from the provisioned ISO only when db is not None. coordinator.launch_environment
(coordinator.py:350-356) calls provision_platform(platform) with db defaulted to None, then performs the same update(Platform).values(base_image_path=...) itself.

Why it's a problem: The identical write exists in two places, reachable on two different call paths (platform-CRUD provision passes a db; on-launch provision does not). Any
future change to how base_image_path is derived must be made in both or they silently diverge. AUDIT.md already noted this; the depth pass confirms both branches are live.

Recommendation: Make provision_platform return the values and let exactly one caller persist them, or always pass db and delete the coordinator copy. Single writer.

F2-3 (Redundancy / correctness inconsistency) — two 86Box INI writers disagree

provisioner.provision_86box_vm (provisioner.py:131-170) writes a [Keyboard]/[Mouse] section pair and Network → net_01_link = "0". At launch, box86.\_prepare_config
(box86.py:111-116, 144-145) removes [Keyboard]/[Mouse], writes [Input devices] instead, and sets Network → net_type = "none".

Why it's a problem: The provisioner writes config keys that the very next launch deletes/overrides, and the two modules disable networking by different mechanisms (net_01_link
vs net_type). This is wasted work plus a latent correctness trap: SECURITY.md §86Box specifies net_type = none as the canonical network-off switch, so the provisioner's
net_01_link = "0" is the wrong/ineffective key (it survives only until first launch, but a provisioned-not-yet-launched VM is left with networking governed by an unintended
key). Three INI mechanisms total across the codebase (this pair + ini_writer), already noted in AUDIT.md §5.

Recommendation: Have the provisioner produce only keys that \_prepare_config does not subsequently manage, or factor the shared machine/network/disk key-set into one function
both call. At minimum, switch the provisioner to net_type = "none" so a provisioned VM is network-safe before its first launch.

F2-4 (Performance, low — admin path) — \_resolve_rom_path + get_install_path("86box") re-run

On an environment launch that triggers provisioning, get_install_path("86box") runs in provision_platform (provisioner.py:181) and again in box86.launch (box86.py:260);
\_resolve_rom_path (a base.iterdir()) runs in provision_platform (:189) and again in box86.launch (:271). Small directory scans, and provisioning is a one-time/admin path, so
severity is low — flagging for completeness, not urgency.

---

F4 — BIOS / dependency validation

F4-1 (Redundancy, the xemu triple-check) — same files stat'd up to 3× per launch

In xemu.launch (xemu.py:258, 291, 292):

1. validate_bios_from_descriptor("xemu") → checks the descriptor bios_path dir (emulators/xemu/data/default) is non-empty.
2. validate_bios_path(data_dir) (xemu.py:182-222) → checks mcpx_1.0.bin, a flash \*.bin, and xbox_hdd.qcow2 exist in data_dir.
3. provision_xemu_defaults(...) (xemu.py:138-162) → checks xbox_hdd.qcow2, mcpx_1.0.bin, and a flash \*.bin again, in the same data_dir, with no filesystem mutation between (2)
   and (3).

Why it's a problem: Steps (2) and (3) perform byte-identical existence checks on the same three files back-to-back. The FileNotFoundErrors in provision_xemu_defaults (lines 139,
149, 159) are unreachable in normal flow — validate_bios_path already guaranteed those files exist microseconds earlier. So validate_bios_path is pure redundant I/O (≈5
stat/glob calls duplicated) plus a second, divergent exception type (RuntimeError vs FileNotFoundError) for the same condition. Correctness is fine; it's wasted work and a
maintenance hazard (two validators that must be kept in sync).

Recommendation: Delete validate_bios_path and let provision_xemu_defaults be the single validator (it already raises clear, path-specific errors). Keep
validate_bios_from_descriptor only if it stays meaningful after F4-2 is resolved.

F4-2 (Correctness) — descriptor bios_path and runtime data_dir diverge under a user override

validate_bios_from_descriptor("xemu") resolves the descriptor path relative to the project root: get_base_path()/emulators/xemu/data/default (emulator_catalog.py:400, descriptor
value from config/emulators/xemu.toml). The runtime data_dir is resolved relative to the executable: get_install_path("xemu").parent/data/default (xemu.py:285-287). These match
for the bundled install, but get_install_path honors a settings.yaml XEMU_PATH override first (emulator_catalog.py:148-158).

Why it's a problem: With an external xemu binary, the descriptor gate validates a different directory than the one xemu actually reads. The gate can pass while the real data_dir
is empty (false-OK, deferred failure inside step 2/3), or fail while the real external data_dir is fully populated (false-block of a valid setup). "Where xemu BIOS lives" has
two definitions that silently disagree.

Recommendation: Pick one source of truth. Since xemu's assets are inherently next to the binary (portable mode), derive the descriptor/gate location from
get_install_path("xemu").parent too, or drop the descriptor-level check for xemu entirely and rely on the exe-relative provision_xemu_defaults (which is always correct because
it derives from exe_path). This naturally folds into F4-1.

F4-3 (Correctness, granularity mismatch) — directory-non-empty is treated as "BIOS present"

check_bios_presence (emulator_catalog.py:350-355) and validate_bios_from_descriptor (:414) both treat any non-empty directory as satisfied. For xemu, a data/default/ containing
only eeprom.bin passes the descriptor gate and reports is_present: true in GET /api/v1/bios (bios.py:38), yet validate_bios_path/provision_xemu_defaults will then fail at launch
because the real required files (mcpx, flash, qcow2) are absent.

Why it's a problem: The presence API and launch gate disagree with the actual launch requirement. A user sees a green "present" state and still cannot launch. For 86Box this is
the already-documented per-machine-completeness limitation (EMULATORS.md), but for xemu it is a strictly weaker check than the code two lines later enforces.

Recommendation: Either make check_bios_presence for file-specific deps consult a required-filenames list from the descriptor, or document that "present" means "directory
populated," not "launch-ready," and surface the stronger per-file validation result in the BIOS panel.

F4-4 (Correctness, box86 vs descriptor) — gate validates roms/, resolver needs a single roms\* subdir

validate_bios_from_descriptor("86box") checks emulators/86box/roms is non-empty (descriptor bios_path, 86box.toml). \_resolve_rom_path (box86.py:151-186) instead scans
emulators/86box/ for subdirectories whose name starts with roms and requires exactly one. The bios-place flow (\_place_tree_merge, bios_placement.py:113-132) copies the pack into
emulators/86box/roms.

Why it's a problem: Two notions of the ROM location. If a user has both roms/ (from the place flow) and a roms-5.3/ (from a manual pack extraction) under emulators/86box/, the
descriptor gate passes (roms/ non-empty) but \_resolve_rom_path raises FileNotFoundError ("No single ROM subdirectory"). The gate green-lights a state the resolver rejects.

Recommendation: Align them: have \_resolve_rom_path and the descriptor gate agree on one canonical path (the descriptor's emulators/86box/roms), with the versioned-subdir search
as an explicit documented fallback only. This also pairs with the F2-1 move — once \_resolve_rom_path is shared, it can read the descriptor bios_path rather than re-deriving by
directory-name heuristic.

---

Cross-cutting findings (the three named items)

X-1 — eras.yaml parsed via ≥6 independent paths; only the catalog copy is cached

Confirmed parse sites: emulator_catalog.\_get_eras_config (cached, :53-59; warmed at startup in lifespan.py:78-82), and uncached direct reads in eras_config.get_cpu_min_rate
(:18), era_media (:15, :28), launcher.\_load_era_limits (:46), app_container.\_load_era (:41), and provisioner.\_load_default_disk_size_mb (:36). job_objects (:40) and
app_container (:33) read once at import via module-level get_cpu_min_rate("").

Why it's a problem: Two distinct costs. (a) Performance on the launch path the user waits on: launcher.\_load_era_limits re-reads and re-parses eras.yaml on every launch
(launcher.py:210), app_container.\_load_era on every container launch, and era_media.supported_extensions_for_era on every directory-media launch — each inside
asyncio.to_thread(dispatch,...) so it blocks launch latency. Small file, so low absolute cost, but it's redundant parse work in the hot path with a cached copy sitting right
there in emulator_catalog. (b) Consistency: the cached \_ERAS_CONFIG_CACHE and the uncached readers can observe different eras.yaml content within one process if the file is
edited at runtime — different stages of a single launch could size the Job Object from stale config while the backend uses fresh config.

Recommendation: Promote \_get_eras_config() (or a thin public wrapper, e.g. eras_config.get_eras() / get_era(era)) to the single accessor and route every site through it.
emulator_catalog already imports core.settings and is the catalog SoT, but it imports app_container lazily — to avoid an import cycle, the cleanest home is the existing
service/utils/eras_config.py (currently one function) holding the cache, with emulator_catalog delegating to it. That gives one parse per process, one invalidation point, and
removes the divergence window. Implies updating ~5 call sites and deleting their local yaml.safe_load blocks.

X-2 — core/settings imports down into service/utils/settings (one-way, confirmed)

core/settings.py:5 does from backend.service.utils import settings as \_settings_module and init_settings()/get_settings() delegate to it. I verified service/utils/settings.py
imports nothing from core (no cycle) — it computes its own \_get_project_root() (:20-23), which is byte-for-byte the same frozen/parents logic as core.settings.get_base_path()
(:10-13).

Why it's a problem: It's a layering inversion (core depending on a service module) rather than a runtime bug. The duplicated root-resolution logic in two files is the concrete
maintenance hazard: a packaging change (e.g. a new frozen layout) must be fixed in both or get_base_path() and \_get_project_root() silently diverge, and they seed different path
constants used across the codebase.

Recommendation: This is an intentional façade (AUDIT.md §3 documents the two-layer settings design), so don't invert it blindly. The actionable fix is narrower: collapse the
duplicated root logic — have service/utils/settings.\_get_project_root() call core.settings.get_base_path() or vice-versa, so there is one implementation. If the façade is kept,
add a one-line module docstring note in core/settings.py stating the downward dependency is deliberate (it currently reads like an accident). Merging the two modules is not
worth it given 28 importers of the core façade.

X-3 — item.platform_id is resolved at prepare time, never persisted, but still read by the list filter

Confirmed precisely: \_prepare_item initializes row["platform_id"] = None (items.py:114), and at :247 computes \_def_platform_id via lookup_platform_and_profile but only writes
row["profile_id"] (:251) — \_def_platform_id is discarded (the inline comment at :243-246 says so). Nothing else in the ingest path writes platform_id. Meanwhile
routes/library.py:50-51 filters LibraryItem.platform_id == platform_id when the query param is supplied.

Why it's a problem: For every auto-added/scanned item, platform_id is permanently NULL. The GET /api/v1/library?platform_id=N filter (library.py:51) therefore matches nothing
for those items — a dead filter that silently returns an empty list, not an error. The frontend EditForm/useEditForm read of platform_id (per the comment) shows a blank where a
value was actually computed and thrown away. Correctness: a write/read contract that one half honors and the other half ignores.

Recommendation: Decide the intended model and make both halves agree. Given DECISIONS.md (2026-05-06 "Profile decoupled from media items"; launch resolves platform via profile,
coordinator.launch_item:320), platform_id on LibraryItem is redundant with profile_id. Cleanest fix: drop the platform_id column read paths — remove the library.py:50-51 filter
and the frontend read — rather than start persisting a denormalized field that launch doesn't consult. If product wants platform-scoped library filtering, instead persist
row["platform_id"] = \_def_platform_id at items.py:251 and index it. Either way, eliminate the half-wired state; do not leave it.

---

Severity ranking for action: F1-1 (crash, trivial fix) > F4-1/F4-2 + F2-1 (the tangled xemu/box86 cluster the audit targeted) > X-3 (silent dead filter) > F1-2/F2-3
(safety/correctness inconsistencies) > X-1 (launch-path I/O + consistency) > F2-2, X-2, F4-3/F4-4 (divergence-risk cleanups) > F1-3, F2-4 (cosmetic). All recommendations only —
no code changed.
