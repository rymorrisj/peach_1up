"""
Constants and enums for Peach 1UP.
Defines era types and media format mappings.
"""

from enum import Enum
from typing import Dict, Set


class Era(Enum):
    """
    Gaming era enumeration with string values matching eras.yaml keys.

    Values correspond exactly to era keys in config/eras.yaml configuration.
    """
    DOS = "dos"
    WIN31 = "win31"
    WIN95 = "win95"
    WIN98 = "win98"
    WINXP = "winxp"


# Mapping of gaming eras to their supported media file extensions.
# DOS and Windows 3.1 support all three formats including disk images (.img).
# Windows 95, 98, and XP support only optical formats (.iso, .cue).
ERA_MEDIA_TYPES: Dict[Era, Set[str]] = {
    Era.DOS: {'.iso', '.img', '.cue'},
    Era.WIN31: {'.iso', '.img', '.cue'},
    Era.WIN95: {'.iso', '.cue'},
    Era.WIN98: {'.iso', '.cue'},
    Era.WINXP: {'.iso', '.cue'},
}