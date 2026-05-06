"""Profile builder utilities for Peach 1UP.

Constructs Profile instances and provides the library scan and bulk import
pipeline. All functions are pure business logic with no Textual dependencies
and are callable from FastAPI route handlers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backend.service.utils.constants import Era
from backend.service.utils.profile import Profile


_SCAN_EXTENSIONS: frozenset[str] = frozenset({".iso", ".img", ".cue"})
_DOSBOX_ERAS: frozenset[Era] = frozenset({Era.DOS, Era.WIN31})


def build_profile(media_path: Path, era: Era, name: str) -> Profile:
    """Build a Profile from a media file, era, and proposed name.

    Does not save the profile — caller must call ``utils.profile.save()``
    explicitly and then ``append_history()`` to record the event.

    Args:
        media_path: Absolute path to the game's media file.
        era: Gaming era to assign to this profile.
        name: Sanitised profile name used as the file stem.

    Returns:
        A new unsaved ``Profile`` instance.
    """
    return Profile(name=name, era=era, media_path=media_path, notes="")


def sanitize_name(stem: str) -> str:
    """Produce a safe profile name from a filename stem.

    Strips characters invalid in a YAML filename stem, collapses runs of
    whitespace and hyphens to underscores, and truncates to 50 characters.

    Args:
        stem: The filename stem to sanitise (no extension).

    Returns:
        A non-empty safe profile name string.
    """
    name = re.sub(r"[^\w\s\-]", "", stem).strip()
    name = re.sub(r"[\s\-]+", "_", name)
    return name[:50] or "unnamed"


@dataclass
class ScanEntry:
    """A single media file found during a library scan.

    Attributes:
        path: Absolute path to the media file.
        era: Detected era, or ``None`` if detection was uncertain.
        name: Sanitised profile name derived from the filename stem.
        selected: Whether this entry is marked for import. Defaults to True.
            Used by the TUI to track user selection state; ignored by FastAPI.
    """
    path: Path
    era: Optional[Era]
    name: str
    selected: bool = True


def scan_directory(base: Path) -> list[ScanEntry]:
    """Walk ``base`` recursively and return a ``ScanEntry`` for each media file.

    Skips files and directories that raise ``OSError`` or ``PermissionError``
    rather than aborting the scan. Returns results sorted by path.

    Args:
        base: Directory to scan recursively.

    Returns:
        Sorted list of ``ScanEntry`` objects for every ``.iso``, ``.img``,
        and ``.cue`` file found. Empty if none are found or ``base`` is
        unreadable.
    """
    from backend.service.utils.media_detect import detect_era

    found: list[Path] = []
    try:
        for p in base.rglob("*"):
            try:
                if p.is_file() and p.suffix.lower() in _SCAN_EXTENSIONS:
                    found.append(p)
            except (OSError, PermissionError):
                continue
    except (OSError, PermissionError):
        pass
    found.sort()
    return [ScanEntry(path=p, era=detect_era(p), name=sanitize_name(p.stem)) for p in found]


def create_dos_profile(
    name: str,
    era: Era,
    media_path: Path,
    conf_dir: Path,
    profiles_dir: Path,
    images_dir: Path,
) -> Profile:
    """Create a new DOS or Win31 profile with generated conf and HDD image.

    Calls ``generate_conf`` and ``ensure_hdd`` in order, both of which
    persist the profile to ``profiles_dir``. Returns the saved ``Profile``
    instance with ``dosbox_conf_path`` and ``hdd_image_path`` populated.

    Caller is responsible for calling ``append_history()`` after this
    function returns.

    Args:
        name: Profile name used as the file stem.
        era: Gaming era — must be ``Era.DOS`` or ``Era.WIN31``.
        media_path: Absolute path to the game's media file.
        conf_dir: Directory for generated ``.conf`` files.
        profiles_dir: Directory for profile ``.yaml`` files.
        images_dir: Directory for HDD ``.img`` files.

    Returns:
        The saved ``Profile`` instance.

    Raises:
        ValueError: If ``era`` is not supported by DOSBox-X config generation.
        RuntimeError: If the HDD image cannot be written.
    """
    from backend.service.utils.dosbox_config import generate_conf
    from backend.service.utils.vhd import ensure_hdd

    profile = Profile(name=name, era=era, media_path=media_path, notes="")
    generate_conf(profile, conf_dir, profiles_dir)
    ensure_hdd(profile, images_dir, profiles_dir)
    return profile


def import_profiles(
    entries: list[ScanEntry],
    profiles_dir: Path,
    conf_dir: Path,
    images_dir: Path,
) -> tuple[int, int]:
    """Bulk import a list of ``ScanEntry`` objects as game profiles.

    For DOS and Win31 entries, generates conf and HDD image in addition to
    saving the profile. For all other eras, saves the profile only.
    Records a ``'scanner'`` history entry for every successfully imported
    profile.

    Args:
        entries: ``ScanEntry`` objects to import (typically the selected
            subset from a ``scan_directory()`` result).
        profiles_dir: Directory for profile ``.yaml`` files.
        conf_dir: Directory for generated ``.conf`` files.
        images_dir: Directory for HDD ``.img`` files.

    Returns:
        ``(saved, failed)`` counts.
    """
    from backend.service.utils.dosbox_config import generate_conf
    from backend.service.utils.profile import save as save_profile, append_history
    from backend.service.utils.vhd import ensure_hdd

    saved = 0
    failed = 0
    for entry in entries:
        try:
            era = entry.era if entry.era is not None else Era.DOS
            media_path = entry.path.resolve()
            profile = build_profile(media_path, era, entry.name)
            if era in _DOSBOX_ERAS:
                generate_conf(profile, conf_dir, profiles_dir)
                ensure_hdd(profile, images_dir, profiles_dir)
            else:
                save_profile(profile, profiles_dir)
            append_history(
                profile,
                profiles_dir,
                "scanner",
                [
                    {"field": "name",       "old": None, "new": entry.name},
                    {"field": "era",        "old": None, "new": era.value},
                    {"field": "media_path", "old": None, "new": str(media_path)},
                ],
            )
            saved += 1
        except Exception:
            failed += 1
    return saved, failed
