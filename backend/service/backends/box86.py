"""86Box backend for Peach 1UP.

Handles Win95 and Win98 accuracy mode launches. Accepts a registered OSPlatform,
loads the era hardware template, validates all identifiers, optionally injects
media attachment into the config file, and launches 86Box under Job Objects.
"""

from __future__ import annotations

import configparser
import logging
import os
from pathlib import Path
from typing import Optional

import yaml

from backend.constants_generated import Era
from backend.core.settings import get_base_path
from backend.models.platform import Platform
from backend.service.utils.launcher import launch_under_job_object
from backend.service.utils.media_attach import build_86box_attachment
from backend.service.utils.settings import get_binary_path

logger = logging.getLogger(__name__)

SUPPORTED_ERAS = {Era.WIN95.value, Era.WIN98.value}


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
            "ROM_PATH must point to the directory containing 86Box ROM files."
        )


def load_template(era: str) -> dict:
    """Load and validate the hardware template for the given era.

    Checks that every string leaf value in the template is present and
    non-empty. A blank identifier would be passed to 86Box verbatim and
    cause a silent failure or wrong hardware configuration.

    Args:
        era: Era string — must be one of ``SUPPORTED_ERAS``.

    Returns:
        Validated template dict with nested section structure.

    Raises:
        FileNotFoundError: If the template file does not exist.
        ValueError: If any string field in the template is blank or None.
    """
    template_path = get_base_path() / "config" / "templates" / f"86box_{era}.yaml"
    if not template_path.exists():
        raise FileNotFoundError(
            f"86Box hardware template not found: {template_path}. "
            "Expected a template file per supported era under config/templates/."
        )

    with template_path.open("r", encoding="utf-8") as fh:
        template = yaml.safe_load(fh)

    if not isinstance(template, dict):
        raise ValueError(
            f"86Box template '{template_path.name}' is not a valid YAML mapping."
        )

    for section_name, section in template.items():
        if not isinstance(section, dict):
            continue
        for key, value in section.items():
            if value is None or (isinstance(value, str) and not value.strip()):
                raise ValueError(
                    f"86Box template '{template_path.name}' has a blank or missing "
                    f"identifier at [{section_name}] {key}. "
                    "Fill in the correct value for your installed 86Box version. "
                    "Reference: https://86box.net"
                )

    return template


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


def _inject_install_iso(config_path: str, iso_path: Path) -> None:
    """Inject confirmed CD-ROM section keys for a first-launch install ISO."""
    cp = Path(config_path)
    if not cp.exists():
        raise FileNotFoundError(f"86Box config not found: {cp}")

    parser = configparser.RawConfigParser()
    parser.optionxform = str
    parser.read(str(cp), encoding="utf-8")

    section = "Floppy and CD-ROM drives"
    if not parser.has_section(section):
        parser.add_section(section)
    iso_fwd = str(iso_path).replace("\\", "/")
    parser.set(section, "cdrom_02_image_path", iso_fwd)
    parser.set(section, "cdrom_02_parameters",  "1, atapi")
    parser.set(section, "cdrom_02_ide_channel", "0:1")

    tmp_path = cp.with_suffix(cp.suffix + ".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as fh:
            parser.write(fh)
        os.replace(str(tmp_path), str(cp))
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise


def _inject_media(attachment: dict) -> None:
    """Inject a media path into an 86Box config file atomically.

    Reads the existing config, sets the attachment section/key, then writes to
    a temp file and renames it into place via os.replace(). If the rename fails
    the temp file is cleaned up and the original config is left untouched — a
    missing or corrupt config is a hard launch failure with no recovery path.

    RawConfigParser(optionxform=str) preserves the mixed-case section names and
    keys that 86Box expects (e.g. the CD-ROM section header).

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

    parser = configparser.RawConfigParser()
    parser.optionxform = str
    parser.read(str(config_path), encoding="utf-8")

    section = attachment["section"]
    if not parser.has_section(section):
        parser.add_section(section)
    parser.set(section, attachment["key"], attachment["value"])

    tmp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as fh:
            parser.write(fh)
        os.replace(str(tmp_path), str(config_path))
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise


def launch(
    platform: Platform,
    media_path: Optional[Path] = None,
    enable_networking: bool = False,
) -> tuple:
    """Launch 86Box in accuracy mode under Job Objects.

    Validates platform state and environment, loads and validates the era
    hardware template, optionally injects game media into the config, then
    launches 86Box with resource limits applied.

    When enable_networking is False (the default), the [Network] section of
    the 86Box config is patched to set net_type = none before launch, removing
    any network device from the machine config. When True, the config is left
    at its current value.

    Args:
        platform: Registered OSPlatform. ``era``, ``working_image_path``, and
            ``config_path`` must all be set before calling.
        media_path: Optional game media to attach at launch time. When
            provided, the cd_path key is injected into the 86Box config
            before launch.
        enable_networking: When False (default), the network device is removed
            from the machine config. Set True only for software that requires
            a network connection.

    Raises:
        ValueError: If the era is unsupported, required platform fields are
            unset, or any template identifier is blank.
        FileNotFoundError: If ``working_image_path``, ``config_path``,
            ``BOX86_PATH``, or ``ROM_PATH`` do not exist on disk.
        RuntimeError: If ``BOX86_PATH`` or ``ROM_PATH`` env vars are unset.
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

    load_template(platform.era)

    box86_path = get_binary_path("box86")
    if not box86_path:
        raise RuntimeError(
            "86Box binary path is not configured. "
            "Set BOX86_PATH in your .env file or add an override in Settings."
        )
    if not Path(box86_path).exists():
        raise FileNotFoundError(f"86Box executable not found: {box86_path}")

    effective_rom_path = _resolve_rom_path(Path(box86_path))

    _inject_media({
        "config_path": platform.config_path,
        "section": "Paths",
        "key": "rompath",
        "value": str(effective_rom_path),
    })

    if media_path is not None:
        attachment = build_86box_attachment(media_path, platform.config_path)
        _inject_media(attachment)

    _inject_media({
        "config_path": platform.config_path,
        "section": "Network",
        "key": "net_type",
        "value": "ne2000" if enable_networking else "none",
    })

    args = [
        "--config", str(platform.config_path),
        "--rompath", str(effective_rom_path),
    ]

    job_paths = [str(platform.working_image_path)]
    if media_path is not None:
        job_paths.append(str(media_path))

    try:
        with img_path.open("rb") as f:
            f.seek(510)
            mbr_sig = f.read(2)
    except OSError as exc:
        raise OSError(
            f"Cannot read disk image for platform '{platform.name}': {img_path}"
        ) from exc

    if mbr_sig != b"\x55\xaa":
        if platform.base_image_path is not None:
            iso = Path(str(platform.base_image_path))
            if iso.exists():
                _inject_install_iso(str(platform.config_path), iso)
                job_paths.append(str(iso))

    job_name = f"peach1up_86box_{platform.era}_{platform.slug}"

    return launch_under_job_object(
        executable_path=box86_path,
        args=args,
        media_paths=job_paths,
        era=platform.era,
        job_name=job_name,
    )
