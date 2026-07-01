"""DOS / Windows 3.1 environment drive hydration.

Replaces the retired per-item Drive model. DOS/Win3.1 media run against a
single shared, persistent FAT16 C: image per era (the environment-style model
86Box already uses). This module:

  * ensures that shared image exists (formatting it on first use), and
  * for pattern-1 (ready-to-run, ``requires_install=False``) directory media,
    copies the game's files into ``C:\\GAMES\\<slug>\\`` on first launch so it
    runs from — and saves to — the writable shared drive rather than a
    read-only D: mount.

Installer media (pattern 2/3) needs none of the copy logic: the source mounts
read-only on D:, the installer writes to the shared C: itself.

Every step fails loud — a missing preset path, a provisioning error, or a
copy/verify mismatch raises a normal Python exception rather than degrading
into an opaque DOSBox-X console error.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from backend.core.logger import get_logger
from backend.service.utils.fat import read_file_from_image, write_file_to_image

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from backend.models.platform import Platform
    from backend.service.launch.launchable_resolver import LaunchableEntity

logger = get_logger(__name__)

_GAMES_ROOT = "GAMES"


def ensure_working_image(platform: "Platform", db: "Session") -> Path:
    """Return the shared C: image path, provisioning (formatting) it if absent.

    working_image_path is preset on the seeded DOS/Win3.1 environment; the file
    is created lazily here on first launch via provision_platform, which
    format_fat16s a real FAT16 filesystem before DOSBox-X ever starts.
    """
    from backend.service.utils.vm import provision_platform

    if not platform.working_image_path:
        raise RuntimeError(
            f"Environment '{platform.slug or platform.id}' has no working_image_path — "
            "cannot resolve a C: drive for this DOS/Win3.1 launch."
        )

    path = Path(platform.working_image_path)
    if path.exists():
        return path

    _iso, working, _cfg, _install, _rom = provision_platform(platform)
    if not working or not Path(working).exists():
        raise RuntimeError(
            f"Provisioning did not produce a working image for environment "
            f"'{platform.slug or platform.id}'."
        )
    return Path(working)


def _relative_run_command(entity: "LaunchableEntity", media_dir: Path) -> str | None:
    """Derive the executable command relative to the copied game directory.

    E.g. media/rally/RALLY.EXE under media/rally/ becomes "RALLY.EXE"; a nested
    media/rally/BIN/RALLY.EXE becomes "BIN\\RALLY.EXE". Returns None when the
    item has no executable_path.
    """
    if not entity.executable_path:
        return None
    exe = Path(entity.executable_path)
    try:
        rel = exe.resolve().relative_to(media_dir.resolve())
    except ValueError:
        rel = Path(exe.name)
    return str(rel).replace("/", "\\")


def _copy_dir_into_image(src_dir: Path, img_path: Path, dest_prefix: str) -> None:
    """Copy every file under src_dir into img_path at dest_prefix/<relative>.

    Uses MD5 read-back verification (integrity only, not security) and raises on
    any mismatch. Raises if src_dir has no files.
    """
    if not src_dir.is_dir():
        raise RuntimeError(f"pattern-1 source is not a directory: {src_dir}")
    files = [f for f in src_dir.rglob("*") if f.is_file()]
    if not files:
        raise RuntimeError(f"No files found under {src_dir} to copy onto the shared drive")
    for f in files:
        data = f.read_bytes()
        src_md5 = hashlib.md5(data).hexdigest()
        rel = f.relative_to(src_dir)
        dest = f"{dest_prefix}/{str(rel).replace(chr(92), '/')}"
        write_file_to_image(img_path, dest, data)
        read_back = read_file_from_image(img_path, dest)
        if hashlib.md5(read_back).hexdigest() != src_md5:
            raise RuntimeError(
                f"MD5 mismatch copying {f} into {img_path} at {dest} — aborting launch."
            )


def prepare_pattern1_media(
    entity: "LaunchableEntity",
    working_image_path: Path,
    db: "Session",
) -> tuple[str | None, str | None]:
    """Copy ready-to-run directory media onto the shared C: drive on first launch.

    Returns (run_dir, run_command):
      * run_dir     — backslash subdir on C: to cd into (e.g. "GAMES\\rally"),
                      or None for installer / non-directory media (pattern 2/3).
      * run_command — the executable to run relative to run_dir, or None.

    The copy runs only once (guarded by item.installed); subsequent launches
    reuse the files already on the persistent drive.
    """
    if entity.requires_install:
        return None, None
    media = Path(entity.media_path)
    if not media.is_dir():
        return None, None

    slug = entity.slug
    if not slug:
        raise RuntimeError(
            f"Cannot place ready-to-run media on the shared drive: item {entity.item_id} has no slug."
        )

    dest_prefix = f"{_GAMES_ROOT}/{slug}"
    if not entity.installed:
        _copy_dir_into_image(media, working_image_path, dest_prefix)
        if entity._db_item is not None:
            entity._db_item.installed = True
            db.add(entity._db_item)
            db.commit()
        logger.info("Copied ready-to-run media for '%s' into C:\\%s", slug, dest_prefix.replace("/", "\\"))

    return dest_prefix.replace("/", "\\"), _relative_run_command(entity, media)
