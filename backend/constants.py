"""Backend-only constants, hand-authored, not generated.

Every PC/console and platform-to-backend set derives from the generated
module, which is built from config/platforms.yaml.
"""

from backend.constants_generated import PC_PLATFORMS, PLATFORM_BACKENDS, BackendSlug, Platform, PlatformValue

__all__ = [
    "BOX86_PLATFORMS",
    "DOSBOX_PLATFORMS",
    "PC_PLATFORMS",
    "PLATFORM_SELECTED_BY_USER_REASON",
    "platform_to_enum",
]

# Platforms served by DOSBox-X (per-item FAT16 C: drive, not a shared working image).
DOSBOX_PLATFORMS: frozenset[str] = frozenset(
    p for p, backend in PLATFORM_BACKENDS.items() if backend == BackendSlug.DOSBOX_X.value
)

# Platforms served by 86Box (shared VHD working image per Environment).
BOX86_PLATFORMS: frozenset[str] = frozenset(
    p for p, backend in PLATFORM_BACKENDS.items() if backend == BackendSlug.BOX86.value
)

# Marker stored in GameItem.detection_reason when a user, not formatscout,
# chose the bundle's platform (at import or via PATCH). Display text only:
# whether the platform is trusted is GameItemBundle.platform_confirmed.
PLATFORM_SELECTED_BY_USER_REASON: str = "Selected by user during import"


def platform_to_enum(value: PlatformValue) -> Platform:
    """Construct the Platform enum from a boundary value (DB column / API I/O).

    Use at the edge of internal dispatch code that needs named-member
    access (e.g. backend_router.resolve_backend_name); never store or pass
    the Enum itself across a DB/API boundary, use PlatformValue there instead.
    """
    return Platform(value)
