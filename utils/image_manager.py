"""Image management utilities for Peach 1UP.

Handles creation and deletion of working copies of OS platform images, and
basic snapshot create/restore/list/delete for registered platforms.
All emulator launches use the working copy — the base image is never modified.
"""

from __future__ import annotations

import datetime
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


_INVALID_FILENAME_CHARS = frozenset('<>:"/\\|?*')


def create_snapshot(working_image_path: Path, snapshot_name: str) -> Path:
    """Copy the working image to a named snapshot in the snapshots/ subdirectory.

    The snapshot is written to a ``.tmp`` file first and renamed into place
    atomically via ``os.replace()``, so an interrupted write cannot produce a
    corrupt snapshot.

    .. warning::
        Each snapshot is a full copy of the working image and will consume
        significant disk space. The caller should warn the user before invoking
        this function.

    Args:
        working_image_path: Path to the working image to snapshot.
        snapshot_name: Short label for the snapshot. Must be non-empty, must
            not contain path separators or characters invalid on Windows
            (``< > : " / \\ | ? *``), and must not be ``.`` or ``..``.
        snapshot_name: Short label for the snapshot.

    Returns:
        Path to the newly created snapshot file.

    Raises:
        FileNotFoundError: If ``working_image_path`` does not exist.
        ValueError: If ``snapshot_name`` is empty, is ``.`` or ``..``, or
            contains path separators or Windows-invalid filename characters.
        OSError: If the copy or rename fails due to a filesystem error.
    """
    if not snapshot_name or snapshot_name.strip() == "":
        raise ValueError("snapshot_name must not be empty.")
    if snapshot_name in (".", ".."):
        raise ValueError(f"snapshot_name '{snapshot_name}' is not a valid filename.")
    invalid = _INVALID_FILENAME_CHARS.intersection(snapshot_name)
    if invalid:
        raise ValueError(
            f"snapshot_name contains invalid characters: "
            f"{', '.join(sorted(invalid))}"
        )

    if not working_image_path.exists():
        raise FileNotFoundError(f"Working image not found: {working_image_path}")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshots_dir = working_image_path.parent / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    target = snapshots_dir / f"{snapshot_name}_{timestamp}.img"

    logger.warning(
        "Creating snapshot '%s' of '%s' — this is a full image copy and will "
        "consume significant disk space. Target: %s",
        snapshot_name,
        working_image_path.name,
        target,
    )

    tmp_path = target.with_suffix(target.suffix + ".tmp")
    try:
        shutil.copy2(str(working_image_path), str(tmp_path))
        os.replace(str(tmp_path), str(target))
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise

    return target


def restore_snapshot(snapshot_path: Path, working_image_path: Path) -> None:
    """Replace the working image with the contents of a snapshot.

    The snapshot is copied to a ``.tmp`` file in the working image's directory
    and renamed into place atomically via ``os.replace()``. The snapshot file
    is not deleted after restore — snapshots are reusable.

    .. danger::
        This is a destructive operation. The current working image is
        permanently replaced. The caller is responsible for obtaining explicit
        user confirmation before invoking this function.

    Args:
        snapshot_path: Path to the snapshot file to restore from.
        working_image_path: Path where the restored working image will be written.
            The file need not exist, but its parent directory must.

    Raises:
        FileNotFoundError: If ``snapshot_path`` does not exist.
        FileNotFoundError: If the parent directory of ``working_image_path``
            does not exist.
        OSError: If the copy or rename fails due to a filesystem error.
    """
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")

    if not working_image_path.parent.exists():
        raise FileNotFoundError(
            f"Working image directory does not exist: {working_image_path.parent}"
        )

    tmp_path = working_image_path.with_suffix(working_image_path.suffix + ".tmp")
    try:
        shutil.copy2(str(snapshot_path), str(tmp_path))
        os.replace(str(tmp_path), str(working_image_path))
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise


def list_snapshots(working_image_path: Path) -> list[Path]:
    """Return all snapshot files in the snapshots/ subdirectory next to the working image.

    Args:
        working_image_path: Path to the working image. Snapshots are looked up
            in a ``snapshots/`` subdirectory of its parent.

    Returns:
        Sorted list of snapshot file paths (ascending by filename, which is
        chronological given the ``YYYYMMDD_HHMMSS`` timestamp format).
        Returns an empty list if the snapshots directory does not exist.
    """
    snapshots_dir = working_image_path.parent / "snapshots"
    if not snapshots_dir.exists():
        return []
    return sorted(p for p in snapshots_dir.iterdir() if p.is_file())


def delete_snapshot(snapshot_path: Path) -> None:
    """Delete the snapshot file at the given path.

    .. danger::
        This operation is irreversible — snapshots cannot be recovered once
        deleted. The caller is responsible for obtaining explicit user
        confirmation before invoking this function.

    Args:
        snapshot_path: Path to the snapshot file to delete.

    Raises:
        FileNotFoundError: If ``snapshot_path`` does not exist.
        OSError: If the file cannot be deleted.
    """
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")
    snapshot_path.unlink()


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
