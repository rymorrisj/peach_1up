from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from backend.constants_generated import EmulatorCatalogSlug


@dataclass
class LaunchSpec:
    # Dispatch key — matches BackendSlug.value (e.g. "dosbox", "flycast")
    slug: str
    era: str

    # Emulator catalog slug for history records (e.g. "dosbox-x", not "dosbox")
    emulator_slug: EmulatorCatalogSlug | None = None

    # Media and executable
    media_path: Path | None = None
    executable_path: str | None = None

    # Network
    enable_networking: bool = False
    enable_dgvoodoo2: bool = False

    # Item-level launch commands (appended after profile commands in dosbox)
    launch_commands: list[str] = field(default_factory=list)

    # True only when the item never had launch_commands configured (None in the
    # DB). Lets dosbox auto-run a runnable media file by default, while an
    # explicitly-cleared ([]) command list drops the user at the DOS prompt.
    auto_run_media: bool = False

    # Hydrated loose-file items (dosbox): their files were copied onto the
    # writable C: drive, so the game runs from C: and the read-only D: source
    # mount is skipped. c_run_command is the executable relative to C:'s root
    # (e.g. "RALLY.EXE" or "BIN\\GAME.EXE"), or None when none was resolved.
    run_from_c: bool = False
    c_run_command: str | None = None

    # Profile plain fields (consumed by dosbox; ignored by other backends)
    profile_id: int | None = None
    profile_launch_commands: list[str] = field(default_factory=list)
    use_drive: bool = True
    container_enabled: bool | None = None

    # Owning user of the launching profile — scopes the AppContainer moniker
    # per-user. None means the profile has no associated user (e.g. bundled).
    user_id: int | None = None

    # Drive plain fields (consumed by dosbox only)
    drive_id: int | None = None
    drive_image_path: Path | None = None
    drive_size_mb: int | None = None

    # Platform plain fields. working_image_path is the shared, persistent
    # working image for 86Box-style eras (box86/xemu) and, separately, the
    # environment-launch persistent C: drive for DOS (dosbox reads it
    # only when media_path is None — see dosbox.write_environment_conf()).
    # For a library-item DOS launch, dosbox instead mounts the
    # per-item drive_image_path as C:, and working_image_path is unset/inert.
    vm_dir: Path | None = None          # resolved from platform.config_path parent
    config_path: Path | None = None     # resolved from platform.config_path
    working_image_path: Path | None = None
    base_image_path: Path | None = None
    hardware_profile: str = "standard"
    platform_name: str | None = None
    platform_slug: str | None = None

    # Pre-resolved by provisioning when a launch triggers it (box86 only) —
    # lets box86.launch skip re-resolving the ROM path it already computed.
    resolved_rom_path: Path | None = None

    # All disc paths in disc_number order (a collection-of-one yields one path).
    # Used by dosbox backend to generate multi-image IMGMOUNT for disc swap.
    disc_paths: list[Path] = field(default_factory=list)

    # History metadata — coordinator only, not used by backends
    collection_id: int | None = None
    platform_id: int | None = None
    launch_review_flagged: bool = False

    # Which table collection_id points into — "game" (game_item_bundles)
    # or "app" (app_item_bundles). Lets the coordinator write the LaunchHistory
    # FK into the right column without a second, parallel launch() path.
    source_type: str = "game"
