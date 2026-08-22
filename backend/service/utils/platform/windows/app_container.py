"""
AppContainer provisioning module for Peach 1UP.

Reads container_broker_files from the emulator descriptor in
config/emulators/<slug>.toml and builds the SandboxConfig that is passed to
wincage.launch().  This is Python-side provisioning only: sandbox_host.exe
handles AppContainer creation and resource brokering at the Win32 level.
"""

from __future__ import annotations

import os
from pathlib import Path

import wincage
from backend.core.logger import get_logger
from backend.service.utils.emulator_catalog import (
    get_emulator,
    get_emulator_era,
    get_skip_cpu_limit,
    get_skip_memory_limit,
)
from backend.service.utils.emulator_paths import resolve_derived_path
from backend.service.utils.eras_config import get_cpu_min_rate, get_era
from wincage import BrokerFile, SandboxConfig, SandboxError, SandboxStage

logger = get_logger(__name__)

# Floor mirrors MinRate in job_objects.py (cpu_min_rate_percent * 100 / 10000).
_CPU_MIN_RATE: int = get_cpu_min_rate("")


def _load_era(slug: str) -> dict:
    """Load the eras.yaml block for *slug*'s era.

    Raises (matching launcher._load_era_limits's fail-loud behaviour for the
    same condition): ValueError if the emulator descriptor has no usable
    ``era`` field, RuntimeError if that era has no block in eras.yaml.
    """
    era_key = get_emulator_era(slug)
    era = get_era(era_key)
    if not era:
        raise RuntimeError(
            f"Era '{era_key}' (used by emulator '{slug}') not found in eras.yaml."
        )
    return era


def _resolve_path_key(path_key: str, slug: str) -> str:
    """Resolve a path_key to an absolute path string.

    Resolution order:
    1. Derived path map keyed by descriptive name (install_dir, saves_dir,
       etc.). Checked first because this vocabulary is descriptor-controlled
       (fixed by the schema, not by user-editable settings), so it must win
       over a same-named settings row rather than be silently shadowed by
       one. A settings key happening to be spelled "cache", "content",
       "nvram", or "config_dir" must not redirect a grant the descriptor
       already gave a fixed meaning to.
    2. Direct settings key, ``settings.get(path_key)`` (covers uppercase
       keys such as ROMS_PATH that the derived map doesn't recognize).

    Args:
        path_key: Value from ``container_broker_files[].path_key`` in the
            emulator's config/emulators/<slug>.toml descriptor.
        slug: Emulator slug; used to derive slug-specific sub-paths.

    Raises:
        SandboxError: stage=CONFIG_VALIDATION if the key cannot be resolved.
    """
    # Step 1: derived paths, keyed by descriptive name, resolved relative to
    # base. The map itself lives in emulator_paths.py, a leaf module depending
    # only on backend.core.settings, so emulator_descriptor.py can import it at
    # module level without the cycle this module would otherwise create.
    derived_path = resolve_derived_path(path_key, slug)
    if derived_path is not None:
        return derived_path

    # Step 2: settings tier, only for keys the derived map doesn't recognize.
    from backend.service.utils import settings as _settings

    try:
        val = _settings.get(path_key)
        if val:
            return str(val)
    except RuntimeError:
        pass

    if path_key == "appdata_xemu":
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            raise SandboxError(
                message="APPDATA environment variable is not set, cannot resolve xemu AppData path",
                stage=SandboxStage.CONFIG_VALIDATION,
                suggestions=["Ensure the application is running in a standard Windows user session"],
            )
        return str(Path(appdata) / "xemu")

    raise SandboxError(
        message=f"Cannot resolve path_key '{path_key}' for emulator '{slug}'",
        stage=SandboxStage.CONFIG_VALIDATION,
        suggestions=[
            f"Add '{path_key}' to settings or define it as a derived "
            "path in emulator_paths.resolve_derived_path()",
        ],
    )


def _moniker_user_scope(user_item_id: int | None) -> str:
    """Map a profile's user_item_id to the moniker's user-scope segment.

    Profiles with no associated user (e.g. bundled profiles) fall back to a
    fixed "shared" scope rather than a per-user one.
    """
    return str(user_item_id) if user_item_id is not None else "shared"


def build_container_moniker(emulator_slug: str, user_item_id: int | None) -> str:
    """Build the AppContainer moniker string for an emulator/user-scope pair.

    Pure string construction, no I/O and no provisioning. This is the single
    source of truth for the moniker format, shared by get_container_config
    (which embeds the result in the SandboxConfig passed to wincage.launch())
    and reset_container, and callable from a read path (e.g. an API response)
    that needs to display the moniker without provisioning a container.
    """
    return f"Peach1UP.{emulator_slug}.{_moniker_user_scope(user_item_id)}"


