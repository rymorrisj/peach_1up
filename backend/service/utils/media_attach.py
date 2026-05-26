"""Media attachment utilities for Peach 1UP.

Builds attachment descriptor dicts consumed by backends at launch time.
Most functions are pure descriptors with no I/O. ``detect_optical_drives``
is the exception — it runs a fixed WMIC subprocess to enumerate host drives.
Backends assemble the final commands from the returned descriptors.
"""

from __future__ import annotations

import configparser
import csv
import io
import re
import subprocess
from pathlib import Path
from typing import Optional

import pycdlib
from pycdlib.pycdlibexception import PyCdlibException

from backend.core.logger import get_logger

logger = get_logger(__name__)


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
    if suffix in {".exe", ".bat", ".com"}:
        return "exe"
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


def detect_optical_drives() -> list[dict]:
    """Enumerate optical drives on the Windows host via WMIC.

    Runs ``wmic logicaldisk where drivetype=5 get deviceid,volumename
    /format:csv`` with a fixed, hardcoded command — no user input reaches
    the subprocess, so there is no injection risk. The args-list form is
    used; ``shell=True`` is never passed.

    Returns:
        List of dicts, each with ``device_id`` (e.g. ``"D:"``) and
        ``volume_name`` (e.g. ``"GAME DISC"`` or ``""`` if no disc is
        present). Returns an empty list if no optical drives are found or
        if the WMIC call fails for any reason.
    """
    try:
        result = subprocess.run(
            [
                "wmic",
                "logicaldisk",
                "where",
                "drivetype=5",
                "get",
                "deviceid,volumename",
                "/format:csv",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        logger.warning("WMIC optical drive enumeration failed: %s", exc)
        return []

    if result.returncode != 0:
        logger.warning(
            "WMIC exited with code %d: %s",
            result.returncode,
            result.stderr.strip(),
        )
        return []

    drives = []
    non_blank = [line for line in result.stdout.splitlines() if line.strip()]
    if len(non_blank) < 2:
        return []

    reader = csv.DictReader(non_blank)
    for row in reader:
        device_id = row.get("DeviceID", "").strip()
        volume_name = row.get("VolumeName", "").strip()
        if device_id:
            drives.append({"device_id": device_id, "volume_name": volume_name})

    return drives


_DEVICE_ID_RE = re.compile(r"^[A-Z]:$")


def build_physical_drive_attachment(device_id: str, platform_id: str) -> dict:
    """Return a passthrough attachment descriptor for a physical optical drive.

    The VirtualBox backend consumes this descriptor to call
    ``VBoxManage storageattach --medium host:{device_id}``. Physical drive
    attachment must be handled via a dedicated ``_attach_physical_drive``
    path in the backend — the ``attachment_type: "physical"`` key
    distinguishes it from image-file attachments handled by ``_attach_media``.

    Note:
        The VirtualBox backend (backends/virtualbox.py) does not yet implement
        ``_attach_physical_drive``. This descriptor is the contract it must
        satisfy when that path is added.

    Args:
        device_id: Windows drive letter and colon, e.g. ``"D:"``. Must match
            the pattern ``[A-Z]:`` — single uppercase letter followed by a colon.
        platform_id: UUID string identifying the target platform VM.

    Returns:
        Dict with ``device_id``, ``platform_id``, and
        ``attachment_type: "physical"``.

    Raises:
        ValueError: If ``device_id`` does not match ``[A-Z]:``.
    """
    if not _DEVICE_ID_RE.fullmatch(device_id):
        raise ValueError(
            f"Invalid device_id '{device_id}'. "
            "Expected a single uppercase drive letter followed by a colon, e.g. 'D:'."
        )
    return {
        "device_id": device_id,
        "platform_id": platform_id,
        "attachment_type": "physical",
    }
