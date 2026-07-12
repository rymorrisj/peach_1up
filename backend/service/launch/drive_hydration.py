from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from backend.service.utils.fat import (
    FAT16_SIZE_MAX_MB,
    FAT16_SIZE_MIN_MB,
    format_fat16,
    read_file_from_image,
    write_file_to_image,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from backend.models.drive import Drive
    from backend.service.launch.launchable_resolver import LaunchableEntity


def _copy_loose_files_to_drive(src_dir: Path, img_path: Path, size_mb: int) -> None:
    # SECURITY NOTE: MD5 is used here for post-write integrity verification only,
    # not for any authentication or security-sensitive purpose.
    if not src_dir.is_dir():
        raise RuntimeError(f"src_dir is not a directory: {src_dir}")
    files = [f for f in src_dir.rglob("*") if f.is_file() and f.resolve() != img_path.resolve()]
    if not files:
        raise RuntimeError(f"No files found under {src_dir}")
    for f in files:
        data = f.read_bytes()
        src_md5 = hashlib.md5(data).hexdigest()
        rel = f.relative_to(src_dir)
        dest = str(rel).replace("\\", "/")
        write_file_to_image(img_path, dest, data)
        read_back = read_file_from_image(img_path, dest)
        img_md5 = hashlib.md5(read_back).hexdigest()
        if src_md5 != img_md5:
            raise RuntimeError(f"MD5 mismatch for {f}: src={src_md5} img={img_md5}")


def hydrate_drive_for_entity(entity: "LaunchableEntity", db: "Session") -> "Drive | None":
    """Resolve or create drive; copy loose files on first launch.

    Uses the pre-resolved drive on the entity (collection-owned). Auto-creates a
    drive for DOS collections when none exists, keyed to the launch leaf's
    folder_path and the collection slug. Disc-image collections never trigger the
    loose-file copy path (media_path is a file, not a directory).

    The installed=True write-back goes through entity._db_collection.
    """
    from backend.models.drive import Drive
    from backend.models.game import GameItem
    from backend.service.utils.drive_utils import compute_drive_size_mb, create_drive_for_collection
    from backend.service.utils.era_defaults import DOS_WIN_ERAS as _DRIVE_ERAS

    drive = entity.drive

    # Auto-create a drive for DOS collections/apps that don't have one yet.
    # entity.era already resolves correctly for both source types (era column
    # for Software, the linked Environment's era for Apps -- see
    # launchable_resolver.resolve_launchable_app), so the DOS-era gate below
    # is source-type-agnostic. Only the launch-leaf lookup differs, since
    # GameItem and AppItem are separate tables with non-overlapping id
    # spaces -- collection.launch_disk_id must be resolved against whichever
    # table entity.source_type actually points into.
    collection = entity._db_collection
    if (
        drive is None
        and entity.era in _DRIVE_ERAS
        and collection is not None
        and collection.launch_disk_id
    ):
        if entity.source_type == "app":
            from backend.models.app import AppItem

            launch_leaf = db.get(AppItem, collection.launch_disk_id)
        else:
            launch_leaf = db.get(GameItem, collection.launch_disk_id)
        if launch_leaf is not None:
            drive = create_drive_for_collection(collection, launch_leaf, db)

    if (
        drive is not None
        and not entity.installed
        and not entity.requires_install
        and entity.folder_path is not None
        and Path(entity.folder_path).is_dir()
    ):
        # media_path is a single resolved launch file (items.py reassigns it at
        # add time); folder_path is the loose-file source directory to size from
        # and copy in full.
        src_dir = Path(entity.folder_path)
        if not drive.image_path:
            raise RuntimeError(f"Drive id={drive.id!r} has no image_path — re-add the library item.")
        img_path = Path(drive.image_path)
        if img_path.exists():
            img_path.unlink()
        fresh_size = max(FAT16_SIZE_MIN_MB, min(
            compute_drive_size_mb(src_dir, entity.media_type or ""),
            FAT16_SIZE_MAX_MB,
        ))
        if fresh_size != drive.size_mb:
            drive.size_mb = fresh_size
            db.add(drive)
            db.commit()
        format_fat16(img_path, fresh_size)
        _copy_loose_files_to_drive(src_dir, img_path, fresh_size)
        if collection is not None:
            collection.installed = True
            db.add(collection)
            db.commit()

    return drive
