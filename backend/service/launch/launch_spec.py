from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LaunchSpec:
    # Dispatch key — matches BackendSlug.value (e.g. "dosbox", "flycast")
    slug: str
    era: str

    # Emulator catalog slug for history records (e.g. "dosbox-x", not "dosbox")
    emulator_slug: str = ""

    # Media and executable
    media_path: Path | None = None
    executable_path: str | None = None

    # Network
    enable_networking: bool = False

    # Item-level launch commands (appended after profile commands in dosbox)
    launch_commands: list[str] = field(default_factory=list)

    # Profile plain fields (consumed by dosbox; ignored by other backends)
    profile_id: int | None = None
    profile_launch_commands: list[str] = field(default_factory=list)
    use_drive: bool = True
    container_enabled: bool | None = None

    # Drive plain fields (consumed by dosbox only)
    drive_id: int | None = None
    drive_image_path: Path | None = None
    drive_size_mb: int | None = None

    # Platform plain fields (consumed by box86 and xemu)
    vm_dir: Path | None = None          # resolved from platform.config_path parent
    config_path: Path | None = None     # resolved from platform.config_path
    working_image_path: Path | None = None
    base_image_path: Path | None = None
    hardware_profile: str = "standard"
    platform_name: str | None = None
    platform_slug: str | None = None

    # History metadata — coordinator only, not used by backends
    item_id: int | None = None
    platform_id: int | None = None
    launch_review_flagged: bool = False
