"""Drive record management utilities for Peach 1UP.

Centralised drive sizing and lifecycle logic used by both the library add
flow and the on-demand launch-time creation path.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from backend.service.utils.era_media import media_type_from_path
from backend.service.utils.fat import FAT16_SIZE_MIN_MB

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from backend.models.software import SoftwareCollection, SoftwareItem
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


def create_drive_for_collection(
    collection: "SoftwareCollection", launch_leaf: "SoftwareItem", db: "Session"
) -> "Drive":
    """Create and persist a Drive record for a library collection.

    Sizing uses the launch leaf's executable_path when set (the actual launch
    file), otherwise its media_path. media_type/requires_install are cached on
    the collection when not already set. The image lives at
    ``{launch_leaf.folder_path}/{collection.slug}.img`` — the launch leaf is the
    SoftwareItem pointed to by collection.launch_disk_id.

    Args:
        collection:  SoftwareCollection ORM instance (already flushed, has an id).
        launch_leaf: The collection's launch-disc SoftwareItem.
        db:          Active SQLAlchemy session.

    Returns:
        The newly created and refreshed Drive instance.
    """
    from backend.models.drive import Drive
    from backend.service.utils.smart_media_detector import detect as _smart_detect

    media_src = Path(launch_leaf.executable_path if launch_leaf.executable_path else launch_leaf.media_path)

    if not launch_leaf.media_type:
        _scan = _smart_detect(media_src)
        media_type = media_type_from_path(media_src)
        launch_leaf.media_type = media_type
        collection.requires_install = _scan.requires_install
        db.add(launch_leaf)
    else:
        media_type = launch_leaf.media_type

    computed = compute_drive_size_mb(media_src, media_type)

    image_path = (
        str(Path(launch_leaf.folder_path) / f"{collection.slug}.img")
        if launch_leaf.folder_path and collection.slug
        else None
    )
    drive = Drive(
        software_collection_id=collection.id,
        name=collection.title,
        size_mb=computed,
        image_path=image_path,
    )
    db.add(drive)
    db.flush()
    collection.drive_id = drive.id
    db.add(collection)
    db.commit()
    db.refresh(drive)
    return drive


def delete_drive_for_collection(collection: "SoftwareCollection", db: "Session") -> None:
    """Delete the Drive record and its on-disk image for a library collection.

    No-op if the collection has no drive_id. Unlinks the FAT16 image file (if
    any) before deleting the row, then clears collection.drive_id and commits.
    The unlink runs here explicitly, ahead of any FK cascade from deleting the
    owning collection, so image cleanup never depends on cascade ordering. A
    missing image file is logged and ignored (idempotent); only a real unlink
    error (e.g. permissions) is logged as a warning — deletion of the DB record
    still proceeds.

    Args:
        collection: SoftwareCollection ORM instance.
        db:         Active SQLAlchemy session.
    """
    if collection.drive_id is None:
        return

    from backend.core.logger import get_logger
    from backend.models.drive import Drive

    logger = get_logger(__name__)
    drive = db.get(Drive, collection.drive_id)
    if drive is None:
        collection.drive_id = None
        db.add(collection)
        db.commit()
        return

    if drive.image_path:
        img_path = Path(drive.image_path)
        try:
            if img_path.exists():
                img_path.unlink()
                logger.info("Deleted drive image: %s", img_path)
        except OSError as exc:
            logger.warning("Could not delete drive image %s: %s", img_path, exc)

    db.delete(drive)
    collection.drive_id = None
    db.add(collection)
    db.commit()
