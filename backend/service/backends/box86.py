"""86Box backend for Peach 1UP.

Handles Win95 and Win98 accuracy mode launches. Accepts a registered OSPlatform,
loads the era hardware template, validates all identifiers, optionally injects
game media into the config file, and launches 86Box under Job Objects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from backend.constants_generated import Era
from backend.core.logger import get_logger
from backend.models.platform import Platform
from backend.service.utils.emulator_catalog import (
    get_emulator,
    get_container_enabled,
    get_container_config as get_emulator_container_config,
)
from backend.service.utils.ini_writer import patch_ini
from backend.service.utils.process.launcher import launch_under_job_object
from backend.service.utils.media_attach import build_86box_attachment
from backend.service.utils.settings import get_binary_path
from backend.service.utils.vm.box86_config import _prepare_config

logger = get_logger(__name__)

SUPPORTED_ERAS = {Era.WIN95.value, Era.WIN98.value, Era.WINXP.value}


def validate_rom_path(rom_path: Path) -> None:
    """Validate that the 86Box ROM path exists and is a directory.

    Args:
        rom_path: Path to the ROM directory.

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If the path exists but is not a directory.
    """
    if not rom_path.exists():
        raise FileNotFoundError(
            f"ROM path not found: {rom_path}. "
            "Download the 86Box ROM pack from: https://github.com/86Box/roms"
        )
    if not rom_path.is_dir():
        raise ValueError(
            f"ROM path is not a directory: {rom_path}. "
            "ROMS_PATH must point to the directory containing 86Box ROM files."
        )


def _resolve_rom_path(box86_binary: Path) -> Path:
    """Derive the effective ROM path from the 86Box binary location.

    Looks in the directory containing the binary for a single versioned
    ROM subdirectory (e.g. roms-5.3). No fallback — the subdirectory must
    exist and be the only subdirectory present.

    Raises:
        FileNotFoundError: If no single ROM subdirectory is found.
    """
    from backend.service.utils.emulator_catalog import get_emulator

    base = box86_binary.parent
    try:
        entries = list(base.iterdir())
    except OSError as exc:
        raise FileNotFoundError(f"Cannot read 86Box directory: {base}") from exc

    subdirs = [e for e in entries if e.is_dir()]
    rom_dirs = [e for e in subdirs if e.name.startswith("roms")]
    if len(rom_dirs) == 1:
        return rom_dirs[0]

    try:
        catalog_entry = get_emulator("86box")
        rom_pack_version = catalog_entry.get("rom_pack_version", "")
        rom_pack_url = catalog_entry.get("rom_pack_url", "https://github.com/86Box/roms")
    except Exception:
        rom_pack_version = ""
        rom_pack_url = "https://github.com/86Box/roms"

    expected_name = f"roms-{rom_pack_version}" if rom_pack_version else "roms-<version>"
    expected_path = base / expected_name
    raise FileNotFoundError(
        f"No ROM directory found alongside the 86Box binary at {base}. "
        f"Expected a versioned subdirectory at {expected_path}. "
        f"Download the 86Box ROM pack from: {rom_pack_url}"
    )



def _inject_media(attachment: dict) -> None:
    """Inject a media path into an 86Box config file atomically.

    Args:
        attachment: Dict from ``build_86box_attachment`` — must contain
            ``config_path``, ``section``, ``key``, and ``value``.

    Raises:
        FileNotFoundError: If the config file does not exist.
        OSError: If reading, writing, or the atomic rename fails.
    """
    config_path = Path(attachment["config_path"])
    if not config_path.exists():
        raise FileNotFoundError(
            f"86Box config file not found: {config_path}. "
            "Ensure the platform config_path is set correctly."
        )
    patch_ini(config_path, {attachment["section"]: {attachment["key"]: attachment["value"]}})


def launch(
    platform: Platform,
    media_path: Optional[Path] = None,
    enable_networking: bool = False,
) -> tuple:
    """Launch 86Box in accuracy mode under Job Objects.

    Validates platform state and environment, patches the 86Box config for
    this launch, optionally injects game media, then launches 86Box with
    resource limits applied.

    Args:
        platform: Registered OSPlatform. ``era``, ``working_image_path``, and
            ``config_path`` must all be set before calling.
        media_path: Optional game media to attach at launch time. When
            provided, the cd_path key is injected into the 86Box config
            before launch.
        enable_networking: When True, overrides the default net_01_link=0 set
            by _prepare_config to allow network traffic.

    Raises:
        ValueError: If the era is unsupported or required platform fields are
            unset.
        FileNotFoundError: If ``working_image_path``, ``config_path``,
            ``BOX86_PATH``, or ``ROMS_PATH`` do not exist on disk.
        RuntimeError: If ``BOX86_PATH`` or ``ROMS_PATH`` env vars are unset.
        OSError: If config injection or Job Object launch fails.
    """
    if platform.era not in SUPPORTED_ERAS:
        raise ValueError(
            f"86Box backend does not support era '{platform.era}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_ERAS))}"
        )

    if platform.working_image_path is None:
        raise ValueError(
            f"Platform '{platform.name}' has no working_image_path set. "
            "Complete platform registration (including image copy) before launching."
        )

    img_path = Path(str(platform.working_image_path))
    if not img_path.exists():
        raise ValueError(
            f"Platform '{platform.name}' working_image_path does not exist on disk: {img_path}. "
            "Re-register the platform to provision a new disk image."
        )
    if img_path.suffix.lower() not in {".img", ".vhd"}:
        raise ValueError(
            f"Platform '{platform.name}' working_image_path must be a disk image "
            f"(.img or .vhd), not '{img_path.suffix}': {img_path}. "
            "working_image_path is set to a config file — re-register the platform."
        )

    if platform.config_path is None:
        raise ValueError(
            f"Platform '{platform.name}' has no config_path set. "
            "Complete platform registration before launching."
        )

    box86_path = get_binary_path("box86")
    if not box86_path:
        raise RuntimeError(
            "86Box binary path is not configured. "
            "Set BOX86_PATH in your .env file or add an override in Settings."
        )
    if not Path(box86_path).exists():
        raise FileNotFoundError(f"86Box executable not found: {box86_path}")

    effective_rom_path = _resolve_rom_path(Path(box86_path))

    _prepare_config(platform, platform.config_path, effective_rom_path)

    if enable_networking:
        catalog_entry = get_emulator("86box")
        net_card_value = catalog_entry.get("net_card", "")
        if not net_card_value:
            raise RuntimeError(
                "Networking requested but no net_card is configured for 86Box. "
                "Add a net_card value to config/emulators/86box.toml."
            )
        _inject_media({
            "config_path": platform.config_path,
            "section": "Network",
            "key": "net_card",
            "value": net_card_value,
        })
        _inject_media({
            "config_path": platform.config_path,
            "section": "Network",
            "key": "net_01_link",
            "value": "1",
        })

    if media_path is not None:
        attachment = build_86box_attachment(media_path, platform.config_path)
        _inject_media(attachment)

    vm_dir = Path(str(platform.config_path)).parent.resolve()

    args = [
        "--config", str(platform.config_path),
        "--rompath", str(effective_rom_path),
        "--vmpath", str(vm_dir),
    ]

    job_name = f"peach1up_86box_{platform.era}_{platform.slug}"

    return launch_under_job_object(
        executable_path=box86_path,
        args=args,
        era=platform.era,
        job_name=job_name,
        slug="86box",
        cwd=str(vm_dir),
        container_enabled=get_container_enabled("86box"),
        sandbox_config=get_emulator_container_config("86box", box86_path),
    )
