"""Backend-only constants — hand-authored, not generated.

Imports Era and BackendSlug from the generated module and defines
ERA_MEDIA_TYPES, which maps each era to its supported file extensions.
"""

from typing import Dict, Set

from backend.constants_generated import Era

ERA_MEDIA_TYPES: Dict[Era, Set[str]] = {
    Era.DOS:   {'.iso', '.img', '.cue', '.exe', '.bat'},
    Era.WIN31: {'.iso', '.img', '.cue', '.exe', '.bat'},
    Era.WIN95: {'.iso', '.cue'},
    Era.WIN98: {'.iso', '.cue'},
    Era.WINXP: {'.iso', '.cue'},
    Era.PS1:   {'.iso', '.bin', '.cue', '.chd'},
    Era.PS2:   {'.iso', '.bin', '.cue', '.chd'},
    Era.XBOX:  {'.iso', '.xiso'},
    Era.NES:   {'.nes', '.chd'},
    Era.N64:   {'.z64', '.n64', '.v64'},
}
