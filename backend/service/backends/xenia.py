"""Xenia backend for Peach 1UP.

Handles Xbox 360 launches. CLI syntax (`--target=<path>`) was verified live
in this pass by running the real xenia.exe under Wine against a Halo 3 ISO
and confirming it loaded the disc's content/achievements before being killed.

The GPU backend (D3D12 vs Vulkan) tradeoff, see xenia.toml's
known_limitations, is deliberately not decided here. Xenia reads its own
gpu setting from xenia.config.toml on startup; this backend never overrides
it, so whatever the user has configured there is honored. _warn_if_risky_gpu
only logs a warning if that file still has the crash-prone default, it never
writes to it.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Tuple

from backend.core.logger import get_logger
from backend.service.utils.detection import resolve_xex_target
from backend.service.utils.emulator_catalog import (
    get_emulator,
    get_install_path,
    resolve_container_enabled,
    build_media_broker_config,
)
from backend.service.utils.file_types import supported_extensions_for_era
from backend.service.utils.platform.windows.process.launcher import launch_under_job_object
from wincage import SandboxProcess, WindowsJobObject

logger = get_logger(__name__)

if TYPE_CHECKING:
    from backend.service.launch.launch_spec import LaunchSpec

_RISKY_GPU_VALUES = {"any", "d3d12", ""}

# XEX folder-shape resolution (MediaTarget, resolve_xex_target) now lives in
# backend.service.utils.detection, shared with backend.service.games.items'
# ingest-time detection instead of each carrying its own copy. Previously a
# private, underscore-prefixed transplant here from the formatscout vendor
# package (services/vendor/formatscout/smart_media_detector, as it existed
# at commit f3fde90 before its working-tree removal); restored to a shared
# module since this is Peach 1UP-specific launch-target logic, not format
# detection, and belongs outside formatscout regardless.


def _warn_if_risky_gpu(install_dir: Path) -> None:
    config_path = install_dir / "xenia.config.toml"
    if not config_path.is_file():
        return
    try:
        cfg = tomllib.loads(config_path.read_text(encoding="utf-8"))
        gpu = cfg.get("GPU", {}).get("gpu", "any")
    except Exception:
        return
    if gpu in _RISKY_GPU_VALUES:
        logger.warning(
            "xenia: gpu backend is '%s' in %s, which resolves to D3D12, confirmed to "
            "trigger an AMD driver timeout during gameplay. Set gpu = \"vulkan\" to avoid "
            "it (Xenia's own Vulkan FBO path is early/incomplete but has run titles "
            "successfully in testing). See xenia.toml's known_limitations.",
            gpu, config_path,
        )


def launch(spec: "LaunchSpec") -> Tuple[SandboxProcess, WindowsJobObject]:
    """Launch Xenia with the given Xbox 360 disc image under Job Object isolation.

    Args:
        spec: LaunchSpec with era="xbox360" and media_path set to the disc
            image (.iso) to boot.

    Returns:
        Tuple of (SandboxProcess, WindowsJobObject).

    Raises:
        FileNotFoundError: If the executable or media file is missing.
        ValueError: If the media extension is unsupported.
        RuntimeError: If process launch fails.
    """
    entry = get_emulator("xenia")
    display_name = entry.get("display_name", "xenia")
    # eras.yaml is the single enforced source for launch-time format
    # validation (matches dosbox.py/flycast.py/xemu.py's pattern), not the
    # TOML descriptor's own supported_formats field, which stays display-only
    # (surfaced by GET /emulators) and is now cross-checked against eras.yaml
    # at startup by EmulatorDescriptor's validator instead of trusted here.
    supported_formats = frozenset(supported_extensions_for_era("xbox360"))

    install_path = get_install_path("xenia")
    if install_path is None or not install_path.is_file():
        raise FileNotFoundError(
            f"{display_name} executable not found. Install it via the Emulators page."
        )
    install_dir = install_path.parent

    if spec.media_path is None:
        raise FileNotFoundError("Xenia requires a disc image to launch (media_path was not set).")
    if not spec.media_path.exists():
        raise FileNotFoundError(f"Media file not found: {spec.media_path}")

    if spec.media_path.is_dir():
        # resolve_xex_target now comes from backend.service.utils.detection,
        # the same shared resolver items.py calls at ingest time (see the
        # module-level note above).
        xex_target = resolve_xex_target(spec.media_path)
        if xex_target is None:
            raise FileNotFoundError(
                f"No bootable Xbox 360 title found in '{spec.media_path}' "
                "(expected a .xex file, ideally named default.xex)."
            )
        target_path = xex_target.launch_path
    else:
        if spec.media_path.suffix.lower() not in supported_formats:
            raise ValueError(
                f"Unsupported media format '{spec.media_path.suffix}'. "
                f"{display_name} supports: {', '.join(sorted(supported_formats))}"
            )
        target_path = spec.media_path

    _warn_if_risky_gpu(install_dir)

    args = [f"--target={target_path}"]
    job_name_prefix = f"Peach1UP_xenia_{target_path.stem}"

    container_enabled = resolve_container_enabled("xenia", spec.container_enabled)
    # target_path (not spec.media_path) is passed here deliberately: for the
    # directory case, target_path.parent == spec.media_path exactly (see
    # detection.xex.find_default_xex, top-level only), so the broker's parent-dir grant
    # still covers the whole extracted folder including sibling resource
    # files, and its exact-file entry gets a real file handle instead of
    # silently failing on a directory (CreateFileW without
    # FILE_FLAG_BACKUP_SEMANTICS cannot open a directory handle).
    sandbox_config = build_media_broker_config(
        "xenia", str(install_path), target_path, spec.user_item_id, container_enabled)

    logger.debug("xenia.launch: args=%s", args)
    return launch_under_job_object(
        executable_path=str(install_path),
        args=args,
        era=spec.era,
        job_name_prefix=job_name_prefix,
        slug="xenia",
        cwd=str(install_dir),
        container_enabled=container_enabled,
        sandbox_config=sandbox_config,
    )
