"""
AppContainer provisioning module for Peach 1UP.

Reads container_dacl_grants from the emulator descriptor in emulators.toml
and builds the SandboxConfig that is passed to sandbox.launch().  This is
Python-side provisioning only — sandbox_host.exe handles AppContainer
creation and DACL application at the Win32 level.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from backend.core.logger import get_logger
from backend.core.settings import get_base_path
from backend.service.utils.emulator_catalog import get_emulator
from backend.service.utils.sandbox import sandbox
from backend.service.utils.sandbox.sandbox_config import DaclGrant, SandboxConfig
from backend.service.utils.sandbox.sandbox_error import SandboxError
from backend.service.utils.sandbox.sandbox_event import SandboxStage

logger = get_logger(__name__)

EXE_NAME: str = "sandbox_host.exe"

_ERAS_PATH: Path = get_base_path() / "config" / "eras.yaml"

# Maps emulator slug → the era used to derive CPU and memory limits.
# For emulators that serve multiple eras (86box: win95/win98/winxp), the
# most-demanding era is used so the container is never under-resourced.
_SLUG_TO_ERA: dict[str, str] = {
    "dosbox-x":    "dos",
    "86box":       "winxp",
    "scummvm":     "dos",
    "duckstation": "ps1",
    "pcsx2":       "ps2",
    "xemu":        "xbox",
    "mesen":       "nes",
    "project64":   "n64",
    "flycast":     "dreamcast",
}

def _load_cpu_min_rate() -> int:
    try:
        eras = yaml.safe_load(_ERAS_PATH.read_text(encoding="utf-8")) or {}
        val = eras.get("cpu_min_rate_percent")
        if val is not None:
            return int(val)
    except Exception:
        pass
    logger.warning(
        "cpu_min_rate_percent not found in eras.yaml; defaulting to 5."
    )
    return 5


# Floor mirrors MinRate in job_objects.py (cpu_min_rate_percent * 100 / 10000).
_CPU_MIN_RATE: int = _load_cpu_min_rate()


def _load_era(slug: str) -> dict:
    era_key = _SLUG_TO_ERA.get(slug)
    if not era_key:
        return {}
    eras = yaml.safe_load(_ERAS_PATH.read_text(encoding="utf-8")) or {}
    return eras.get(era_key, {})


def _resolve_path_key(path_key: str, slug: str) -> str:
    """Resolve a path_key to an absolute path string.

    Resolution order:
    1. Direct settings key — ``settings.get(path_key)`` (covers uppercase keys
       such as ROM_PATH, GAMES_PATH, PS1_BIOS_PATH, DREAMCAST_BIOS_PATH,
       XBOX_BIOS_PATH, BIOS_PATH).
    2. Derived path map keyed by descriptive name (install_dir, saves_dir, etc.).

    Args:
        path_key: Value from ``container_dacl_grants[].path_key`` in emulators.toml.
        slug: Emulator slug; used to derive slug-specific sub-paths.

    Raises:
        SandboxError: stage=CONFIG_VALIDATION if the key cannot be resolved.
    """
    from backend.service.utils import settings as _settings

    # Step 1: direct settings lookup.
    try:
        val = _settings.get(path_key)
        if val:
            return str(val)
    except RuntimeError:
        pass

    # Step 2: derived paths.
    base = get_base_path()
    derived: dict[str, Path] = {
        "install_dir":  base / "emulators" / slug,
        "games_dir":    base / "library" / "games",
        "saves_dir":    base / "library" / "saves",
        "config_dir":   base / "emulators" / slug,
        "nvram":        base / "emulators" / slug / "vms",
        "cache_dir":    base / "emulators" / slug / "cache",
        "memcards_dir": base / "library" / "saves" / slug,
        "snaps_dir":    base / "library" / "saves" / slug / "snaps",
        "plugin_dir":   base / "emulators" / slug / "plugins",
        "hdd_image":    base / "library" / "bios" / "xbox",
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

    Reads container_dacl_grants from the emulator descriptor, resolves each
    path_key, then combines the resolved paths with era-derived CPU and memory
    limits into a SandboxConfig ready to pass to sandbox.launch().

    Args:
        emulator_slug: Slug matching an entry in emulators.toml.
        exe_path: Absolute path to the emulator executable.
        launch_paths: Optional mapping of path_key → absolute path.  When a
            path_key appears in this dict, the provided value is used directly
            instead of the normal resolution path.  Pass ``hdd_image`` here at
            launch time to narrow the xemu DACL grant to the specific .qcow2
            file rather than the directory placeholder.

    Returns:
        A fully populated SandboxConfig.

    Raises:
        SandboxError: stage=CONFIG_VALIDATION if any path_key cannot be resolved.
        ValueError: If emulator_slug is not found in the catalog.
    """
    descriptor = get_emulator(emulator_slug)
    era = _load_era(emulator_slug)

    grants_raw = descriptor.get("container_dacl_grants", [])

    if any(e["path_key"] == "hdd_image" for e in grants_raw):
        if not launch_paths or "hdd_image" not in launch_paths:
            logger.warning(
                "hdd_image grant for '%s' is using the directory placeholder "
                "(library/bios/xbox/); pass hdd_image in launch_paths for a "
                "tighter DACL grant targeting the specific .qcow2 file.",
                emulator_slug,
            )

    dacl_grants: list[DaclGrant] = [
        DaclGrant(
            path=(
                launch_paths[entry["path_key"]]
                if launch_paths and entry["path_key"] in launch_paths
                else _resolve_path_key(entry["path_key"], emulator_slug)
            ),
            access=entry["access"],
        )
        for entry in grants_raw
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
        dacl_grants=dacl_grants,
        cpu_max_rate=cpu_max_rate,
        cpu_min_rate=_CPU_MIN_RATE,
        memory_limit_mb=memory_limit_mb,
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
