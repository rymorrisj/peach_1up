"""Drive record management utilities for Peach 1UP.

Centralised drive sizing and lifecycle logic used by both the library add
flow and the on-demand launch-time creation path.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from backend.service.utils.era_media import media_type_from_path
from backend.service.utils.fat import FAT16_SIZE_MAX_MB, FAT16_SIZE_MIN_MB

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
        media_type = media_type_from_path(media_src)
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


def update_drive_for_item(item: "LibraryItem", new_size_mb: int, db: "Session") -> "Drive":
    """Resize the Drive image for a library item, preserving its file contents.

    FAT16 has no in-place resize primitive: format_fat16 refuses to overwrite
    an existing image, and growing/shrinking the filesystem structures
    requires rebuilding the FAT and directory tables from scratch. So this
    builds a new image at new_size_mb, copies every existing file across, and
    only swaps it in for the original once the copy is verified byte-for-byte.
    The original is kept as a .bak until the swap succeeds, so a failure at
    any point (bad size, full new image, crash mid-copy) leaves the original
    image untouched rather than silently losing data.

    Args:
        item: LibraryItem ORM instance with an existing drive_id.
        new_size_mb: Target image size in MB.
        db: Active SQLAlchemy session.

    Returns:
        The updated and refreshed Drive instance.
    """
    from backend.models.drive import Drive
    from backend.service.utils.fat import (
        format_fat16,
        list_files_in_image,
        read_file_from_image,
        write_file_to_image,
    )

    if item.drive_id is None:
        raise RuntimeError("update_drive_for_item: item has no associated drive")

    drive = db.get(Drive, item.drive_id)
    if drive is None:
        raise RuntimeError(f"update_drive_for_item: drive_id={item.drive_id} not found")

    if not (FAT16_SIZE_MIN_MB <= new_size_mb <= FAT16_SIZE_MAX_MB):
        raise RuntimeError(
            f"update_drive_for_item: new_size_mb={new_size_mb} is outside the "
            f"supported range ({FAT16_SIZE_MIN_MB}-{FAT16_SIZE_MAX_MB})"
        )

    if not drive.image_path or not Path(drive.image_path).exists():
        # Nothing to migrate — no image has been created yet, so resizing is
        # just bookkeeping; the next create/hydrate pass will use the new size.
        drive.size_mb = new_size_mb
        db.add(drive)
        db.commit()
        db.refresh(drive)
        return drive

    image_path = Path(drive.image_path)
    files = list_files_in_image(image_path)

    tmp_path = image_path.with_name(image_path.name + ".new")
    if tmp_path.exists():
        tmp_path.unlink()
    try:
        format_fat16(tmp_path, new_size_mb)
        for dest_path, data in files:
            write_file_to_image(tmp_path, dest_path, data)
            src_md5 = hashlib.md5(data).hexdigest()
            img_md5 = hashlib.md5(read_file_from_image(tmp_path, dest_path)).hexdigest()
            if src_md5 != img_md5:
                raise RuntimeError(
                    f"update_drive_for_item: MD5 mismatch migrating '{dest_path}' into resized image"
                )
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    backup_path = image_path.with_name(image_path.name + ".bak")
    if backup_path.exists():
        backup_path.unlink()
    image_path.replace(backup_path)
    try:
        tmp_path.replace(image_path)
    except Exception:
        backup_path.replace(image_path)
        raise
    backup_path.unlink()

    drive.size_mb = new_size_mb
    db.add(drive)
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
