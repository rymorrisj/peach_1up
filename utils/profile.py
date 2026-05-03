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
    name: str
    era: Era
    media_path: Path
    backend: str
    dosbox_conf_path: Path
    hdd_image_path: Path
    installed: bool
    notes: str


def save(profile: Profile, profiles_dir: Path) -> None:
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
    with profile_path.open("r", encoding="utf-8") as fh:
        raw: Any = yaml.safe_load(fh)

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
    if not profiles_dir.exists():
        return []
    return sorted(profiles_dir.glob("*.yaml"))
