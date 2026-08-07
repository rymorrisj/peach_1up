"""PS3 launch-target resolution.

PS3 folder-shape resolution, restored here as a shared module after living as
a private, underscore-prefixed copy inside rpcs3.py, itself transplanted
inline from the formatscout vendor package (services/vendor/formatscout/
smart_media_detector, as it existed at commit f3fde90 before its
working-tree removal). Now genuinely shared: rpcs3.py's launch() and
backend.service.games.items' ingest-time detection both call
resolve_ps3_target() from here instead of each carrying (or importing from
formatscout) their own copy.
"""

from __future__ import annotations

from pathlib import Path

from .media_target import MediaTarget

# PS3_DISC.SFB at a folder's root (alongside PS3_GAME/, optionally PS3_UPDATE/)
# marks the folder as a disc-format dump. RPCS3's own "Boot Game" targets the
# folder itself in this case and does its own internal walk, so the folder is
# the launch unit, not a resolved EBOOT.BIN, a distinct shape from the
# dev_hdd0/game/<TITLE_ID>/ and loose extracted folders find_eboot resolves.
_PS3_DISC_MARKER_FILENAME = "PS3_DISC.SFB"


def is_disc_format_folder(folder: Path) -> bool:
    """Return True if *folder* is a disc-format dump (has PS3_DISC.SFB at its root)."""
    return (folder / _PS3_DISC_MARKER_FILENAME).is_file()


def find_eboot(folder: Path) -> Path | None:
    """Return the EBOOT.BIN path for *folder*, checking both known layouts.

    dev_hdd0/game/<TITLE_ID>/ folders (installed pkgs) hold USRDIR directly;
    extracted disc folders hold it one level down, under PS3_GAME/.
    """
    for candidate in (folder / "USRDIR" / "EBOOT.BIN", folder / "PS3_GAME" / "USRDIR" / "EBOOT.BIN"):
        if candidate.is_file():
            return candidate
    return None


def resolve_ps3_target(folder: Path) -> MediaTarget | None:
    """Resolve *folder* to a PS3 MediaTarget if it matches a known PS3 folder shape.

    The single resolver for both PS3 folder shapes, called from rpcs3.py's
    launch() and from items.py at ingest time, instead of either
    independently reimplementing the is_disc_format_folder/find_eboot check.

    A real, bootable EBOOT.BIN must exist for either shape to resolve, a
    folder with PS3_DISC.SFB but no findable EBOOT.BIN is not a valid target
    and returns None here, the same as a folder with neither signal. This is
    deliberate: the disc-format branch used to trust the SFB marker alone and
    skip this check, letting an unbootable folder reach RPCS3 before failing
    there instead of here.

    detect_path is always the resolved EBOOT.BIN (what classify()/hash_file()
    should hash); launch_path is always the folder itself (what RPCS3 is
    handed, it does its own internal walk from the folder root for both
    shapes). era is resolved structurally here, not by suffix-dispatching
    the returned EBOOT.BIN through detect()'s generic .bin handling.

    Returns:
        None if *folder* is not a directory or has no resolvable PS3 shape.
    """
    if not folder.is_dir():
        return None
    eboot = find_eboot(folder)
    if eboot is None:
        return None
    kind = "disc_folder" if is_disc_format_folder(folder) else "installed_dir"
    return MediaTarget(
        kind=kind, detect_path=eboot, launch_path=folder,
        era="ps3", requires_install=False, license_files=(),
    )
