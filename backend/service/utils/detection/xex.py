"""Xbox 360 XEX launch-target resolution.

XEX folder-shape resolution, restored here as a shared module after living as
a private, underscore-prefixed copy inside xenia.py, itself transplanted
inline from the formatscout vendor package (services/vendor/formatscout/
smart_media_detector, as it existed at commit f3fde90 before its
working-tree removal). Now genuinely shared: xenia.py's launch() and
backend.service.games.items' ingest-time detection both call
resolve_xex_target() from here instead of each carrying (or importing from
formatscout) their own copy.
"""

from __future__ import annotations

from pathlib import Path

from backend.core.logger import get_logger

from .media_target import MediaTarget

logger = get_logger(__name__)


def resolve_xex_target(folder: Path) -> MediaTarget | None:
    """Resolve *folder* to an Xbox 360 MediaTarget if it contains a bootable XEX.

    Called from xenia.py's launch() and from items.py at ingest time,
    instead of either independently calling find_default_xex. Unlike PS3,
    detect_path and launch_path are the same file here, Xenia is handed the
    resolved .xex directly, not the containing folder.

    Returns:
        None if *folder* is not a directory or contains no .xex file.
    """
    if not folder.is_dir():
        return None
    xex = find_default_xex(folder)
    if xex is None:
        return None
    return MediaTarget(
        kind="xex_folder", detect_path=xex, launch_path=xex,
        era="xbox360", requires_install=False, license_files=(),
    )


def find_default_xex(folder: Path) -> Path | None:
    """Return the launchable .xex path for an extracted Xbox 360 XEX folder.

    Prefers an exact "default.xex" match (case-insensitive) at the folder's
    top level, the conventional entry point Xenia itself looks for. If no
    default.xex exists but other .xex files are present, falls back to the
    alphabetically first one by filename, chosen deterministically rather
    than by filesystem iteration order, and logs a warning since this is a
    tie-break, not a confirmed match, and the wrong title could otherwise
    launch silently.
    """
    try:
        xex_files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".xex"]
    except OSError:
        return None
    if not xex_files:
        return None
    for f in xex_files:
        if f.name.lower() == "default.xex":
            return f
    xex_files.sort(key=lambda f: f.name.lower())
    chosen = xex_files[0]
    logger.warning(
        "xex resolver: no default.xex found in '%s', %d other .xex file(s) present, "
        "deterministically choosing '%s' (alphabetically first) as a tie-break. "
        "Rename the intended file to default.xex to avoid relying on this.",
        folder, len(xex_files), chosen.name,
    )
    return chosen
