"""Shared MediaTarget dataclass for Peach 1UP-specific launch-target resolution.

Restored as a single shared type after living as two near-identical private
copies in rpcs3.py and xenia.py (one PS3-shaped, one Xbox 360-shaped). Genuinely
shared across three callers now (rpcs3.py, xenia.py, backend.service.games.items),
not duplicated per-file. This logic is about how Peach 1UP structures a
launchable target, not format detection, so it lives here rather than in
formatscout.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(slots=True, frozen=True)
class MediaTarget:
    """A resolved, launchable PS3 or Xbox 360 media shape.

    Produced by resolve_ps3_target() or resolve_xex_target() below, or
    constructed directly for a PS3 .pkg file, and consumed by the rpcs3/xenia
    backends' launch() functions.

    kind:
        "file", a single launchable file (a PS3 .pkg), no folder-shape
            resolution needed.
        "disc_folder", a PS3 folder identified by a disc-format structural
            marker (e.g. PS3_DISC.SFB); RPCS3's own "Boot Game" walks the
            folder itself, not a resolved boot file.
        "installed_dir", a PS3 folder with no disc marker but a resolvable
            boot file at a known relative layout (e.g.
            dev_hdd0/game/<ID>/USRDIR/EBOOT.BIN).
        "xex_folder", an extracted Xbox 360 folder containing a bootable
            .xex file.

    detect_path: what classify()/hash_file() should hash for verification.
        For "disc_folder"/"installed_dir" this is the resolved boot file
        (e.g. EBOOT.BIN), not the folder, a folder can never be hashed. For
        "xex_folder" this is the same file as launch_path.
    launch_path: what gets handed to the emulator. For "disc_folder"/
        "installed_dir" this is the folder itself (RPCS3 does its own
        internal walk); for "file" and "xex_folder" it is the same file as
        detect_path.
    license_files: sibling license files discovered alongside a "file"-kind
        target (today: .rap files next to a PS3 .pkg). Empty for every other
        kind.
    """

    kind: Literal["file", "disc_folder", "installed_dir", "xex_folder"]
    detect_path: Path
    launch_path: Path
    era: str | None
    requires_install: bool
    license_files: tuple[Path, ...] = ()
