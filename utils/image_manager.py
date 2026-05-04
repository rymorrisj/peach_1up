"""Image management utilities for Peach 1UP.

Handles creation and deletion of working copies of OS platform images.
All emulator launches use the working copy — the base image is never modified.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path


logger = logging.getLogger(__name__)


def get_working_copy_path(base_image_path: Path, era: str, platform_id: str) -> Path:
    """Return the expected working copy path without checking existence.

    Args:
        base_image_path: Path to the base image file.
        era: Era string (e.g. ``"win95"``).
        platform_id: UUID string identifying the platform.

    Returns:
        Expected path for the working copy.
    """
    return Path("images") / "os" / era / platform_id / base_image_path.name


def working_copy_exists(base_image_path: Path, era: str, platform_id: str) -> bool:
    """Return True if a working copy already exists at the expected target path.

    Args:
        base_image_path: Path to the base image file.
        era: Era string (e.g. ``"win95"``).
        platform_id: UUID string identifying the platform.

    Returns:
        True if the working copy file exists, False otherwise.
    """
    return get_working_copy_path(base_image_path, era, platform_id).exists()


def create_working_copy(base_image_path: Path, era: str, platform_id: str) -> Path:
    """Copy the base image to the platform's working directory.

    The base image is never modified. All emulator launches use the working copy.
    The copy is written to a ``.tmp`` file first and renamed into place atomically
    via ``os.replace()``, so an interrupted write cannot leave a corrupt working
    copy that blocks recovery — the original is untouched until the rename
    succeeds.

    .. warning::
        This operation doubles disk usage for the image file. A multi-GB image
        will consume the same space again under ``images/os/{era}/{platform_id}/``.
        The caller should warn the user before invoking this function.

    Args:
        base_image_path: Path to the source base image file.
        era: Era string (e.g. ``"win95"``).
        platform_id: UUID string identifying the platform.

    Returns:
        Path to the newly created working copy.

    Raises:
        FileNotFoundError: If ``base_image_path`` does not exist.
        FileExistsError: If a working copy already exists at the target path.
            Delete it explicitly before calling this function again.
        OSError: If the copy or rename fails due to a filesystem error.
    """
    if not base_image_path.exists():
        raise FileNotFoundError(f"Base image not found: {base_image_path}")

    target = get_working_copy_path(base_image_path, era, platform_id)

    if target.exists():
        raise FileExistsError(
            f"Working copy already exists: {target}. "
            "Delete it explicitly before creating a new one."
        )

    logger.warning(
        "Creating working copy of '%s' — this will double disk usage for this image. "
        "Target: %s",
        base_image_path.name,
        target,
    )

    target.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = target.with_suffix(target.suffix + ".tmp")
    try:
        shutil.copy2(str(base_image_path), str(tmp_path))
        os.replace(str(tmp_path), str(target))
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise

    return target


def delete_working_copy(working_image_path: Path) -> None:
    """Delete the working copy at the given path.

    This is a destructive, irreversible operation. The caller is responsible
    for obtaining explicit user confirmation before invoking this function.

    Args:
        working_image_path: Path to the working copy to delete.

    Raises:
        FileNotFoundError: If ``working_image_path`` does not exist.
        OSError: If the file cannot be deleted.
    """
    if not working_image_path.exists():
        raise FileNotFoundError(f"Working copy not found: {working_image_path}")
    working_image_path.unlink()
