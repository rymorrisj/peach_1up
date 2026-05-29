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
    from backend.models.library import LibraryItem


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


def hydrate_drive_for_item(item: "LibraryItem", db: "Session") -> "Drive | None":
    """Resolve or create drive; copy loose files on first launch.

    On first launch of a loose-file DOS item, the drive image is (re)created
    and all source files are written into it. Raises RuntimeError on any
    filesystem or integrity failure — callers must not swallow this.

    SECURITY NOTE: img_path.unlink() silently discards any prior image content
    on every pre-install launch. This is intentional but means a user who
    manually placed data in the image will lose it on retry.
    """
    from backend.models.drive import Drive
    from backend.service.utils.drive_utils import compute_drive_size_mb, create_drive_for_item

    drive = db.query(Drive).filter(Drive.library_item_id == item.id).first()
    if drive is None:
        drive = create_drive_for_item(item, db)

    if (
        drive is not None
        and not item.installed
        and not item.requires_install
        and Path(item.media_path).is_dir()
    ):
        if not drive.image_path:
            raise RuntimeError(f"Drive id={drive.id!r} has no image_path — re-add the library item.")
        img_path = Path(drive.image_path)
        if img_path.exists():
            if item.installed:
                raise RuntimeError(
                    f"Drive image at {img_path} already contains installed data and will not be automatically overwritten. "
                    "To force a reinstall, manually delete the drive image file."
                )
            img_path.unlink()
        fresh_size = max(FAT16_SIZE_MIN_MB, min(
            compute_drive_size_mb(Path(item.media_path), item.media_type or ""),
            FAT16_SIZE_MAX_MB,
        ))
        if fresh_size != drive.size_mb:
            drive.size_mb = fresh_size
            db.add(drive)
            db.commit()
        format_fat16(img_path, fresh_size)
        _copy_loose_files_to_drive(Path(item.media_path), img_path, fresh_size)
        item.installed = True
        db.add(item)
        db.commit()

    return drive
