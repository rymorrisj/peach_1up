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
    PS1 = "ps1"
    PS2 = "ps2"
    XBOX = "xbox"
    NES = "nes"
    N64 = "n64"


# Mapping of gaming eras to their supported media file extensions.
ERA_MEDIA_TYPES: Dict[Era, Set[str]] = {
    Era.DOS: {'.iso', '.img', '.cue'},
    Era.WIN31: {'.iso', '.img', '.cue'},
    Era.WIN95: {'.iso', '.cue'},
    Era.WIN98: {'.iso', '.cue'},
    Era.WINXP: {'.iso', '.cue'},
    Era.PS1: {'.iso', '.bin', '.cue', '.chd'},
    Era.PS2: {'.iso', '.bin', '.cue', '.chd'},
    Era.XBOX: {'.iso', '.xiso'},
    Era.NES: {'.nes', '.chd'},
    Era.N64: {'.z64', '.n64', '.v64'},
}