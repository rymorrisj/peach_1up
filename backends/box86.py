"""86Box backend for Peach 1UP.

Handles Win95 and Win98 accuracy mode launches. Accepts a registered OSPlatform,
loads the era hardware template, validates all identifiers, optionally injects
media attachment into the config file, and launches 86Box under Job Objects.
"""

from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Optional

import yaml

from utils.job_objects import launch_under_job_object
from utils.media_attach import build_86box_attachment
from utils.platform import OSPlatform


SUPPORTED_ERAS = {"win95", "win98"}

_TEMPLATE_DIR = Path("config") / "templates"


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
    template_path = _TEMPLATE_DIR / f"86box_{era}.yaml"
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

    parser = configparser.RawConfigParser(optionxform=str)
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


def launch(platform: OSPlatform, media_path: Optional[Path] = None) -> None:
    """Launch 86Box in accuracy mode under Job Objects.

    Validates platform state and environment, loads and validates the era
    hardware template, optionally injects game media into the config, then
    launches 86Box with network blocked and resource limits applied.

    Args:
        platform: Registered OSPlatform. ``era``, ``working_image_path``, and
            ``config_path`` must all be set before calling.
        media_path: Optional game media to attach at launch time. When
            provided, the cd_path key is injected into the 86Box config
            before launch.

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

    if platform.config_path is None:
        raise ValueError(
            f"Platform '{platform.name}' has no config_path set. "
            "Complete platform registration before launching."
        )

    load_template(platform.era)

    box86_path = os.getenv("BOX86_PATH", "")
    if not box86_path:
        raise RuntimeError(
            "BOX86_PATH environment variable is not set. "
            "Set it to the full path of the 86Box executable in your .env file."
        )
    if not Path(box86_path).exists():
        raise FileNotFoundError(f"86Box executable not found: {box86_path}")

    rom_path_str = os.getenv("ROM_PATH", "")
    if not rom_path_str:
        raise RuntimeError(
            "ROM_PATH environment variable is not set. "
            "Set it to the 86Box ROM directory in your .env file. "
            "Download the ROM pack from: https://github.com/86Box/roms"
        )
    validate_rom_path(Path(rom_path_str))

    if media_path is not None:
        attachment = build_86box_attachment(media_path, platform.config_path)
        _inject_media(attachment)

    args = [
        "--config", str(platform.config_path),
        "--rom-path", rom_path_str,
    ]

    job_paths = [str(platform.working_image_path)]
    if media_path is not None:
        job_paths.append(str(media_path))

    job_name = f"peach1up_86box_{platform.era}_{platform.platform_id}"

    launch_under_job_object(
        executable_path=box86_path,
        args=args,
        media_paths=job_paths,
        era=platform.era,
        job_name=job_name,
    )
