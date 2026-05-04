"""Media attachment utilities for Peach 1UP.

Builds attachment descriptor dicts consumed by backends at launch time.
No file writes or command execution happens here — backends assemble
the final commands from these descriptors.
"""

from __future__ import annotations

import configparser
import io
import logging
from pathlib import Path
from typing import Optional

import pycdlib
from pycdlib import PyCdlibException


logger = logging.getLogger(__name__)


def detect_media_type(media_path: Path) -> str:
    """Return the media type based on file extension.

    Args:
        media_path: Path to the media file.

    Returns:
        ``"iso"`` for .iso and .cue; ``"hdd"`` for .img and .vhd;
        ``"unknown"`` for anything else.
    """
    suffix = media_path.suffix.lower()
    if suffix in {".iso", ".cue"}:
        return "iso"
    if suffix in {".img", ".vhd"}:
        return "hdd"
    return "unknown"


def find_autorun(media_path: Path) -> Optional[str]:
    """Look for autorun.inf at the root of an ISO and return the open= value.

    Only attempts parsing for .iso files via pycdlib. Returns None immediately
    for all other extensions — .img files are raw disk images (not ISO 9660),
    and .cue/.vhd autorun detection is out of scope.

    If the ISO cannot be opened, or autorun.inf is absent or unparseable,
    returns None and logs a warning. Never raises.

    Args:
        media_path: Path to the media file.

    Returns:
        The ``open=`` value from the ``[autorun]`` section if present,
        otherwise ``None``.
    """
    if media_path.suffix.lower() != ".iso":
        return None

    iso = pycdlib.PyCdlib()
    try:
        iso.open(str(media_path))
    except PyCdlibException as exc:
        logger.warning(
            "Could not open ISO for autorun detection: %s — %s", media_path, exc
        )
        return None

    try:
        file_buf = io.BytesIO()
        try:
            if iso.has_joliet():
                iso.get_file_from_iso_fp(file_buf, joliet_path="/autorun.inf")
            else:
                iso.get_file_from_iso_fp(file_buf, iso_path="/AUTORUN.INF;1")
        except PyCdlibException:
            return None

        content = file_buf.getvalue().decode("latin-1", errors="replace")
        parser = configparser.ConfigParser()
        parser.read_string(content)

        # Section name casing in autorun.inf varies — match case-insensitively.
        section = next(
            (s for s in parser.sections() if s.lower() == "autorun"),
            None,
        )
        if section is None:
            return None
        return parser.get(section, "open", fallback=None)

    except Exception as exc:
        logger.warning("Error reading autorun.inf from %s: %s", media_path, exc)
        return None
    finally:
        iso.close()


def build_dosbox_attachment(media_path: Path, drive_letter: str = "D") -> dict:
    """Return imgmount parameters for DOSBox-X media attachment.

    The DOSBox-X backend assembles the final imgmount command from this dict.

    Args:
        media_path: Path to the media file.
        drive_letter: Drive letter to mount the media at. Defaults to ``"D"``.

    Returns:
        Dict with ``media_path``, ``drive_letter``, and ``mount_type``.
    """
    return {
        "media_path": str(media_path),
        "drive_letter": drive_letter,
        "mount_type": detect_media_type(media_path),
    }


def build_virtualbox_attachment(media_path: Path, platform_id: str) -> dict:
    """Return VBoxManage storageattach parameters for VirtualBox media attachment.

    The VirtualBox backend assembles the final VBoxManage command from this dict.

    Args:
        media_path: Path to the media file.
        platform_id: UUID string identifying the target platform VM.

    Returns:
        Dict with ``media_path``, ``platform_id``, and ``controller``.
        ``controller`` is ``"IDE"`` for .iso files, ``"SATA"`` for .img/.vhd.
    """
    controller = "IDE" if media_path.suffix.lower() == ".iso" else "SATA"
    return {
        "media_path": str(media_path),
        "platform_id": platform_id,
        "controller": controller,
    }


def build_86box_attachment(media_path: Path, config_path: Path) -> dict:
    """Return config injection parameters for 86Box media attachment.

    86Box mounts optical media by reading a path from its config file —
    there is no CLI flag for this. The 86Box backend writes this value into
    the config file before launch.

    Args:
        media_path: Path to the media file.
        config_path: Path to the 86Box config file for the target platform.

    Returns:
        Dict with ``config_path``, ``section``, ``key``, and ``value``.
        The 86Box backend (P2-7) writes this key into the config before launch.

    Note:
        ``section`` and ``key`` must be verified against the installed 86Box
        version before use — identifiers vary between releases.
        Reference: https://86box.net
    """
    return {
        "config_path": str(config_path),
        "section": "CD-ROM",   # verify against your 86Box version
        "key": "cd_path",      # verify against your 86Box version
        "value": str(media_path),
    }
