"""Backend-only constants, hand-authored, not generated.

Imports Era and BackendSlug from the generated module.
"""

from backend.constants_generated import Era, EraValue

# Eras that are PC platforms (item_type == "pc") rather than console platforms.
# Shared by the SoftwareCollection.item_type validator (models/software.py) and
# the environments install-media route (api/routes/media.py).
PC_ERAS: frozenset[str] = frozenset({"dos", "win95", "win98", "winxp"})


def era_to_enum(value: EraValue) -> Era:
    """Construct the Era enum from a boundary value (DB column / API I/O).

    Use at the edge of internal dispatch code that needs named-member
    access (e.g. backend_router.resolve_backend_name); never store or pass
    the Enum itself across a DB/API boundary, use EraValue there instead.
    """
    return Era(value)
