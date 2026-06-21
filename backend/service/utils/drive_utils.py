"""Drive record management utilities for Peach 1UP.

Centralised drive sizing and lifecycle logic used by both the library add
flow and the on-demand launch-time creation path.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from backend.service.utils.fat import FAT16_SIZE_MIN_MB

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from backend.models.library import LibraryItem
    from backend.models.drive import Drive

# iso/cue media is mounted directly and never passed to format_fat16 (it always
# sets requires_install=True, see smart_media_detector._compute_requires_install),
# so this cap is independent of FAT16_SIZE_MAX_MB and can exceed it.
_ISO_CUE_SIZE_MAX_MB = 2048


def compute_drive_size_mb(media_path: Path, media_type: str) -> int:
    """Return the drive image size in MB for the given media.

    Args:
        media_path: Path to the media file or folder.
        media_type: Detected media type string (e.g. "iso", "cue", "floppy").

    Returns:
        Drive size in whole MB, clamped to safe bounds per media type.
        The fallback branch enforces a minimum of 4 MB so FAT16 formatting
        never receives a sub-minimum size.
    """
    source_size_mb = (
        media_path.stat().st_size / (1024 * 1024)
        if media_path.is_file()
        else sum(f.stat().st_size for f in media_path.rglob("*") if f.is_file()) / (1024 * 1024)
    )

    if media_type in ("iso", "cue"):
        return max(50, min(int(source_size_mb * 1.5), _ISO_CUE_SIZE_MAX_MB))
    if media_type == "floppy":
        return max(20, min(int(source_size_mb * 2), 40))
    return max(FAT16_SIZE_MIN_MB, min(int(source_size_mb * 1.5) + 3, 100))


def _media_type_from_path(path: Path) -> str:
    if path.is_dir():
        return "directory"
    suffix = path.suffix.lower()
    if suffix == ".iso":
        return "iso"
    if suffix == ".cue":
        return "cue"
    if suffix == ".img":
        try:
            return "floppy" if path.stat().st_size < 2 * 1024 * 1024 else "hdd"
        except OSError:
            return "hdd"
    if suffix in {".exe", ".bat", ".com"}:
        return "exe"
    return "unknown"


def create_drive_for_item(item: "LibraryItem", db: "Session") -> "Drive":
    """Create and persist a Drive record for a library item.

    Uses item.executable_path for size detection when set (the actual launch
    file), otherwise falls back to item.media_path. Detects and stores
    media_type on the item if not already set.

    Args:
        item: LibraryItem ORM instance that has already been flushed (has an id).
        db:   Active SQLAlchemy session.

    Returns:
        The newly created and refreshed Drive instance.
    """
    from backend.models.drive import Drive
    from backend.service.utils.smart_media_detector import detect as _smart_detect

    media_src = Path(item.executable_path if item.executable_path else item.media_path)

    if not item.media_type:
        _scan = _smart_detect(media_src)
        media_type = _media_type_from_path(media_src)
        item.media_type = media_type
        item.requires_install = _scan.requires_install
    else:
        media_type = item.media_type

    computed = compute_drive_size_mb(media_src, media_type)

    image_path = (
        str(Path(item.folder_path) / f"{item.slug}.img")
        if item.folder_path
        else None
    )
    drive = Drive(
        library_item_id=item.id,
        name=item.title,
        size_mb=computed,
        image_path=image_path,
    )
    db.add(drive)
    db.flush()
    item.drive_id = drive.id
    db.add(item)
    db.commit()
    db.refresh(drive)
    return drive


def delete_drive_for_item(item: "LibraryItem", db: "Session") -> None:
    """Delete the Drive record associated with a library item.

    No-op if the item has no drive_id. Clears item.drive_id and commits.

    Args:
        item: LibraryItem ORM instance.
        db:   Active SQLAlchemy session.
    """
    if item.drive_id is None:
        return

    from backend.models.drive import Drive

    drive = db.get(Drive, item.drive_id)
    if drive is None:
        item.drive_id = None
        db.add(item)
        db.commit()
        return

    db.delete(drive)
    item.drive_id = None
    db.add(item)
    db.commit()
