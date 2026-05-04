from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from utils.constants import Era


_REQUIRED_FIELDS = frozenset({
    "name", "era", "media_path", "backend",
    "dosbox_conf_path", "hdd_image_path", "notes",
})


@dataclass
class Profile:
    """Per-game configuration record persisted as a YAML file.

    Attributes:
        name: Unique identifier for the game; used as the filename stem for
            both the profile YAML and generated artefacts (conf, HDD image).
        era: Gaming era that determines which backend and hardware profile to use.
        media_path: Path to the game's installation media (.iso / .img / .cue).
        backend: Backend identifier string (e.g. ``"dosbox"``, ``"86box"``).
        dosbox_conf_path: Path to the DOSBox-X ``.conf`` file for this game.
            Set by ``dosbox_config.generate_conf``; empty ``Path("")`` until then.
        hdd_image_path: Path to the FAT16 ``.img`` HDD image for this game.
            Set by ``vhd.ensure_hdd``; empty ``Path("")`` until then.
        installed: ``True`` once the installation flow has completed
            successfully.  Controls whether the launcher runs the installer
            or boots directly to the C: prompt.
        notes: Free-text field for user annotations; never read by the launcher.
    """
    name: str
    era: Era
    media_path: Path
    backend: str
    dosbox_conf_path: Path
    hdd_image_path: Path
    installed: bool
    notes: str


def save(profile: Profile, profiles_dir: Path) -> None:
    """Serialise a profile to ``<profiles_dir>/<profile.name>.yaml``.

    Converts ``Path`` and ``Era`` fields to strings for YAML serialisation.
    Creates ``profiles_dir`` if it does not exist.

    Args:
        profile: The profile to save.
        profiles_dir: Directory in which to write the ``.yaml`` file.
    """
    profiles_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "name": profile.name,
        "era": profile.era.value,
        "media_path": str(profile.media_path),
        "backend": profile.backend,
        "dosbox_conf_path": str(profile.dosbox_conf_path),
        "hdd_image_path": str(profile.hdd_image_path),
        "installed": profile.installed,
        "notes": profile.notes,
    }
    dest = profiles_dir / f"{profile.name}.yaml"
    with dest.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True)


def load(profile_path: Path) -> Profile:
    """Deserialise and validate a profile from a YAML file.

    Validates that all required fields are present and that ``era`` is a
    recognised value before constructing the ``Profile`` dataclass.

    Args:
        profile_path: Path to the ``.yaml`` profile file.

    Returns:
        A fully populated ``Profile`` instance.

    Raises:
        ValueError: If the file is not a YAML mapping, required fields are
            missing, the era value is invalid, or a field has the wrong type.
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

    try:
        return Profile(
            name=str(raw["name"]),
            era=era,
            media_path=Path(raw["media_path"]),
            backend=str(raw["backend"]),
            dosbox_conf_path=Path(raw["dosbox_conf_path"]),
            hdd_image_path=Path(raw["hdd_image_path"]),
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
    return sorted(profiles_dir.glob("*.yaml"))
