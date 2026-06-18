# Manual copy of Era enum values and ERA_MEDIA_TYPES from backend/constants_generated.py and
# backend/constants.py — must be kept in sync if the source enums or extension sets change.

from enum import Enum
from typing import Dict, Set


class Era(Enum):
    DOS = "dos"
    WIN31 = "win31"
    WIN95 = "win95"
    WIN98 = "win98"
    WINXP = "winxp"
    PS1 = "ps1"
    PS2 = "ps2"
    XBOX = "xbox"
    NES = "nes"
    SNES = "snes"
    N64 = "n64"
    DREAMCAST = "dreamcast"


ERA_MEDIA_TYPES: Dict[Era, Set[str]] = {
    Era.DOS:       {'.iso', '.img', '.cue', '.exe', '.bat'},
    Era.WIN31:     {'.iso', '.img', '.cue', '.exe', '.bat'},
    Era.WIN95:     {'.iso', '.cue'},
    Era.WIN98:     {'.iso', '.cue'},
    Era.WINXP:     {'.iso', '.cue'},
    Era.PS1:       {'.iso', '.bin', '.cue', '.chd', '.zip'},
    Era.PS2:       {'.iso', '.bin', '.cue', '.chd', '.zip'},
    Era.XBOX:      {'.iso', '.xiso', '.zip'},
    Era.NES:       {'.nes', '.chd', '.zip'},
    Era.N64:       {'.z64', '.n64', '.v64', '.zip'},
    Era.DREAMCAST: {'.gdi', '.cdi', '.chd', '.zip'},
}