def get_container_config(
    emulator_slug: str,
    exe_path: str,
    launch_paths: dict[str, str] | None = None,
    user_item_id: int | None = None,
) -> SandboxConfig:
    """Build a SandboxConfig for the given emulator.

    Reads container_broker_files from the emulator descriptor, resolves each
    path_key, then combines the resolved paths with era-derived CPU and memory
    limits into a SandboxConfig ready to pass to wincage.launch().

    Args:
        emulator_slug: Slug matching a config/emulators/<slug>.toml descriptor.
        exe_path: Absolute path to the emulator executable.
        launch_paths: Optional mapping of path_key → absolute path.  When a
            path_key appears in this dict, the provided value is used directly
            instead of the normal resolution path.
        user_item_id: The launching profile's user_item_id, used to scope the
            AppContainer moniker per-user so two users sharing an emulator
            don't collide on the same sandbox profile/SID. None falls back to
            a "shared" scope (e.g. bundled profiles with no user_item_id).

    Returns:
        A fully populated SandboxConfig.

    Raises:
        SandboxError: stage=CONFIG_VALIDATION if any path_key cannot be resolved.
        ValueError: If emulator_slug is not found in the catalog.
    """
    descriptor = get_emulator(emulator_slug)
    era = _load_era(emulator_slug)

    files_raw = descriptor.get("container_broker_files", [])

    if any(e.get("path_key") == "hdd_image" for e in files_raw):
        if not launch_paths or "hdd_image" not in launch_paths:
            logger.warning(
                "hdd_image broker_file for '%s' is using the directory placeholder "
                "(emulators/xemu/); pass hdd_image in launch_paths for a "
                "tighter grant targeting the specific .qcow2 file.",
                emulator_slug,
            )

    broker_files: list[BrokerFile] = [
        BrokerFile(
            path=(
                entry["path"]
                if "path" in entry
                else (
                    launch_paths[entry["path_key"]]
                    if launch_paths and entry["path_key"] in launch_paths
                    else _resolve_path_key(entry["path_key"], emulator_slug)
                )
            ),
            access=entry["access"],
            mode=entry.get("mode", "grant"),
        )
        for entry in files_raw
    ]

    cpu_limit_percent = era.get("cpu_limit_percent")
    if cpu_limit_percent is None:
        raise RuntimeError(
            f"cpu_limit_percent not defined in eras.yaml for the era used by emulator '{emulator_slug}'."
        )
    cpu_max_rate: int = int(cpu_limit_percent)

    memory_limit_mb: int | None = None
    # Resolved through get_skip_memory_limit (not descriptor.get), the same
    # bug class as skip_cpu_limit below: descriptor.get() ignores the
    # sandbox_<slug>_skip_memory_limit settings override set by
    # PATCH /emulators/{slug}/sandbox, which launcher.py's Python-side Job
    # Object path already honours via this resolver.
    if not get_skip_memory_limit(emulator_slug):
        memory_limit_mb_cfg = era.get("memory_limit_mb")
        if memory_limit_mb_cfg is None:
            raise RuntimeError(
                f"memory_limit_mb not defined in eras.yaml for the era used by emulator '{emulator_slug}'."
            )
        memory_limit_mb = int(memory_limit_mb_cfg)

    return SandboxConfig(
        moniker=build_container_moniker(emulator_slug, user_item_id),
        exe_path=exe_path,
        broker_files=broker_files,
        cpu_max_rate=cpu_max_rate,
        cpu_min_rate=_CPU_MIN_RATE,
        # Resolved through get_skip_cpu_limit (not descriptor.get) so the
        # sandbox_<slug>_skip_cpu_limit settings override set by
        # PATCH /emulators/{slug}/sandbox is honoured here too, matching the
        # resolution launcher.py uses for the Python-side Job Object. Without
        # this the container path applied the CPU cap unconditionally, ignoring
        # both tiers.
        skip_cpu_limit=get_skip_cpu_limit(emulator_slug),
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
            "Startup validation failed, the following path_keys in "
            "container_broker_files cannot be resolved by _resolve_path_key:\n"
            + "\n".join(failures)
            + "\nFix: add the key to settings._DEFAULTS/_PATH_DEFAULTS or to the "
            "derived map in emulator_paths.resolve_derived_path()."
        )


def reset_container(emulator_slug: str, user_item_id: int | None = None) -> None:
    """Delete the persisted AppContainer profile for the given emulator and user scope.

    Safe to call even if the container has never been provisioned, the
    sandbox_host.exe --reset command treats a missing moniker as a no-op.

    Args:
        emulator_slug: Slug matching a config/emulators/<slug>.toml descriptor.
        user_item_id: The user scope to reset (matches the user_item_id used to build
            the moniker at launch time). None resets the "shared" scope.

    Raises:
        SandboxError: stage=CONTAINER_PROVISION if the reset command fails.
    """
    wincage.reset_container(build_container_moniker(emulator_slug, user_item_id))
