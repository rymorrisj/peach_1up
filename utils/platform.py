from __future__ import annotations

import os
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from utils.image_manager import create_working_copy as _img_create_working_copy


_VALID_ERAS = frozenset({"win95", "win98", "winxp"})
_VALID_MEDIA_PATH_TYPES = frozenset({"preinstalled", "installer"})
_VALID_STATUSES = frozenset({"registered", "degraded", "unknown"})


@dataclass
class OSPlatform:
    """Registered OS platform record persisted in platforms.yaml.

    Attributes:
        platform_id: UUID string, auto-generated on creation.
        name: User-facing display name for this platform.
        era: One of ``win95``, ``win98``, ``winxp``.
        backend: Emulator backend selected at registration time.
            ``virtualbox`` for all eras by default; ``86box`` when
            ``accuracy_mode`` is True (win95/win98 only).
        accuracy_mode: When True, routes Win9x to 86Box instead of VirtualBox.
        config_path: Path to the emulator config file for this platform.
        base_image_path: Locked after registration — never modified.
        working_image_path: Active image used for all launches.
        media_path_type: ``"preinstalled"`` for images with OS already present;
            ``"installer"`` for original media requiring manual setup.
        notes: Free-text field for user annotations.
        status: One of ``"registered"``, ``"degraded"``, ``"unknown"``.
    """
    name: str
    era: str
    backend: str
    platform_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    accuracy_mode: bool = False
    config_path: Optional[Path] = None
    base_image_path: Optional[Path] = None
    working_image_path: Optional[Path] = None
    media_path_type: str = "installer"
    notes: str = ""
    status: str = "unknown"

    def create_working_copy(self, base_image_path: Path) -> Path:
        """Create a working copy of the base image for this platform.

        Delegates to ``image_manager.create_working_copy`` using this platform's
        ``era`` and ``platform_id``. Sets ``self.working_image_path`` on success.

        The caller must call ``save()`` explicitly after this method — no
        auto-save is performed here.

        Args:
            base_image_path: Path to the base image to copy.

        Returns:
            Path to the newly created working copy.

        Raises:
            FileNotFoundError: If ``base_image_path`` does not exist.
            FileExistsError: If a working copy already exists at the target path.
            OSError: If the copy or rename fails.
        """
        working_path = _img_create_working_copy(
            base_image_path, self.era, self.platform_id
        )
        self.working_image_path = working_path
        return working_path


def _validate_platform(data: dict[str, Any], source: str) -> OSPlatform:
    """Parse and validate a raw YAML dict into an OSPlatform.

    Args:
        data: Raw dictionary from YAML.
        source: Description of the source (used in error messages).

    Returns:
        A validated OSPlatform instance.

    Raises:
        ValueError: If any required field is missing or any validated field
            contains an unrecognised value.
    """
    for required in ("platform_id", "name", "era", "backend"):
        if required not in data:
            raise ValueError(
                f"Platform entry in {source} is missing required field '{required}'"
            )

    era = str(data["era"])
    if era not in _VALID_ERAS:
        raise ValueError(
            f"Platform '{data.get('name', data['platform_id'])}' in {source} has "
            f"invalid era '{era}'. Valid values: {', '.join(sorted(_VALID_ERAS))}"
        )

    media_path_type = str(data.get("media_path_type", "installer"))
    if media_path_type not in _VALID_MEDIA_PATH_TYPES:
        raise ValueError(
            f"Platform '{data.get('name', data['platform_id'])}' in {source} has "
            f"invalid media_path_type '{media_path_type}'. "
            f"Valid values: {', '.join(sorted(_VALID_MEDIA_PATH_TYPES))}"
        )

    status = str(data.get("status", "unknown"))
    if status not in _VALID_STATUSES:
        raise ValueError(
            f"Platform '{data.get('name', data['platform_id'])}' in {source} has "
            f"invalid status '{status}'. "
            f"Valid values: {', '.join(sorted(_VALID_STATUSES))}"
        )

    raw_config = data.get("config_path")
    raw_base = data.get("base_image_path")
    raw_working = data.get("working_image_path")

    return OSPlatform(
        platform_id=str(data["platform_id"]),
        name=str(data["name"]),
        era=era,
        backend=str(data["backend"]),
        accuracy_mode=bool(data.get("accuracy_mode", False)),
        config_path=Path(raw_config) if raw_config else None,
        base_image_path=Path(raw_base) if raw_base else None,
        working_image_path=Path(raw_working) if raw_working else None,
        media_path_type=media_path_type,
        notes=str(data.get("notes", "")),
        status=status,
    )


def _serialise(platform: OSPlatform) -> dict[str, Any]:
    """Convert an OSPlatform to a YAML-serialisable dict.

    Optional Path fields that are None are omitted from the output.
    """
    data: dict[str, Any] = {
        "platform_id": platform.platform_id,
        "name": platform.name,
        "era": platform.era,
        "backend": platform.backend,
        "accuracy_mode": platform.accuracy_mode,
        "media_path_type": platform.media_path_type,
        "notes": platform.notes,
        "status": platform.status,
    }
    if platform.config_path is not None:
        data["config_path"] = str(platform.config_path)
    if platform.base_image_path is not None:
        data["base_image_path"] = str(platform.base_image_path)
    if platform.working_image_path is not None:
        data["working_image_path"] = str(platform.working_image_path)
    return data


def load_all(platforms_path: Path) -> list[OSPlatform]:
    """Load all platforms from platforms.yaml.

    Args:
        platforms_path: Path to ``platforms.yaml``.

    Returns:
        List of OSPlatform instances, or an empty list if the file is missing
        or the ``platforms`` key is absent or empty.

    Raises:
        ValueError: If any platform entry fails validation.
        yaml.YAMLError: If the file exists but is not valid YAML.
    """
    if not platforms_path.exists():
        return []

    with platforms_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict) or not raw.get("platforms"):
        return []

    source = platforms_path.name
    return [_validate_platform(entry, source) for entry in raw["platforms"]]


def save(platform: OSPlatform, platforms_path: Path) -> None:
    """Upsert a platform into platforms.yaml.

    If a platform with the same ``platform_id`` already exists it is replaced
    in-place; otherwise the new platform is appended.  The file is written
    atomically: output goes to a temporary file in the same directory, then
    ``os.replace()`` renames it into place so a mid-write interruption cannot
    corrupt the target.

    Args:
        platform: The platform to save or update.
        platforms_path: Path to ``platforms.yaml``.
    """
    platforms_path.parent.mkdir(parents=True, exist_ok=True)

    existing = load_all(platforms_path)
    entries = [p for p in existing if p.platform_id != platform.platform_id]
    entries.append(platform)

    payload = {"platforms": [_serialise(p) for p in entries]}

    dir_path = str(platforms_path.parent)
    fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".yaml.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(payload, fh, allow_unicode=True, sort_keys=False)
        os.replace(tmp_path, str(platforms_path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def find_by_id(platforms_path: Path, platform_id: str) -> Optional[OSPlatform]:
    """Return the platform with the given ID, or None if not found.

    Args:
        platforms_path: Path to ``platforms.yaml``.
        platform_id: UUID string to search for.

    Returns:
        Matching OSPlatform, or None.
    """
    for platform in load_all(platforms_path):
        if platform.platform_id == platform_id:
            return platform
    return None
