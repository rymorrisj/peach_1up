"""Peach 1UP-specific launch-target resolution.

Small, Peach 1UP-specific module holding PS3/Xbox 360 launch-target
resolution plus Xbox optical-image identification, logic about how Peach
1UP structures a launchable target, not format detection, so it does not
live in formatscout. Successor to the orphaned pre-extraction
smart_media_detector copy that formatscout's vendored package fully
superseded; this directory was cleared and repurposed for this narrower
scope.

is_disc_format_folder, find_eboot, and find_default_xex stay internal to
this module, not exported here, matching how formatscout treated them
before this logic moved out.
"""

from .media_target import MediaTarget
from .ps3 import resolve_ps3_target
from .xbox_image import XboxDvdRipDetected, is_xiso
from .xex import resolve_xex_target

__all__ = [
    "MediaTarget",
    "resolve_ps3_target",
    "resolve_xex_target",
    "is_xiso",
    "XboxDvdRipDetected",
]
