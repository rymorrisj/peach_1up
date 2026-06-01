"""xemu backend for Peach 1UP.

Handles original Xbox launches. Validates the binary path, disc image, and
Xbox BIOS directory, then launches xemu under Job Objects with network blocked.

Xbox BIOS files (MCPX ROM and BIOS ROM) must be dumped from original Xbox
hardware the user owns. Peach 1UP does not provide, link to, or assist with
acquiring BIOS files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from backend.constants import ERA_MEDIA_TYPES
from backend.constants_generated import Era
from backend.models.platform import Platform
from backend.service.utils.emulator_catalog import (
    get_container_enabled,
    get_container_config as get_emulator_container_config,
)
from backend.service.utils.process.launcher import launch_under_job_object
from backend.service.utils.sandbox_process import SandboxProcess
from backend.service.utils.process.job_objects import WindowsJobObject
from backend.core.settings import get_base_path
from backend.service.utils.settings import get_binary_path

SUPPORTED_ERAS = {Era.XBOX.value}
SUPPORTED_MEDIA = ERA_MEDIA_TYPES[Era.XBOX]


def validate_media(media_path: Path) -> None:
    """Validate that the disc image exists and has a supported extension.

    Args:
        media_path: Path to the Xbox disc image.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file extension is not supported.
    """
    if not media_path.exists():
        raise FileNotFoundError(f"Media file not found: {media_path}")
    if media_path.suffix.lower() not in SUPPORTED_MEDIA:
        raise ValueError(
            f"Unsupported media format '{media_path.suffix}'. "
            f"xemu supports: {', '.join(sorted(SUPPORTED_MEDIA))}"
        )


def validate_bios_path() -> None:
    """Validate that the asset files declared in emulators/xemu/xemu.toml exist on disk.

    Reads flash_path, bios_path, and hdd_path from the global xemu config and
    verifies each file is present. Paths may be absolute or relative to the
    project root.

    Raises:
        RuntimeError: If the config is missing, a key is unset, or a file is absent.
    """
    import tomllib

    base = get_base_path()
    xemu_toml = base / "emulators" / "xemu" / "xemu.toml"

    if not xemu_toml.exists():
        raise RuntimeError(
            f"xemu config not found: {xemu_toml}. "
            "Configure flash_path, bios_path, and hdd_path via the Emulators page."
        )

    with xemu_toml.open("rb") as fh:
        config = tomllib.load(fh)

    system = config.get("system", {})
    storage = config.get("storage", {})

    checks = [
        ("flash_path", system.get("flash_path", "")),
        ("bios_path", system.get("bios_path", "")),
        ("hdd_path", storage.get("hdd_path", "")),
    ]

    missing: list[str] = []
    for key, raw in checks:
        if not raw:
            raise RuntimeError(
                f"xemu config key '{key}' is not set in {xemu_toml}. "
                "Configure it via the Emulators page."
            )
        resolved = Path(raw) if Path(raw).is_absolute() else base / raw
        if not resolved.exists():
            missing.append(f"  {key}: {resolved}")

    if missing:
        lines = "\n".join(missing)
        raise RuntimeError(
            f"xemu asset files not found:\n{lines}\n"
            "Update these paths in emulators/xemu/xemu.toml via the Emulators page."
        )


def build_args(media_path: Path) -> list[str]:
    """Build xemu command line arguments for the given disc image.

    Args:
        media_path: Path to the Xbox ISO disc image.

    Returns:
        List of command line arguments (excludes the executable path).
    """
    return ["-dvd_path", str(media_path)]


def launch(
    platform: Platform,
    media_path: Optional[Path] = None,
    enable_networking: bool = False,
) -> Tuple[SandboxProcess, WindowsJobObject]:
    """Launch xemu with the given Xbox disc image under Job Object isolation.

    Args:
        platform: Registered Platform record for the Xbox environment.
            ``config_path`` must point to the VM directory's xemu.toml so the
            VM directory can be resolved and used as the process CWD.
        media_path: Optional path to the Xbox disc image to mount.
        enable_networking: Accepted for interface compatibility; ignored for
            xemu (no meaningful network capability per SECURITY.md).

    Returns:
        Tuple of (SandboxProcess, WindowsJobObject instance).
        Caller is responsible for cleanup via job_object.teardown().

    Raises:
        FileNotFoundError: If the executable, media file, or BIOS path is missing.
        ValueError: If the media extension is unsupported or config_path is unset.
        RuntimeError: If XEMU_PATH is not configured or launch fails.
    """
    if platform.config_path is None:
        raise ValueError(
            f"Platform '{platform.name}' has no config_path set. "
            "Complete platform registration before launching."
        )

    executable_path = get_binary_path("xemu")
    if not executable_path:
        raise RuntimeError(
            "xemu binary path is not configured. "
            "Set XEMU_PATH in config/settings.yaml or via the Settings page."
        )
    if not Path(executable_path).exists():
        raise FileNotFoundError(f"xemu executable not found: {executable_path}")

    if media_path is not None:
        validate_media(media_path)

    validate_bios_path()

    vm_dir = Path(str(platform.config_path)).parent.resolve()

    args = ["-config_path", str(platform.config_path)]
    if media_path is not None:
        args += build_args(media_path)

    job_name = f"peach1up_xemu_{platform.era}_{platform.slug}"

    return launch_under_job_object(
        executable_path=executable_path,
        args=args,
        era=platform.era,
        job_name=job_name,
        slug="xemu",
        cwd=str(vm_dir),
        container_enabled=get_container_enabled("xemu"),
        sandbox_config=get_emulator_container_config("xemu", executable_path),
    )
