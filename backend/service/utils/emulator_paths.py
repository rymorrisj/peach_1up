"""
Derived emulator path resolution.

Platform-neutral leaf module: it depends only on ``backend.core.settings``
(itself a leaf importing nothing from ``backend``), so it can be imported from
anywhere in the codebase without risking an import cycle.

It exists to break one: ``emulator_descriptor.py`` needs the derived-path map to
check broker-file path identity, but the map used to live in
``platform/windows/app_container.py``, which imports ``emulator_catalog.py``,
which imports ``emulator_descriptor.py``. Holding the map here lets
``emulator_descriptor`` import it directly at module level, while
``app_container._resolve_path_key`` keeps its settings tier, its
``appdata_xemu`` branch, and its ``SandboxError`` raising and delegates only the
map lookup here.
"""

from __future__ import annotations

from pathlib import Path

from backend.core.settings import get_base_path


def resolve_derived_path(path_key: str, slug: str) -> str | None:
    """Resolve *path_key* to an absolute path derived from the base path.

    Covers the descriptive-name keys used by ``container_broker_files`` in
    ``config/emulators/<slug>.toml``. Keys resolved from the settings system, or
    from the environment (``appdata_xemu``), are deliberately not handled here;
    they stay with the caller that owns those tiers.

    Args:
        path_key: Value from ``container_broker_files[].path_key``.
        slug: Emulator slug; used to derive slug-specific sub-paths.

    Returns:
        The resolved absolute path as a string, or ``None`` if *path_key* is not
        a derived key. ``None`` means "not mine", not "invalid": the caller
        decides whether an unresolved key is an error.
    """
    base = get_base_path()
    derived: dict[str, Path] = {
        # Emulator install root (binary directory).
        "install_dir":  base / "emulators" / slug,
        # Per-emulator save-state directory (e.g. Flycast, Mesen, Project64).
        "saves_dir":    base / "emulators" / slug / "saves",
        # Per-emulator quick save-state directory (DuckStation, which really
        # does ship a "savestates" folder). PCSX2 does NOT: it names the same
        # thing "sstates", so it uses sstates_dir below. Do not merge the two.
        "savestates_dir": base / "emulators" / slug / "savestates",
        # PCSX2 save-state directory. PCSX2 writes to "sstates", not
        # "savestates" (confirmed against a live install actively receiving
        # .p2s writes). Kept as its own key rather than changing
        # savestates_dir, which DuckStation shares and which is correct there.
        "sstates_dir":  base / "emulators" / slug / "sstates",
        # Per-emulator memory-card directory (PCSX2, DuckStation).
        "memcards_dir": base / "emulators" / slug / "memcards",
        # Per-emulator screenshot/snapshot directory (PCSX2).
        "snaps_dir":    base / "emulators" / slug / "snaps",
        # Emulator config directory (same as install root for portable layout).
        "config_dir":   base / "emulators" / slug,
        # xemu NVRAM/VM state directory.
        "nvram":        base / "emulators" / slug / "vms",
        # Per-emulator shader/disk cache directory.
        "cache_dir":    base / "emulators" / slug / "cache",
        # Per-emulator plugin directory (Project64, capital-P singular as PJ64
        # ships it: the archive creates "Plugin", not "plugins").
        "plugin_dir":   base / "emulators" / slug / "Plugin",
        # Project64 portable EEPROM/save directory (capital-S as PJ64 writes it).
        "pj64_save_dir": base / "emulators" / slug / "Save",
        # Project64 portable config directory (capital-C as PJ64 writes it).
        "pj64_config_dir": base / "emulators" / slug / "Config",
        # PCSX2 portable inis directory (needs rw; install_dir grant is r-only).
        "inis_dir":     base / "emulators" / slug / "inis",
        # Per-emulator BIOS/firmware directory (Flycast: data/).
        "bios_dir":     base / "emulators" / slug / "data",
        # xemu HDD image fallback: grants the whole xemu emulator dir when launch_paths
        # does not supply the specific .qcow2 path.
        "hdd_image":    base / "emulators" / "xemu",
        # RPCS3 portable virtual HDD (game installs, saves, trophies).
        "dev_hdd0":     base / "emulators" / slug / "dev_hdd0",
        # RPCS3 portable firmware directory (populated by File > Install Firmware).
        "dev_flash":    base / "emulators" / slug / "dev_flash",
        # RPCS3 portable mounted-disc directory.
        "dev_bdvd":     base / "emulators" / slug / "dev_bdvd",
        # Xenia portable content directory (saves/DLC), under storage_root.
        "content":      base / "emulators" / slug / "content",
        # Xenia portable shader cache directory, under storage_root.
        "cache":        base / "emulators" / slug / "cache",
    }

    if path_key in derived:
        return str(derived[path_key])
    return None
