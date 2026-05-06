from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from utils.constants import Era


_REQUIRED_FIELDS = frozenset({"name", "era", "media_path", "notes"})

_VALID_MEDIA_PATH_TYPES = frozenset({"preinstalled", "installer"})


@dataclass
class Profile:
    """Per-game configuration record persisted as a YAML file.

    Attributes:
        name: Unique identifier for the game; used as the filename stem for
            both the profile YAML and generated artefacts (conf, HDD image).
        era: Gaming era that determines which backend and hardware profile to use.
        media_path: Path to the game's installation media (.iso / .img / .cue).
        media_path_type: ``"preinstalled"`` for HDD images with OS and software
            already present; ``"installer"`` for original install media where the
            user completes setup manually inside the emulator.
        platform_id: Name of the registered OSPlatform this profile targets.
            ``None`` for DOS profiles, which own their own per-game HDD image.
        dosbox_conf_path: Path to the DOSBox-X ``.conf`` file for this game.
            ``None`` until set by ``dosbox_config.generate_conf``.  Only
            relevant for DOS and Win31 profiles.
        hdd_image_path: Path to the FAT16 ``.img`` HDD image for this game.
            ``None`` until set by ``vhd.ensure_hdd``.  Only relevant for DOS
            and Win31 profiles — Win9x/XP use the OSPlatform working image.
        installed: ``True`` once the installation flow has completed
            successfully.  Controls whether the launcher runs the installer
            or boots directly to the C: prompt.
        notes: Free-text field for user annotations; never read by the launcher.
    """
    name: str
    era: Era
    media_path: Path
    notes: str
    media_path_type: str = "installer"
    platform_id: Optional[str] = None
    dosbox_conf_path: Optional[Path] = None
    hdd_image_path: Optional[Path] = None
    installed: bool = False


def save(profile: Profile, profiles_dir: Path) -> None:
    """Serialise a profile to ``<profiles_dir>/<profile.name>.yaml``.

    Converts ``Path`` and ``Era`` fields to strings for YAML serialisation.
    Creates ``profiles_dir`` if it does not exist.  Optional fields that are
    ``None`` are omitted from the output file.

    Args:
        profile: The profile to save.
        profiles_dir: Directory in which to write the ``.yaml`` file.
    """
    profiles_dir.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "name": profile.name,
        "era": profile.era.value,
        "media_path": str(profile.media_path),
        "media_path_type": profile.media_path_type,
        "installed": profile.installed,
        "notes": profile.notes,
    }
    if profile.platform_id is not None:
        data["platform_id"] = profile.platform_id
    if profile.dosbox_conf_path is not None:
        data["dosbox_conf_path"] = str(profile.dosbox_conf_path)
    if profile.hdd_image_path is not None:
        data["hdd_image_path"] = str(profile.hdd_image_path)

    dest = profiles_dir / f"{profile.name}.yaml"
    with dest.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True)


def load(profile_path: Path) -> Profile:
    """Deserialise and validate a profile from a YAML file.

    Validates that all required fields are present and that ``era`` and
    ``media_path_type`` are recognised values before constructing the
    ``Profile`` dataclass.

    Args:
        profile_path: Path to the ``.yaml`` profile file.

    Returns:
        A fully populated ``Profile`` instance.

    Raises:
        ValueError: If the file is not a YAML mapping, required fields are
            missing, the era or media_path_type value is invalid, or a field
            has the wrong type.
    """
    with profile_path.open("r", encoding="utf-8") as fh:
        raw: Any = yaml.safe_load(fh)  # unvalidated YAML output; treated as trusted after checks below

    if not isinstance(raw, dict):
        raise ValueError(
            f"Profile '{profile_path.name}' is not a valid YAML mapping"
        )

    missing = _REQUIRED_FIELDS - raw.keys()
    if missing:
        raise ValueError(
            f"Profile '{profile_path.name}' is missing required fields: "
            + ", ".join(sorted(missing))
        )

    try:
        era = Era(raw["era"])
    except ValueError:
        valid = ", ".join(e.value for e in Era)
        raise ValueError(
            f"Profile '{profile_path.name}' has invalid era '{raw['era']}'. "
            f"Valid values: {valid}"
        )

    media_path_type = str(raw.get("media_path_type", "installer"))
    if media_path_type not in _VALID_MEDIA_PATH_TYPES:
        raise ValueError(
            f"Profile '{profile_path.name}' has invalid media_path_type "
            f"'{media_path_type}'. Valid values: "
            + ", ".join(sorted(_VALID_MEDIA_PATH_TYPES))
        )

    raw_conf = raw.get("dosbox_conf_path")
    raw_hdd = raw.get("hdd_image_path")

    try:
        return Profile(
            name=str(raw["name"]),
            era=era,
            media_path=Path(raw["media_path"]),
            media_path_type=media_path_type,
            platform_id=raw.get("platform_id") or None,
            dosbox_conf_path=Path(raw_conf) if raw_conf else None,
            hdd_image_path=Path(raw_hdd) if raw_hdd else None,
            installed=bool(raw.get("installed", False)),
            notes=str(raw["notes"]),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Profile '{profile_path.name}' has a malformed field: {exc}"
        ) from exc


def list_profiles(profiles_dir: Path) -> list[Path]:
    """Return sorted paths of all ``.yaml`` profile files in ``profiles_dir``.

    Args:
        profiles_dir: Directory to scan for profile files.

    Returns:
        Sorted list of ``.yaml`` paths, or an empty list if the directory
        does not exist.
    """
    if not profiles_dir.exists():
        return []
    return sorted(p for p in profiles_dir.glob("*.yaml") if not p.name.endswith(".history.yaml"))


def append_history(
    profile: Profile,
    profiles_dir: Path,
    source: str,
    changes: list[dict],
) -> None:
    """Append a history entry to the profile's sidecar history file.

    The sidecar is written at ``<profiles_dir>/<profile.name>.history.yaml``
    and is append-only — entries are never rewritten or truncated.

    This function never raises. Any I/O or serialisation error is silently
    swallowed so that history writes never block a profile save.

    Args:
        profile: The profile being saved.
        profiles_dir: Directory containing profile YAML files.
        source: Short label for the caller — ``'user'``, ``'scanner'``, or
            ``'wizard'``.
        changes: List of change dicts, each with keys ``'field'``, ``'old'``,
            and ``'new'``.
    """
    try:
        hist_path = profiles_dir / f"{profile.name}.history.yaml"
        entry = {
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "source": source,
            "changes": changes,
        }
        existing: list = []
        if hist_path.exists():
            with hist_path.open("r", encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh) or []
            if isinstance(loaded, list):
                existing = loaded
        existing.append(entry)
        profiles_dir.mkdir(parents=True, exist_ok=True)
        with hist_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(existing, fh, allow_unicode=True)
    except Exception:
        pass


def load_history(profile: Profile, profiles_dir: Path) -> list[dict]:
    """Load the history for a profile, newest entry first.

    Args:
        profile: The profile whose history to load.
        profiles_dir: Directory containing profile YAML files.

    Returns:
        List of history entry dicts in reverse chronological order, or an
        empty list if no history exists or any error occurs.
    """
    try:
        hist_path = profiles_dir / f"{profile.name}.history.yaml"
        if not hist_path.exists():
            return []
        with hist_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or []
        if isinstance(data, list):
            return list(reversed(data))
        return []
    except Exception:
        return []
