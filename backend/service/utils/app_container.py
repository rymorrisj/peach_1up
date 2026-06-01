"""
AppContainer provisioning module for Peach 1UP.

Reads container_broker_files from the emulator descriptor in emulators.toml
and builds the SandboxConfig that is passed to sandbox.launch().  This is
Python-side provisioning only — sandbox_host.exe handles AppContainer
creation and resource brokering at the Win32 level.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from backend.core.logger import get_logger
from backend.core.settings import get_base_path
from backend.service.utils.emulator_catalog import get_emulator, get_emulator_era
from backend.service.utils.eras_config import get_cpu_min_rate
from backend.service.utils.sandbox import sandbox
from backend.service.utils.sandbox.sandbox_config import BrokerFile, SandboxConfig
from backend.service.utils.sandbox.sandbox_error import SandboxError
from backend.service.utils.sandbox.sandbox_event import SandboxStage

logger = get_logger(__name__)

EXE_NAME: str = "sandbox_host.exe"

_ERAS_PATH: Path = get_base_path() / "config" / "eras.yaml"

# Floor mirrors MinRate in job_objects.py (cpu_min_rate_percent * 100 / 10000).
_CPU_MIN_RATE: int = get_cpu_min_rate("")


def _load_era(slug: str) -> dict:
    try:
        era_key = get_emulator_era(slug)
    except (ValueError, Exception):
        return {}
    eras = yaml.safe_load(_ERAS_PATH.read_text(encoding="utf-8")) or {}
    return eras.get(era_key, {})


def _resolve_path_key(path_key: str, slug: str) -> str:
    """Resolve a path_key to an absolute path string.

    Resolution order:
    1. Direct settings key — ``settings.get(path_key)`` (covers uppercase keys
       such as ROMS_PATH).
    2. Derived path map keyed by descriptive name (install_dir, saves_dir, etc.).

    Args:
        path_key: Value from ``container_broker_files[].path_key`` in emulators.toml.
        slug: Emulator slug; used to derive slug-specific sub-paths.

    Raises:
        SandboxError: stage=CONFIG_VALIDATION if the key cannot be resolved.
    """
    from backend.service.utils import settings as _settings

    try:
        val = _settings.get(path_key)
        if val:
            return str(val)
    except RuntimeError:
        pass

    # Step 2: derived paths — keyed by descriptive name, resolved relative to base.
    # GAMES_PATH is intentionally absent: it is a registered settings key resolved
    # by the settings.get() call in step 1 above.
    base = get_base_path()
    derived: dict[str, Path] = {
        # Emulator install root (binary directory).
        "install_dir":  base / "emulators" / slug,
        # Per-emulator save-state directory (e.g. Flycast, Mesen, Project64, ScummVM).
        "saves_dir":    base / "emulators" / slug / "saves",
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
        # Per-emulator plugin directory (Project64).
        "plugin_dir":   base / "emulators" / slug / "plugins",
        # xemu HDD image fallback: grants the whole xbox bios dir when launch_paths
        # does not supply the specific .qcow2 path.
        "hdd_image":    base / "library" / "system" / "bios" / "xbox",
    }

    if path_key in derived:
        return str(derived[path_key])

    if path_key == "appdata_xemu":
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            raise SandboxError(
                message="APPDATA environment variable is not set — cannot resolve xemu AppData path",
                stage=SandboxStage.CONFIG_VALIDATION,
                suggestions=["Ensure the application is running in a standard Windows user session"],
            )
        return str(Path(appdata) / "xemu")

    raise SandboxError(
        message=f"Cannot resolve path_key '{path_key}' for emulator '{slug}'",
        stage=SandboxStage.CONFIG_VALIDATION,
        suggestions=[
            f"Add '{path_key}' to settings.yaml or define it as a derived "
            "path in app_container._resolve_path_key()",
        ],
    )


def get_container_config(
    emulator_slug: str,
    exe_path: str,
    launch_paths: dict[str, str] | None = None,
) -> SandboxConfig:
    """Build a SandboxConfig for the given emulator.

    Reads container_broker_files from the emulator descriptor, resolves each
    path_key, then combines the resolved paths with era-derived CPU and memory
    limits into a SandboxConfig ready to pass to sandbox.launch().

    Args:
        emulator_slug: Slug matching an entry in emulators.toml.
        exe_path: Absolute path to the emulator executable.
        launch_paths: Optional mapping of path_key → absolute path.  When a
            path_key appears in this dict, the provided value is used directly
            instead of the normal resolution path.

    Returns:
        A fully populated SandboxConfig.

    Raises:
        SandboxError: stage=CONFIG_VALIDATION if any path_key cannot be resolved.
        ValueError: If emulator_slug is not found in the catalog.
    """
    descriptor = get_emulator(emulator_slug)
    era = _load_era(emulator_slug)

    files_raw = descriptor.get("container_broker_files", [])

    if any(e["path_key"] == "hdd_image" for e in files_raw):
        if not launch_paths or "hdd_image" not in launch_paths:
            logger.warning(
                "hdd_image broker_file for '%s' is using the directory placeholder "
                "(library/system/bios/xbox/); pass hdd_image in launch_paths for a "
                "tighter grant targeting the specific .qcow2 file.",
                emulator_slug,
            )

    broker_files: list[BrokerFile] = [
        BrokerFile(
            path=(
                launch_paths[entry["path_key"]]
                if launch_paths and entry["path_key"] in launch_paths
                else _resolve_path_key(entry["path_key"], emulator_slug)
            ),
            access=entry["access"],
            mode=entry.get("mode", "grant"),
        )
        for entry in files_raw
    ]

    cpu_max_rate: int = int(era.get("cpu_limit_percent", 50))
    memory_limit_mb: int | None = (
        None
        if descriptor.get("skip_memory_limit", False)
        else int(era.get("memory_limit_mb", 512))
    )

    return SandboxConfig(
        moniker=f"Peach1UP.{emulator_slug}",
        exe_path=exe_path,
        broker_files=broker_files,
        cpu_max_rate=cpu_max_rate,
        cpu_min_rate=_CPU_MIN_RATE,
        memory_limit_mb=memory_limit_mb,
    )


def validate_descriptor_grant_surface() -> None:
    """Assert every path_key in every descriptor's container_broker_files is resolvable.

    Iterates the full emulator catalog and attempts to resolve each path_key
    via _resolve_path_key.  Collects all failures and raises a single RuntimeError
    at the end so every bad key is surfaced in one startup message.

    Raises:
        RuntimeError: If any path_key in any descriptor cannot be resolved.
            Lists each failing key and the descriptor that declared it.
    """
    from backend.service.utils.emulator_catalog import load_catalog

    failures: list[str] = []
    for desc in load_catalog():
        slug = desc.get("slug", "<unknown>")
        for entry in desc.get("container_broker_files", []):
            pk = entry.get("path_key", "")
            if not pk:
                continue
            try:
                _resolve_path_key(pk, slug)
            except SandboxError:
                failures.append(f"  {pk!r} declared by '{slug}'")

    if failures:
        raise RuntimeError(
            "Startup validation failed — the following path_keys in "
            "container_broker_files cannot be resolved by _resolve_path_key:\n"
            + "\n".join(failures)
            + "\nFix: add the key to settings._DEFAULTS/_PATH_DEFAULTS or to the "
            "derived map in app_container._resolve_path_key()."
        )


def reset_container(emulator_slug: str) -> None:
    """Delete the persisted AppContainer profile for the given emulator.

    Safe to call even if the container has never been provisioned — the
    sandbox_host.exe --reset command treats a missing moniker as a no-op.

    Args:
        emulator_slug: Slug matching an entry in emulators.toml.

    Raises:
        SandboxError: stage=CONTAINER_PROVISION if the reset command fails.
    """
    sandbox.reset_container(f"Peach1UP.{emulator_slug}")
