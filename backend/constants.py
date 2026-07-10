"""Backend-only constants — hand-authored, not generated.

Imports Era and BackendSlug from the generated module and defines
ERA_FILE_TYPES, which maps each era to its supported file extensions.
"""

from typing import Dict, Set

from backend.constants_generated import Era, EraValue

# Eras that are PC platforms (item_type == "pc") rather than console platforms.
# Shared by the SoftwareCollection.item_type validator (models/software.py) and
# the environments install-media route (api/routes/media.py).
PC_ERAS: frozenset[str] = frozenset({"dos", "win95", "win98", "winxp"})


def era_to_enum(value: EraValue) -> Era:
    """Construct the Era enum from a boundary value (DB column / API I/O).

    Use at the edge of internal dispatch code that needs named-member
    access (e.g. backend_router.resolve_backend_name); never store or pass
    the Enum itself across a DB/API boundary — use EraValue there instead.
    """
    return Era(value)


ERA_FILE_TYPES: Dict[Era, Set[str]] = {
    Era.DOS:       {'.iso', '.img', '.cue', '.exe', '.bat'},
    Era.WIN95:     {'.iso', '.cue'},
    Era.WIN98:     {'.iso', '.cue'},
    Era.WINXP:     {'.iso', '.cue'},
    Era.PS1:       {'.iso', '.bin', '.cue', '.chd', '.zip'},
    Era.PS2:       {'.iso', '.bin', '.cue', '.chd', '.zip'},
    Era.XBOX:      {'.iso', '.xiso', '.zip'},
    Era.NES:       {'.nes', '.chd', '.zip'},
    Era.SNES:      {'.sfc', '.smc', '.fig', '.swc', '.zip'},
    Era.N64:       {'.z64', '.n64', '.v64', '.zip'},
    Era.DREAMCAST: {'.gdi', '.cdi', '.chd', '.zip'},
}
